#!/usr/bin/env python3
"""Decode private QEMU LCD write values into public-safe *metadata*.

Source: QEMU EXeSX memtrace plugin with virtual_only=1,values=1.
Inputs contain proprietary command/pixel values: NEVER commit raw traces.
This script emits only command IDs, counts, window extents and RGB565
histograms. It cannot infer physical LCD model or unobserved framebuffer.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

WRITE = re.compile(
    r"EXESX_VALUE cpu=(\d+) pc=0x([0-9a-fA-F]+) kind=WRITE "
    r"virtual=0x([0-9a-fA-F]+) width=(\d+) value=0x([0-9a-fA-F]+)")
LEGACY_WRITE = re.compile(
    r"EXESX_LCD cpu=(\d+) pc=([0-9a-fA-F]+) "
    r"addr=([0-9a-fA-F]+) width=(\d+) val=([0-9a-fA-F]+)")
CMD_PCS = {0x6001514c, 0x60015268, 0x600152c0, 0x60015314,
           0x6001535c, 0x60015364}
PIXEL_PCS = {0x600154fc, 0x6001550c, 0x60015518, 0x600154d8,
             0x600154e8, 0x600154f0}
PORT = 0xb0000000


def decode_lines(lines):
    commands, control_writes = [], []
    pixel_hist = Counter()
    pixel_samples = 0
    current = None
    width_hist = Counter()
    for line in lines:
        match = WRITE.search(line) or LEGACY_WRITE.search(line)
        if not match:
            continue
        cpu, pc, addr, width, value = (int(x, 16) if i in (1, 2, 4)
                                         else int(x)
                                      for i, x in enumerate(match.groups()))
        if cpu != 0 or width not in (2, 4):
            continue
        if addr != PORT:
            if addr in (0x44f00000, 0x44f00004):
                control_writes.append({"address":hex(addr),
                                       "width":width})
            continue
        width_hist[width] += 1
        if pc in CMD_PCS:
            current = {"command":value & 255, "params":[],
                       "pc":hex(pc), "pixel_samples":0}
            commands.append(current)
        elif pc in PIXEL_PCS:
            pixel_hist[value & 0xffff] += 1
            pixel_samples += 1
            if current is not None:
                current["pixel_samples"] += 1
        elif current is not None:
            current["params"].append(value)
    def last_params(cmd):
        return [c["params"] for c in commands if c["command"] == cmd]
    def windows(cmd):
        out = []
        for p in last_params(cmd):
            if len(p) >= 4:
                start = ((p[0] & 255) << 8) | (p[1] & 255)
                end = ((p[2] & 255) << 8) | (p[3] & 255)
                out.append({"start":start, "end":end, "count":end-start+1,
                            "params_above_byte_range":sum(x>255 for x in p[:4])})
        return out
    return {
        "port":"0xb0000000",
        "command_count":len(commands),
        "commands":[{"id":f"0x{c['command']:02x}",
                     "param_count":len(c["params"]),
                     "pixels_seen":c["pixel_samples"]} for c in commands],
        "column_windows":windows(0x2a),
        "row_windows":windows(0x2b),
        "te_enable_observed":bool(last_params(0x35)),
        "rgb565_mode_observed":any(p and p[0] == 0x55 for p in last_params(0x3a)),
        "ramwr_observed":bool(last_params(0x2c)),
        "pixel_samples":pixel_samples,
        "pixel_top_colors":[{"rgb565":f"0x{val:04x}", "count":num}
                            for val,num in pixel_hist.most_common(6)],
        "write_widths":dict(sorted(width_hist.items())),
        "other_bus_control_write_count":len(control_writes),
        "disclaimer":"Sampled writes, not a complete frame. RGB565 decoding "
                     "assumes commands/data distinguished by original ROM PCs.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_trace", type=Path)
    ap.add_argument("--json", type=Path, help="metadata output; no raw values")
    args = ap.parse_args()
    summary = decode_lines(args.private_trace.read_text(errors="replace").splitlines())
    out = json.dumps(summary, indent=2) + "\n"
    if args.json:
        args.json.write_text(out)
    print(out)


if __name__ == "__main__":
    main()
