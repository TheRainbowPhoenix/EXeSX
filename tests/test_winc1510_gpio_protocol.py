"""Firmware-free tests of the extended WINC electrical control lines.

Do not mistake these for original WLAN menu OK results. The test only
checks GPIO_RESET/EN, HIF interrupt, and socket semantics.
"""
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from winc1510_spi_backend import Winc1510SPI, recv_exact


class WincGPIOTests(unittest.TestCase):
    def test_pending_hif_irq_n_only_after_real_device_callback(self):
        chip = Winc1510SPI(hif_mailbox=True, flash=b"\x11" * 1024)
        self.assertTrue(chip.irq_n)
        chip._write_reg(0x1078, 2)  # outbound grant, NOT an inbound event
        self.assertTrue(chip.irq_n)
        chip.queue_hif_callback(1, 0x2c, b"\x01" + bytes(3))
        self.assertFalse(chip.irq_n)
        chip._write_reg(0x1070, chip._read_reg(0x1070) & ~1)
        self.assertTrue(chip.irq_n)
        chip.queue_hif_callback(1, 0x2c, b"\x00" * 4)
        self.assertFalse(chip.irq_n)
        chip.set_pins(reset_n=False)
        self.assertTrue(chip.irq_n)
        self.assertEqual(chip._read_reg(0x1070), 0)
        self.assertEqual(chip.flash, b"\x11" * 1024)
        self.assertEqual(chip.shift(2, b"\xca\x00\x10\x00",
                                    begin=True, end=True), b"\xff" * 4)
        chip.set_pins(reset_n=True)
        self.assertTrue(chip.irq_n)
        self.assertEqual(chip._read_reg(0x1000), 0x1002b0)

    def test_chip_enable_line_disconnects_but_wake_is_not_success(self):
        chip = Winc1510SPI(hif_mailbox=True)
        chip.set_pins(wake_n=True)
        self.assertEqual(chip.hif_requests, [])
        self.assertTrue(chip.irq_n)
        chip.set_pins(chip_enable=False)
        self.assertEqual(chip.shift(2, bytes.fromhex("ca001000"),
                                    begin=True, end=True), b"\xff" * 4)
        chip.set_pins(chip_enable=True)
        self.assertEqual(chip._read_reg(0x1000), 0x1002b0)
        self.assertTrue(chip.irq_n)

    def test_opt_in_ap_fixture_only_answers_original_hif_request(self):
        # Source-derived: original FUN_601c37d0 sends 0xBB connect,
        # FUN_601c4088 sends 0x05 AP details, and FUN_601c3d78
        # sends 0x2B disconnect. Earlier 0x10/0x2F/0x03 expectations
        # confused outgoing and incoming opcodes.
        chip = Winc1510SPI(hif_mailbox=True, fixture_ssid="PRIVATE_SIM_AP")
        self.assertTrue(chip.irq_n)
        self.assertFalse(chip.ap_connected)
        addr = 0x30000

        def guest_hif(opcode, payload=b""):
            raw = bytes((1, opcode))
            raw += (8 + len(payload)).to_bytes(2, "little")
            raw += bytes(4) + payload
            chip._dma_put(addr, raw)
            chip._write_reg(0x106c, (addr << 2) | 2)

        guest_hif(0xbb, b"PRIVATE_SIM_AP" + bytes(34))
        self.assertTrue(chip.ap_connected)
        self.assertFalse(chip.irq_n)
        self.assertEqual(chip.hif_notifications[-1][:2], (1, 0x2c))
        self.assertEqual(chip._dma_get(0x32000 + 8, 4),
                         bytes((1, 0, 0, 0)))

        # Original A7 requests SSID/channel while connection IRQ pending.
        # Device callback waits until original A7 clears bit 0 at 0x1070.
        guest_hif(5)
        self.assertEqual(len(chip.deferred_callbacks), 1)
        chip._write_reg(0x1070, chip._read_reg(0x1070) & ~1)
        # A7 ACK happens before it reads original callback RAM. Until
        # it has clocked all 12 bytes, AP info MUST NOT overwrite it.
        self.assertTrue(chip.irq_n)
        self.assertEqual(chip._dma_get(0x32000 + 8, 4),
                         bytes((1, 0, 0, 0)))
        chip._dma_get(0x32000, 12)
        self.assertFalse(chip.irq_n)
        self.assertEqual(chip.hif_notifications[-1][:2], (1, 6))
        info = chip._dma_get(0x32000 + 8, 48)
        self.assertEqual(info[:14], b"PRIVATE_SIM_AP")
        self.assertEqual(info[45], 6)
        chip._write_reg(0x1070, chip._read_reg(0x1070) & ~1)
        # A7 must read the full 56-byte AP info frame after ACK.
        chip._dma_get(0x32000, 56)
        self.assertTrue(chip.irq_n)
        guest_hif(0x2b)
        self.assertFalse(chip.ap_connected)
        self.assertFalse(chip.irq_n)
        self.assertEqual(chip._dma_get(0x32000 + 8, 4), bytes(4))
        with self.assertRaises(ValueError):
            Winc1510SPI(fixture_ssid="AP")
        self.assertEqual(Winc1510SPI(hif_mailbox=True).hif_notifications, [])

    def test_original_tcg_idle_does_not_drop_live_winc_session(self):
        """A7 RTOS/DMA may take >5s between real SPI frames under TCG.

        Old backend conn.settimeout(5) disconnected and reset HIF state.
        Keep the same TCP/PCS transaction alive through host-side idle.
        """
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/winc1510_spi_backend.py"),
             "--port", str(port), "--gpio-status"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(70):
                try:
                    connection = socket.create_connection(
                        ("127.0.0.1", port), .1)
                    break
                except OSError:
                    if proc.poll() is not None:
                        self.fail("WINC backend failed before listen")
                    time.sleep(.03)
            else:
                self.fail("WINC backend never listened")
            with connection as sock:
                sock.settimeout(2)
                sock.sendall(bytes((255, 0x20, 0, 0)))
                self.assertEqual(recv_exact(sock, 1), bytes((1,)))
                # No QEMU SPI transfer for more than the former 5s bound.
                time.sleep(5.2)
                sock.sendall(bytes((255, 0x20, 0, 0)))
                self.assertEqual(recv_exact(sock, 1), bytes((1,)))
                self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_extended_socket_irq_poll_and_legacy_byte_clock(self):
        # Stand-alone device loopback only, no QEMU or original ROM.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        p = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/winc1510_spi_backend.py"),
             "--port", str(port), "--gpio-status", "--hif-mailbox"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(60):
                try:
                    connection = socket.create_connection(("127.0.0.1", port), .1)
                    break
                except OSError:
                    if p.poll() is not None:
                        self.fail("Python WINC backend exited before listen")
                    time.sleep(.03)
            else:
                self.fail("Backend never listened")
            with connection as sock:
                sock.settimeout(2)
                sock.sendall(bytes((255, 0x20, 0, 0)))
                self.assertEqual(recv_exact(sock, 1), b"\x01")
                # Enabled RESET_N=1, CHIP_EN=1, CS BEGIN=1.
                sock.sendall(bytes((2, 0x15, 4, 0)) + bytes.fromhex("ca001000"))
                self.assertEqual(recv_exact(sock, 5), b"\xff" * 4 + b"\x01")
                # CS END=2, same controls; read WINC ID from SPI.
                sock.sendall(bytes((2, 0x16, 7, 0)) + bytes(7))
                self.assertEqual(recv_exact(sock, 8), bytes.fromhex("ca00f3b0021000") + b"\x01")
                # Active reset pin: bus goes electrically absent.
                sock.sendall(bytes((2, 0x12, 4, 0)) + bytes.fromhex("ca001000"))
                self.assertEqual(recv_exact(sock, 5), b"\xff" * 4 + b"\x01")
                sock.sendall(bytes((255, 0x20, 0, 0)))
                self.assertEqual(recv_exact(sock, 1), b"\x01")
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if __name__ == "__main__":
    unittest.main()
