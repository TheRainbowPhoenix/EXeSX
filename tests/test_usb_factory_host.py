"""Firmware-free tests for the external USB *host* fixture wire protocol."""
import socket
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from usb_factory_host import packet, decode_header, recv_exact, exchange, plan


class USBFixtureTests(unittest.TestCase):
    def test_original_factory_six_byte_command_and_endian_ambiguity(self):
        self.assertEqual(packet(1), bytes.fromhex("ffff01000600"))
        self.assertEqual(packet(3, 2, b"ABC"),
                         bytes.fromhex("ffff03020900414243"))
        self.assertEqual(decode_header(bytes.fromhex("ffff80000600"))["length"],6)
        alt = decode_header(bytes.fromhex("ffff80050040"))
        self.assertEqual(alt["length"], 64)
        self.assertEqual(alt["length_endian"], "big")
        for bad in (b"", bytes.fromhex("ffff80000000"),
                    bytes.fromhex("00ff80000600")):
            with self.assertRaises(ValueError):
                decode_header(bad)
        with self.assertRaises(ValueError):
            packet(3, 0, bytes(8192))

    def test_external_fixture_stops_on_real_device_error(self):
        left, right = socket.socketpair()
        def fake_usb_guest():
            try:
                self.assertEqual(recv_exact(right, 6), packet(1))
                right.sendall(bytes.fromhex("ffff80000600"))
                self.assertEqual(recv_exact(right, 6), packet(3, 1))
                # Factory cannot pass: real A7 replied error.
                right.sendall(bytes.fromhex("ffff82000600"))
                # Do not accept an EXIT command after failure.
                right.settimeout(.2)
                try:
                    remainder = right.recv(6)
                    self.assertEqual(remainder, b"")
                except socket.timeout:
                    pass
            finally:
                right.close()
        t = threading.Thread(target=fake_usb_guest)
        t.start()
        try:
            with self.assertRaises(RuntimeError):
                plan(left, full_plan=True)
        finally:
            left.close()
            t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_host_only_smoke_sends_hello_without_fake_completion(self):
        left, right = socket.socketpair()
        def fake_usb_guest():
            try:
                self.assertEqual(recv_exact(right, 6), packet(1))
                right.sendall(bytes.fromhex("ffff80000600"))
                self.assertEqual(right.recv(1), b"")
            finally:
                right.close()
        t=threading.Thread(target=fake_usb_guest)
        t.start()
        try:
            records=plan(left)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["response"]["status"], "accepted")
        finally:
            left.close()
            t.join(timeout=2)
        self.assertFalse(t.is_alive())


if __name__ == "__main__":
    unittest.main()
