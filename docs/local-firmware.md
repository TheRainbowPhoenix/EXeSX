# Local firmware run (native Linux, no Casio firmware in repository)

Only use firmware that you legally possess. EXeSX source and GitHub release assets are **firmware-free**. Do not upload OSUP.BIN or extracted ROMs to this public repository or CI.

1. Download `exesx-qemu-linux-x86_64.tar.gz` from [dev-native](https://github.com/TheRainbowPhoenix/EXeSX/releases/tag/dev-native) once a passing native release has been published. It targets Ubuntu 24.04 x86-64 and is not WebAssembly or an Android binary.
2. In the GitHub checkout, run `python3 scripts/prepare_osup.py /private/path/OSUP.BIN -o private/a7-firmware.elf`.
3. Extract the binary tarball and invoke `python3 scripts/run_firmware.py private/a7-firmware.elf --qemu /path/to/qemu-system-arm --seconds 3`.
4. Review `private/firmware-trace/report.json`, `qemu-instructions.log` and `qemu-console.txt`. The presence of ARM code in the trace **does not** establish a boot.

The native executable dynamically links against Linux system libraries. On other Linux distributions you may need a local build. A real graphical guest and touch I/O require more MMIO devices, M4 release, interrupts and a framebuffer; there is no usable phone/browser firmware runner yet.

The private directory is git-ignored. Preserve OSUP hashes and checksum-validated memory mapping, rather than relying on filename-derived offsets.
