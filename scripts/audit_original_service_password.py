#!/usr/bin/env python3
"""Audit original A7 service-unlock input records without changing guest state.

Input is five *observed* FUN_6004752C event records from a private
read-only debugger/guest trace: [{"type":"0x17","code":"0x91"}, ...].
The caller distinguishes SERVICE gate mode1 from protected-operation mode0.
This does not construct A7 events or force any factory authorization.
"""
import argparse
import json
from pathlib import Path


def number(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("expected an observed numeric event type/code")


def audit(events, mode):
    if mode not in (0, 1):
        raise ValueError("original password mode is 0 or 1")
    if len(events) != 5:
        raise ValueError("original firmware consumes exactly five events")
    expected = ((0x91, 0x93, 0x93, 0x92, 0x94),
                (0x91, 0x93, 0x90, 0x92, 0x94))[mode]
    records = []
    for pos, event in enumerate(events):
        event_type = number(event["type"])
        code = number(event.get("code", 0))
        # Original FUN_6004752C accepts event 0x12 in *either* mode
        # only for the fifth event. For key-down 0x17, mode0 permits
        # both code0x93 and code0x93 at indices 1 and 2.
        valid = (event_type == 0x12 and pos == 4) or (
            event_type == 0x17 and code == expected[pos])
        records.append({"position": pos+1, "type": hex(event_type),
                        "code": hex(code), "accepted": valid})
    return {"mode": mode, "accepted": all(r["accepted"] for r in records),
            "first_rejected_position": next(
                (r["position"] for r in records if not r["accepted"]), None),
            "observations": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_json", type=Path)
    parser.add_argument("--mode", choices=(0, 1), type=int, default=1)
    args = parser.parse_args()
    observations = json.loads(args.events_json.read_text(encoding="utf-8"))
    if isinstance(observations, dict):
        observations = observations["observed"]
    print(json.dumps(audit(observations, args.mode), indent=2))


if __name__ == "__main__":
    main()
