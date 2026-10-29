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
                self.assertEqual(sock.recv(5), b"\xff" * 4 + b"\x01")
                sock.sendall(bytes((255, 0x20, 0, 0)))
                self.assertEqual(sock.recv(1), b"\x01")
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if __name__ == "__main__":
    unittest.main()
