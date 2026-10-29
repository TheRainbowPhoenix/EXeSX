"""Host-side USB protocol tests; no proprietary ROM or fake guest OK."""
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from usb_endpoint_host import (
    USBEndpointHost, EndpointFactoryStream, SETUP, OUT, IN,
    ATTACH, RESET, MAX_PACKET,
)
from usb_factory_host import recv_exact

DEVICE = bytes.fromhex("120100020000004034127856000101020301")
CONFIG = bytes.fromhex(
    "090220000101008032"
    "0904000002ff000000"
    "07050102400000"
    "07058102400000"
)


class BridgeTests(unittest.TestCase):
    def test_original_device_driven_enumeration_and_bulk(self):
        left, right = socket.socketpair()
        received = []
        def bridge_stub():
            try:
                for _ in range(16):
                    try:
                        header = recv_exact(right, 4)
                    except ConnectionError:
                        return
                    op, ep, length = struct.unpack("<BBH", header)
                    payload = recv_exact(right, length) if op != IN else b""
                    received.append((op, ep, payload, length))
                    data = b""
                    if op == IN and ep == 0:
                        if length == 18:
                            data = DEVICE
                        elif length == 9:
                            data = CONFIG[:9]
                        elif length == len(CONFIG):
                            data = CONFIG
                    elif op == IN and ep == 1:
                        data = bytes.fromhex("ffff80000600")
                    response = struct.pack("<BBH", 0, ep, len(data)) + data
                    right.sendall(response)
            finally:
                right.close()
        t=threading.Thread(target=bridge_stub,daemon=True)
        t.start()
        try:
            host=USBEndpointHost(left, timeout=.2)
            info=host.enumerate()
            self.assertEqual(info["bulk_in"], 1)
            self.assertEqual(info["bulk_out"], 1)
            self.assertEqual(info["max_packet"], 64)
            socket_like=EndpointFactoryStream(host)
            socket_like.sendall(bytes.fromhex("ffff01000600"))
            self.assertEqual(socket_like.recv(2), b"\xff\xff")
            self.assertEqual(recv_exact(socket_like, 4),
                             bytes.fromhex("80000600"))
            self.assertEqual(received[0][0], ATTACH)
            self.assertEqual(received[1][0], RESET)
            self.assertEqual(received[2][0], SETUP)
            self.assertTrue(any(op == OUT and ep == 1 and
                                payload == bytes.fromhex("ffff01000600")
                                for op, ep, payload, _ in received))
        finally:
            left.close()
            t.join(timeout=1)

    def test_nak_and_invalid_buffers_do_not_claim_success(self):
        left, right = socket.socketpair()
        def no_device():
            try:
                while True:
                    try:
                        data = recv_exact(right, 4)
                    except ConnectionError:
                        break
                    op, ep, count = struct.unpack("<BBH", data)
                    if op != IN:
                        recv_exact(right, count)
                    right.sendall(struct.pack("<BBH", 1, ep, 0))
            finally:
                right.close()
        t=threading.Thread(target=no_device,daemon=True)
        t.start()
        try:
            host=USBEndpointHost(left, timeout=.08)
            with self.assertRaises(RuntimeError):
                host.transaction(IN, 1, request_length=2)
            with self.assertRaises(ValueError):
                host.transaction(OUT, 1, b"x" * (MAX_PACKET+1))
        finally:
            left.close()
            t.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
