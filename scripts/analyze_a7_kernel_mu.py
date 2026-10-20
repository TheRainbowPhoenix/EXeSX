#!/usr/bin/env python3
"""Summarize A7 semaphore 31 traffic and experimental M4 MU IRQ behavior.

Read-only reducer for private QEMU guest_errors,int,plugin logs. Never
interprets absent logged events as proof a device or callback worked.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

SEM = re.compile(r'EXESX_ACCESS\s+cpu=(\d+)\s+pc=0x([0-9a-fA-F]+)\s+kind=(READ|WRITE)\s+[^\r\n]*?physical=0x621eaedc\b')
BUSY = re.compile(r'EXeSX MU busy TR(\d+) at 0x([0-9a-fA-F]+) ignored data=0x([0-9a-fA-F]+)')
MU_WRITE = re.compile(r'EXeSX MU WRITE @0x([0-9a-fA-F]+) data=0x([0-9a-fA-F]+)')
ENTRY = re.compile(r'\.\.\.taking pending nonsecure exception (\d+)')
RETURN = re.compile(r'Exception return:[^\r\n]* previous exception (\d+)')

def analyze(trace: str) -> dict:
    accesses=Counter()
    for cpu, pc, kind in SEM.findall(trace):
        accesses[f'cpu{cpu}:pc0x{pc.lower()}:{kind.lower()}']+=1
    busy=Counter(f'TR{channel}@0x{int(addr,16):08x}' for channel,addr,_ in BUSY.findall(trace))
    writes=Counter()
    for addr,value in MU_WRITE.findall(trace):
        if int(addr,16) in (0x41022060,0x41022064,0x40220028,0x40220064):
            writes[f'0x{int(addr,16):08x}=0x{int(value,16):08x}']+=1
    entries=Counter(ENTRY.findall(trace))
    returns=Counter(RETURN.findall(trace))
    clears=writes['0x41022060=0x00000000']
    return {
        'a7_semaphore31': {
            'count_decrement_writes':accesses['cpu0:pc0x601e19cc:write'],
            'count_increment_writes':accesses['cpu0:pc0x601e17a4:write'],
            'successful_access_sites':dict(accesses)},
        'messaging_unit': {'busy_transmit_attempts':dict(busy), 'selected_writes':dict(writes)},
        'm4_irq22': {'entries':entries['38'], 'exception_returns':returns['38'],
                     'entries_per_zero_status_write':round(entries['38']/clears,4) if clears else None},
        'limitations':'Counts observed successful accesses and QEMU diagnostics only; does not infer values, guest success, or unseen events.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('logs',type=Path,nargs='+')
    p.add_argument('--json',type=Path)
    args=p.parse_args()
    content=json.dumps({str(log):analyze(log.read_text(errors='replace')) for log in args.logs},indent=2)+'\n'
    if args.json:
        args.json.parent.mkdir(parents=True,exist_ok=True)
        args.json.write_text(content)
    print(content,end='')

if __name__=='__main__':main()
