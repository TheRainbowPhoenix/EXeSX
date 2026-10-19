#!/usr/bin/env python3
"""Generate target-remote GDB commands to stop on the two BIOS memory writes.
QEMU -S -gdb tcp:127.0.0.1:1234 ; gdb-multiarch -x generated.gdb
Breakpoints are precise but slow inside a large zeroing loop. Use TCG plugin
for fast bulk access logs. No proprietary images are included.
"""
import argparse
from pathlib import Path

TARGETS=(0x61080000,0x67100000)
def render(port=1234):
    lines=[
        "set pagination off",
        "set confirm off",
        "set architecture arm",
        f"target remote 127.0.0.1:{port}",
        "set print pretty on",
        "# Direct breakpoint at Thumb STR zero-initialization instruction.",
        "# Conditional expressions identify the first word at each region.",
    ]
    for addr in TARGETS:
        lines += [
            "hbreak *0x60254714",
            f"condition $bpnum $r1 == {addr:#x}",
            "commands",
            "silent",
            f'printf "EXESX_GDB_ZERO_WRITE target=0x{addr:08x}\\n"',
            "info registers r0 r1 r2 r3 r9 pc cpsr",
            "x/8wx $r0",
            "x/4i $pc",
            "continue",
            "end",
        ]
    lines += ["# To stop without continuing, delete 'continue' from commands.",
              "continue"]
    return "\n".join(lines)+"\n"
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=1234)
    parser.add_argument("-o","--output",type=Path,default=Path("private/bios-zero-write.gdb"))
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(render(args.port))
    print(args.output)
if __name__=="__main__":
    main()
