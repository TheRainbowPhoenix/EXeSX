#!/usr/bin/env python3
"""Read-only cold-boot M4 keyboard/MU observer for an owner-private EXeSX image.

The only host input is an electrical contact-closure file. No GDB, firmware
patch, CPU register write, or synthesized IPC/event is used. This can prove
M4 typed key construction, not acceptance by the A7 factory-menu handler.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from drive_factory_menu import QMP, connect, choose_port, voltage


def read_words(qmp, address, count):
    text = qmp.hmp(f"xp /{count}wx 0x{address:x}")
    words = []
    for line in text.splitlines():
        if ':' in line:
            words.extend(int(x, 16) for x in re.findall(
                r'0x[0-9a-fA-F]+', line.split(':', 1)[1]))
    return words[:count]


def run(args):
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for path in [args.qemu, args.elf, args.emmc, args.profile] + ([args.sd] if args.sd else []):
        if not path.is_file():
            raise FileNotFoundError(f"Missing local original/test-kit input: {path}")
    contacts = out / 'closed-contact.txt'
    voltage(contacts, 0)
    if args.startup_chord:
        contacts.write_text(args.startup_chord + '\n', encoding='ascii')
    env = os.environ.copy()
    env.update(
        EXESX_MEMORY_PROFILE=str(args.profile.resolve()),
        EXESX_EXPERIMENTAL_M4_BOOT='1', EXESX_EXPERIMENTAL_MU_IRQ='1',
        EXESX_EXPERIMENTAL_LPIT1_IRQ='1',
        EXESX_EXPERIMENTAL_LPTMR_IRQ='1' if args.lptmr_irq else '0',
        EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS='1',
        EXESX_EXPERIMENTAL_M4_PORT_IRQ='1',
        EXESX_EXPERIMENTAL_M4_TPM0_IRQ='1',
        EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ='48',
        EXESX_DIAGNOSTIC_A7_TPM6_KHZ='32',
        EXESX_EXPERIMENTAL_LCD='1', EXESX_EXPERIMENTAL_DMA1_M2M='1',
        EXESX_USDHC1_EMMC='1', EXESX_USDHC0_SD='1' if args.sd else '0',
        EXESX_USDHC0_SD_DETECT_GPIO='1' if args.sd else '0',
        EXESX_I2C4B_REGISTER_MIRROR='1', EXESX_I2C40_REGISTER_MIRROR='1',
        EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES='1',
        EXESX_GPIOA_INPUT_MASK='0x808c6008',
        EXESX_GPIOB_INPUT_MASK='0xc8',
        EXESX_M4_KEY_MATRIX_FILE=str(contacts),
    )
    if args.mailbox_trace:
        env['EXESX_TRACE_MU_MAILBOX'] = '1'
    if (args.qemu.parent / 'lib').is_dir():
        env['LD_LIBRARY_PATH'] = (str(args.qemu.parent / 'lib') + os.pathsep +
                                  env.get('LD_LIBRARY_PATH', ''))
    port = choose_port()
    cmd = [str(args.qemu.resolve()), '-machine', 'exesx', '-m', '64M',
           '-accel', 'tcg', '-display', 'none', '-serial', 'none',
           '-monitor', 'none', '-no-reboot',
           '-drive', f'if=none,id=exesx-emmc,file={args.emmc.resolve()},format=raw,snapshot=on',
           '-device', f'loader,file={args.elf.resolve()},cpu-num=0',
           '-S', '-qmp', f'tcp:127.0.0.1:{port},server=on,wait=off']
    if args.sd:
        cmd += ['-drive', f'if=none,id=exesx-sd,file={args.sd.resolve()},format=raw,snapshot=on']
    if args.mailbox_trace:
        # qemu_log() requires an active log sink; guest_errors creates verbose
        # private MMIO traces, so explicitly warn and never publish the file.
        cmd += ['-d', 'guest_errors', '-D', str(out / 'qemu-mu-private.log')]
    report = dict(configuration=dict(lptmr_irq=args.lptmr_irq,
                                     sd_attached=bool(args.sd),
                                     startup_chord=args.startup_chord,
                                     poll_seconds=args.poll),
                  physical_contacts=[], observations=[],
                  m4_keydown_codes=[], mailbox_counts={},
                  a7_key_acceptance_proven=False,
                  factory_menu_execution_proven=False)
    start = time.monotonic()
    def press_keys():
        remaining = args.contact_at - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(remaining)
        if args.startup_chord:
            voltage(contacts, 0)
            report['physical_contacts'].append(dict(t=round(time.monotonic()-start, 4),
                                                     event='startup_chord_released'))
        for keycode in (0x93, 0x93, 0x94):
            voltage(contacts, keycode)
            report['physical_contacts'].append(dict(t=round(time.monotonic()-start, 4),
                                                     event='contact_closed', key=hex(keycode)))
            time.sleep(args.hold)
            voltage(contacts, 0)
            report['physical_contacts'].append(dict(t=round(time.monotonic()-start, 4),
                                                     event='contact_released', key=hex(keycode)))
            time.sleep(args.gap)
    with (out / 'qemu-console-private.log').open('w') as console:
        proc = subprocess.Popen(cmd, env=env, stdout=console,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            with connect(port, proc) as sock:
                qmp = QMP(sock)
                qmp.execute('cont')
                worker = threading.Thread(target=press_keys, daemon=True)
                worker.start()
                while time.monotonic() - start < args.seconds and proc.poll() is None:
                    t = round(time.monotonic() - start, 4)
                    sample = dict(t=t,
                        m4_queue=read_words(qmp, 0x1ffea34c, 5),
                        m4_debounce=read_words(qmp, 0x1ffea320, 1),
                        a7_startup_selector=read_words(qmp, 0x6232e33c, 1),
                        a7_boot_mode=read_words(qmp, 0x20007810, 1),
                        m4_power_state=read_words(qmp, 0x1ffe9b0c, 2),
                        shared_ipc=read_words(qmp, 0x2f028000, 6))
                    queue = sample['m4_queue']
                    if len(queue) >= 3 and queue[0] == 0x00010002 and queue[2] in (0x93, 0x94):
                        report['m4_keydown_codes'].append(dict(t=t, code=hex(queue[2])))
                    report['observations'].append(sample)
                    time.sleep(args.poll)
                worker.join(timeout=1)
        finally:
            proc.kill()
            proc.wait()
            voltage(contacts, 0)
    if args.mailbox_trace:
        trace = (out / 'qemu-mu-private.log').read_text(errors='replace')
        for prefix in ('EXeSX MU TX M4 TR0', 'EXeSX MU RX A7 RR0',
                       'EXeSX MU TX M4 TR3', 'EXeSX MU RX A7 RR3',
                       'accepted=0'):
            report['mailbox_counts'][prefix] = trace.count(prefix)
    (out / 'report-private.json').write_text(json.dumps(report, indent=2) + '\n')
    codes = [entry['code'] for entry in report['m4_keydown_codes']]
    print('Observed original M4 type2/subtype1 keycodes:', sorted(set(codes)))
    print('MU hardware transactions:', report['mailbox_counts'])
    print('A7 acceptance / factory menu NOT proven by this read-only probe')
    print('Private report:', out / 'report-private.json')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('qemu', 'elf', 'emmc', 'profile', 'output-dir'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--sd', type=Path, help='Disposable SD image; always snapshot=on')
    p.add_argument('--seconds', type=float, default=15)
    p.add_argument('--contact-at', type=float, default=7)
    p.add_argument('--poll', type=float, default=.06)
    p.add_argument('--hold', type=float, default=.15)
    p.add_argument('--gap', type=float, default=.08)
    # 0x9c+0x90 is checked by the original M4 *before* A7 startup,\n    # unlike the two original A7 three-key chords.\n    p.add_argument('--startup-chord', choices=('0x80,0x95,0x92', '0x80,0x90,0x96', '0x9c,0x90'),
                   default='0x80,0x95,0x92')
    p.add_argument('--no-startup-chord', action='store_true')
    p.add_argument('--lptmr-irq', action='store_true')
    p.add_argument('--mailbox-trace', action='store_true')
    a = p.parse_args()
    if a.no_startup_chord:
        a.startup_chord = None
    if a.seconds <= 0 or a.poll <= 0 or a.contact_at < 0 or a.hold <= 0 or a.gap < 0:
        p.error('Seconds/poll/hold must be positive; contact-at/gap nonnegative')
    run(a)

if __name__ == '__main__':
    main()
