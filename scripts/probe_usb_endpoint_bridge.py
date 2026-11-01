#!/usr/bin/env python3
"""Real ARM/ChipIdea EP0 SETUP plus EP1 OUT descriptor-to-socket test.

The synthetic ARM guest writes a QH, active dTD and genuine USB MMIO
registers. Python externally injects USB bus packets via the TCP bridge.
Only actual guest DMA buffers and ENDPTCOMPLETE status count as PASS.
No OSUP or guest memory patching/IPC is involved in this probe.
"""
import argparse
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import re
from drive_factory_menu import QMP, choose_port, connect
from usb_endpoint_host import USBEndpointHost, ATTACH, SETUP, OUT, IN

ENTRY = 0x60000000
QH = 0x62010000
DTD = 0x62011000
RX_BUFFER = 0x62012000
USB = 0x40330000


def elf():
    ins, literals = [], []
    def emit(n):
        ins.append(n)
    def lit(reg, val):
        literals.append((len(ins), reg, val))
        emit(0)
    def st(reg, base, offset):
        emit(0xe5800000 | (base << 16) | (reg << 12) | offset)
    lit(7, QH)
    lit(1, DTD)
    st(1, 7, 0x90)  # original EP1 OUT queue-head dTD next pointer
    lit(7, DTD)
    lit(1, 1)
    st(1, 7, 0)  # final dTD next=terminate
    lit(1, (4 << 16) | 0x80)  # ACTIVE, 4 bytes
    st(1, 7, 4)
    lit(1, RX_BUFFER)
    st(1, 7, 8)
    lit(0, USB)
    lit(1, 2)
    st(1, 0, 0x1a4)  # USBMODE device
    lit(1, QH)
    st(1, 0, 0x158)  # ENDPTLISTADDR, 2-KiB aligned
    lit(1, 0x45)
    st(1, 0, 0x148)  # USBINTR: UI, PCD, URI
    lit(1, 1)
    st(1, 0, 0x140)  # USBCMD.RUN
    lit(1, 2)
    st(1, 0, 0x1b0)  # ENDPTPRIME: ep1 OUT
    emit(0xeafffffe)
    for pos,reg,value in literals:
        offset = len(ins) * 4 - pos * 4 - 8
        if not 0 <= offset <= 4095:
            raise ValueError("ARM literal too distant")
        ins[pos] = 0xe59f0000 | (reg << 12) | offset
        ins.append(value)
    code = struct.pack("<{}I".format(len(ins)), *ins)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                         ENTRY, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I", 1, 0x100, ENTRY, ENTRY,
                       len(code), len(code), 5, 0x100)
    return header + phdr + bytes(0x100 - len(header) - len(phdr)) + code


def word(q, address):
    data = q.hmp("xp /1wx 0x{:x}".format(address))
    m = re.search(r":\s+0x([0-9a-fA-F]+)", data)
    if not m:
        raise AssertionError("Guest MMIO unavailable: "+data)
    return int(m.group(1), 16)


def run(qemu, profile):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        elf_path = root/"probe.elf"
        elf_path.write_bytes(elf())
        port = choose_port()
        qport = choose_port()
        while qport == port:
            qport = choose_port()
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
        env["EXESX_EXPERIMENTAL_USB_ENDPOINTS"] = "1"
        env["EXESX_USB_FIXTURE_TCP_PORT"] = str(port)
        lib = qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH","")
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg,thread=single", "-display", "none",
               "-serial", "none", "-monitor", "none", "-no-reboot",
               "-S", "-qmp", "tcp:127.0.0.1:{},server=on,wait=off".format(qport),
               "-device", "loader,file={},cpu-num=0".format(elf_path)]
        with (root/"qemu.log").open("wb") as log:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                with connect(qport, proc) as conn:
                    q = QMP(conn)
                    q.execute("cont")
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        if word(q, USB + 0x1b8) == 2:
                            break
                        time.sleep(.05)
                    else:
                        raise AssertionError("Original ARM did not PRIME EP1 OUT")
                    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                        sock.settimeout(3)
                        host = USBEndpointHost(sock, 3)
                        self_result = host.transaction(ATTACH)
                        assert self_result == b""
                        setup = bytes.fromhex("8006000100001200")
                        assert host.transaction(SETUP, data=setup) == b""
                        assert host.transaction(OUT, ep=1, data=b"TEST") == b""
                        try:
                            host.transaction(IN, ep=2, request_length=2,
                                             retry=False)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError("unprimed USB IN endpoint falsely completed")
                    assert word(q, QH+0x28) == 0x01000680, hex(word(q,QH+0x28))
                    assert word(q, QH+0x2c) == 0x00120000
                    assert word(q, RX_BUFFER) == 0x54534554, hex(word(q,RX_BUFFER))
                    assert word(q, DTD+4) & (0x80 | 0x7fff0000) == 0
                    assert word(q, USB+0x1bc) & 2
                    assert word(q, USB+0x1a8) & 1
                    assert word(q, USB+0x144) & 1
                    print("PASS original ARM ChipIdea EP0 SETUP QH RAM,"
                          " EP1 OUT 4-byte dTD DMA, guest ENDPTCOMPLETE"
                          " + USBSTS.UI and unprimed IN negative", flush=True)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if proc.returncode and proc.returncode != -15:
                    print((root/"qemu.log").read_text(errors="replace")[-1200:],
                          flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    a = p.parse_args()
    run(a.qemu, a.profile)
