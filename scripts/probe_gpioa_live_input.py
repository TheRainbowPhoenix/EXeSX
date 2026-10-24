#!/usr/bin/env python3
"""Firmware-free live M4 GPIOA input voltage A/B: actual ARM reads + QMP."""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from hmp_memory import memory_words

RESULT = 0x6200b400
MASK = 0x808c6008


def elf():
    words, literals = [], []
    def lit(reg, val):
        literals.append((len(words), reg, val))
        words.append(0)
    lit(7, RESULT)
    lit(0, 0x4100f000)
    lit(1, 0)
    words.append(0xe5801014)  # STR R1,[R0,#0x14] PDDR=0 (all inputs)
    loop = len(words)
    words.extend((0xe5902010, 0xe5872000))  # PDIR -> scratch RAM
    words.append(0xea000000 | ((loop - len(words) - 2) & 0xffffff))
    pool = len(words)
    for idx,(pos,reg,value) in enumerate(literals):
        off = (pool + idx - pos) * 4 - 8
        assert 0 <= off < 4096
        words[pos] = 0xe59f0000 | reg << 12 | off
        words.append(value)
    body = struct.pack("<%dI" % len(words), *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    head = struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,0x60000000,
                       52,0,0x05000000,52,32,1,0,0,0)
    phdr = struct.pack("<8I",1,0x100,0x60000000,0x60000000,
                       len(body),len(body),5,0x100)
    return head + phdr + bytes(0x100-len(head)-len(phdr)) + body


def exercise(qemu, profile):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder/"gpioa-live.elf"
        source.write_bytes(elf())
        input_file = folder/"pta-pins.txt"
        input_file.write_text("0\n")
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
        env["EXESX_GPIOA_INPUT_MASK"] = "0"
        env["EXESX_GPIOA_INPUT_MASK_FILE"] = str(input_file.resolve())
        lib = qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH","")
        with socket.socket() as free:
            free.bind(("127.0.0.1",0))
            port = free.getsockname()[1]
        cmd = [str(qemu.resolve()),"-machine","exesx","-m","64M",
               "-accel","tcg","-display","none","-serial","none",
               "-monitor","none","-no-reboot",
               "-device",f"loader,file={source.resolve()},cpu-num=0",
               "-qmp",f"tcp:127.0.0.1:{port},server=on,wait=off"]
        process = subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            conn = None
            for _ in range(80):
                if process.poll() is not None:
                    raise AssertionError("QEMU exited before QMP startup")
                try:
                    conn = socket.create_connection(("127.0.0.1",port),timeout=.35)
                    break
                except OSError:
                    time.sleep(.1)
            if conn is None:
                raise AssertionError("QMP listener unavailable")
            with conn:
                conn.settimeout(8)
                with conn.makefile("rb") as reader:
                    def response():
                        while True:
                            line = reader.readline()
                            if not line: raise AssertionError("QMP disconnected")
                            item = json.loads(line)
                            if "event" in item: continue
                            if "error" in item: raise AssertionError(str(item["error"]))
                            return item["return"]
                    assert "QMP" in json.loads(reader.readline())
                    def call(name, arguments=None):
                        obj = {"execute":name}
                        if arguments is not None: obj["arguments"] = arguments
                        conn.sendall((json.dumps(obj)+"\n").encode())
                        return response()
                    call("qmp_capabilities")
                    def value():
                        output = call("human-monitor-command",{
                            "command-line":f"xp /1wx 0x{RESULT:08x}"})
                        return memory_words(output,RESULT,1)[0]
                    def expect(expected):
                        for _ in range(40):
                            if value() == expected: return
                            time.sleep(.10)
                        raise AssertionError(
                            f"Live ARM GPIOA PDIR expected {expected:#x}, got {value():#x}")
                    expect(0)
                    for mask in (MASK,0):
                        new = folder/"new-mask.txt"
                        new.write_text(f"{mask:#x}\n")
                        os.replace(new,input_file)  # atomic external-voltage update
                        expect(mask)
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
    print("PASS live original ARM GPIOA input read 0 -> 0x808c6008 -> 0 with file updates")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    args = ap.parse_args()
    exercise(args.qemu,args.profile)
