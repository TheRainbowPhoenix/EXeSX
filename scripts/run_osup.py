#!/usr/bin/env python3
"""One-command, PRIVATE DY357 OSUP -> synthetic eMMC -> native EXeSX run.

No Casio bytes are distributed. Synthetic media contains only available,
checksum-validated OSUP components at source-confirmed user-area LBAs and
source PVOS metadata at boot1 LBA0/32. This is NOT physical installed flash.

Usage: python3 scripts/run_osup.py OSUPD.bin --qemu build/qemu-system-arm
Optional: --seconds 15 --lcd-trace --profile profiles/imx7ulp-early-boot.ini
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_osup
import analyze_osup_install_layout as layout


def prepare(osup, dest):
    data = osup.read_bytes()
    sections, sha = prepare_osup.extract(osup)
    info = layout.analyze(data)
    dest.mkdir(parents=True, exist_ok=True)
    elf = dest / "a7-bios-os.elf"
    media = dest / "source-derived-synthetic-emmc.raw"
    elf.write_bytes(prepare_osup.elf32(sections))
    # QEMU's eMMC raw device convention is boot0:4MiB, boot1:4MiB, user:rest.
    pvos = info["pvos"]["osup_offset"]
    with media.open("wb") as f:
        f.truncate(layout.QEMU_SYNTHETIC_SIZE)
        for lba in (0, 32):
            f.seek(layout.BOOT_SIZE + lba * layout.SECTOR)
            f.write(data[pvos:pvos + layout.SECTOR])
        user_base = 2 * layout.BOOT_SIZE
        for c in info["components"]:
            src = c["header_osup_offset"]
            lba = sum(prev["declared_sectors"] for prev in info["components"]
                      if prev["header_osup_offset"] < src)
            available = max(0, min(c["declared_bytes"], len(data) - 2 - src))
            # Source-derived bytes only. F resources are incomplete.
            f.seek(user_base + lba * layout.SECTOR)
            f.write(data[src:src + available])
    manifest = {
        "input_sha256": sha,
        "elf": str(elf),
        "media": str(media),
        "actual_media": False,
        "boot1_pvos_lbas": [0, 32],
        "user_components": [
            {"type":c["type"], "user_lba":sum(p["declared_sectors"]
                for p in info["components"]
                if p["header_osup_offset"] < c["header_osup_offset"]),
             "source_offset":c["header_osup_offset"],
             "declared_sectors":c["declared_sectors"]}
            for c in info["components"]],
        "caveats": [
            "SYNTHETIC sparse QEMU media, not actual installed device",
            "OSUP resource F payload is incomplete",
            "boot1 sectors beyond PVOS remain zero",
            "0xB0000000 LCD model is experimental; TE timing/wiring not authenticated",
        ],
    }
    (dest/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return elf, media, manifest


def launch(qemu, elf, media, profile, dest, seconds, lcd_trace, plugin, dma1_m2m=False, handoff_probe=False, gpiob3_high=False, ipc1808_probe=False, gpioa_input_mask=0, gpiob_input_mask=None, ipc0804_probe=False):
    env = os.environ.copy()
    # Explicitly labeled temporary LCD-bus address sink for runs without
    # an implemented display model. It does NOT acknowledge any LCD
    # commands, generate TE, or constitute the physical device.
    diagnostic_profile = dest / "diagnostic-memory-profile.ini"
    profile_text = profile.read_text()
    if "[diagnostic-flexbus-lcd]" not in profile_text and (
            "base=0xb0000000" not in profile_text.lower()):
        profile_text += ("\n[diagnostic-flexbus-lcd]\nkind=exesx-lcd\n"
                         "base=0xb0000000\nsize=0x1000\n")
    diagnostic_profile.write_text(profile_text)
    env.update({
        "EXESX_MEMORY_PROFILE":str(diagnostic_profile.resolve()),
        "EXESX_EXPERIMENTAL_M4_BOOT":"1",
        "EXESX_EXPERIMENTAL_MU_IRQ":"1",
        "EXESX_EXPERIMENTAL_LPIT1_IRQ":"1",
        "EXESX_I2C4B_REGISTER_MIRROR":"1",
        "EXESX_I2C40_REGISTER_MIRROR":"1",
        "EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES":"1",
        "EXESX_GPIOB_INPUT_MASK":hex(gpiob_input_mask) if gpiob_input_mask is not None else ("0x88" if gpiob3_high else "0x80"),
        "EXESX_GPIOA_INPUT_MASK":hex(gpioa_input_mask),
        "EXESX_USDHC1_EMMC":"1",
        "EXESX_EXPERIMENTAL_LCD":"1",
        "EXESX_EXPERIMENTAL_DMA1_M2M":"1" if dma1_m2m else "0",
        "EXESX_LCD_SCREENSHOT":str((dest/"lcd-screenshot.ppm").resolve()),
    })
    lib = qemu.resolve().parent/"lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH","")
    screenshot_file = dest/"lcd-screenshot.ppm"
    previous_screenshot_mtime = (screenshot_file.stat().st_mtime_ns
                                if screenshot_file.is_file() else None)
    log = dest/"qemu-trace-private.log"
    stdout_log = dest/"qemu-console-private.log"
    cmd = [str(qemu.resolve()), "-machine","exesx","-m","64M",
           "-accel","tcg","-display","none","-serial","none",
           "-monitor","none","-no-reboot",
           "-drive",f"if=none,id=exesx-emmc,file={media},format=raw,snapshot=on",
           "-device",f"loader,file={elf},cpu-num=0",
           "-trace","enable=sdhci_send_command",
           "-d","guest_errors,unimp" + (",plugin" if lcd_trace else ""),
           "-D",str(log)]
    if lcd_trace:
        if not plugin or not plugin.is_file():
            raise FileNotFoundError("LCD tracing requires --plugin exesx-memtrace.so")
        cmd += ["-plugin", f"{plugin.resolve()},virtual_only=1,values=1,"
                "max=25000,range=0xb0000000:0xb0000004,"
                "range=0x400f0004:0x400f000c"]
    if ipc0804_probe:
        from probe_ipc_0804 import run_probe as trace_input_ready
        print("PRIVATE M4 GPIO/input-ready IPC 0x0804 diagnostic; A/B masks",
              env["EXESX_GPIOA_INPUT_MASK"], env["EXESX_GPIOB_INPUT_MASK"], flush=True)
        report = trace_input_ready(cmd, env, seconds, dest)
        print("IPC 0x0804 metadata:", dest / "ipc0804-summary.json",
              "events:", len(report["events"]), flush=True)
        return
    if ipc1808_probe:
        from probe_ipc_1808 import run_probe as trace_ipc
        print("PRIVATE A7/M4 IPC 0x1808 diagnostic; GPIOB input mask",
              env["EXESX_GPIOB_INPUT_MASK"], flush=True)
        report = trace_ipc(cmd, env, seconds, dest)
        print("IPC 0x1808 metadata:", dest / "ipc1808-summary.json",
              "events:", len(report["events"]), flush=True)
        return
    if handoff_probe:
        from probe_postdma_handoff import run_probe
        print("Private A7 GDB post-DMA probe; no firmware or logs uploaded.", flush=True)
        report = run_probe(cmd, env, seconds, dest)
        print("Probe results:", dest / "handoff-summary.json",
              "milestones hit:", len(report["hits"]), flush=True)
        return
    print("Running owner-held firmware in synthetic QEMU media; no input uploaded.",
          flush=True)
    print("Experimental LCD device; 60Hz TE timing and 864px GRAM are hypotheses.",flush=True)
    print("Screenshot:",dest/"lcd-screenshot.ppm",flush=True)
    print("Private log:",log,flush=True)
    with stdout_log.open("w") as out:
        try:
            subprocess.run(cmd,env=env,stdout=out,stderr=subprocess.STDOUT,
                           timeout=seconds,check=False)
        except subprocess.TimeoutExpired:
            pass
    if lcd_trace:
        from decode_lcd_bus_trace import decode_lines
        metadata = decode_lines(log.read_text(errors="replace").splitlines())
        (dest/"lcd-metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
        print("LCD observed:",metadata["command_count"],"commands;",
              metadata["pixel_samples"],"pixel samples")
    if screenshot_file.is_file() and (previous_screenshot_mtime is None or
                                     screenshot_file.stat().st_mtime_ns != previous_screenshot_mtime):
        from summarize_lcd_screenshot import summarize
        statistics = summarize(screenshot_file)
        (dest/"lcd-summary.json").write_text(json.dumps(statistics, indent=2)+"\n")
        print("LCD raw framebuffer:", statistics["width"], "x", statistics["height"],
              "nonwhite pixels:", statistics["nonwhite_pixels"],
              "bbox:", statistics["nonwhite_bbox_xyxy"], flush=True)
        print("A nonwhite framebuffer does NOT alone establish OS entry or accurate orientation.")
    print("Finished bounded run. Full QEMU output stays private.")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("osup",type=Path)
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile",type=Path,
                    default=Path("profiles/imx7ulp-early-boot.ini"))
    ap.add_argument("--output-dir",type=Path,default=Path("private/osup-run"))
    ap.add_argument("--seconds",type=float,default=15)
    ap.add_argument("--lcd-trace",action="store_true")
    ap.add_argument("--plugin",type=Path)
    ap.add_argument("--prepare-only",action="store_true")
    ap.add_argument("--gpioa-input-mask", type=lambda value: int(value,0), default=0,
                    help="Research-only external M4 GPIOA input pin-high mask; no authenticated board wiring")
    ap.add_argument("--gpiob-input-mask", type=lambda value: int(value,0), default=None,
                    help="Research-only override for external M4 GPIOB input pins (e.g. 0xc8); supersedes --gpiob3-high")
    ap.add_argument("--gpiob3-high", action="store_true",
                    help="Diagnostic only: drive unverified M4 GPIOB PDIR bit3 HIGH (0x88 vs default 0x80)")
    ap.add_argument("--ipc0804-probe", action="store_true",
                    help="Private read-only original M4 IPC 0x0804 GPIO input-ready producer trace")
    ap.add_argument("--ipc1808-probe", action="store_true",
                    help="Read-only A7/M4 shared-slot response provenance trace for service 0x1808")
    ap.add_argument("--handoff-probe",action="store_true",
                    help="Private read-only A7 callback/DMA/OS milestone GDB probe")
    ap.add_argument("--dma1-m2m",action="store_true",
                    help="Opt in to experimental RAM-to-RAM DMA1 transfers")
    a=ap.parse_args()
    if not a.osup.is_file(): ap.error("OSUP input file not found")
    if a.seconds <= 0: ap.error("--seconds must be positive")
    if not 0 <= a.gpioa_input_mask <= 0xffffffff or (a.gpiob_input_mask is not None and not 0 <= a.gpiob_input_mask <= 0xffffffff):
        ap.error("GPIO input masks must fit in unsigned 32-bit register")
    if sum((a.handoff_probe, a.ipc1808_probe, a.ipc0804_probe)) > 1:
        ap.error("Use only one GDB probe option at a time")
    elf,media,manifest=prepare(a.osup,a.output_dir)
    print(json.dumps(manifest,indent=2))
    if not a.prepare_only:
        root = Path(__file__).resolve().parents[1]
        if not a.qemu.is_file():
            if a.qemu != Path("build/qemu-system-arm"):
                ap.error("Custom --qemu executable not found")
            print("Native EXeSX QEMU missing; building pinned v10.1.0 now.",
                  flush=True)
            subprocess.run(["bash", str(root/"scripts"/"build.sh")],
                           cwd=root, check=True)
        if not a.profile.is_file(): ap.error("QEMU memory profile missing")
        if a.lcd_trace and not a.plugin:
            a.plugin = Path("build/exesx-memtrace.so")
        if a.lcd_trace and not a.plugin.is_file():
            if a.plugin != Path("build/exesx-memtrace.so"):
                ap.error("Custom --plugin path not found")
            subprocess.run(["bash", str(root/"scripts"/"build_memtrace.sh")],
                           cwd=root, check=True)
        launch(a.qemu,elf,media,a.profile,a.output_dir,a.seconds,
               a.lcd_trace,a.plugin,a.dma1_m2m,a.handoff_probe,
               a.gpiob3_high,a.ipc1808_probe,a.gpioa_input_mask,a.gpiob_input_mask,a.ipc0804_probe)


if __name__=="__main__":
    main()
