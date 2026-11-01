# Private original-ROM ARM PATTERN end-to-end CI

Branch: `experiment/dy357-wlan-host-20261029`. The post-build
`private-arm-pattern-e2e` job in `.github/workflows/qemu.yml` runs only on
trusted pushes/workflow dispatches to this branch. It depends on the complete
`native-qemu` job, downloads **that same commit's Linux QEMU artifact** and
checks `SOURCE_COMMIT == GITHUB_SHA`. No historical emulator is used.

## Required private fixture (never commit this ZIP)

The owner-private ZIP is named
`EXeSX-DY357-private-ARM-pattern-fixture.zip`, with a single
`EXeSX-private-E2E-fixture/` top-level folder. It contains original
`OSUP.BIN` (SHA-256
`d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`),
`a7-bios-os.elf`, `emmc-data-extents.bin`, `reconstruct_media.py`,
`manifest.json`, `ci_e2e_arm_pattern.py`, original-A7/M4 decompilations,
and a previously captured golden PPM/PNG.

The eMMC reconstruction produces a 15,642,656,768-byte **sparse** raw image;
the SD image is a disposable sparse 2,147,483,648-byte image. They are
opened with QEMU `snapshot=on`. Only the allocated ~30 MB of eMMC
extents are included in the ZIP. Do not upload proprietary fixture bytes,
images, raw logs, ELF, eMMC or SD to GitHub source/release artifacts.

### Configure

1. Host the ZIP behind a private HTTPS address reachable by GitHub-hosted
   Ubuntu runners.
2. Create repository **Actions secrets**:
   - `EXESX_PRIVATE_E2E_URL`: private HTTPS ZIP URL.
   - `EXESX_PRIVATE_E2E_SHA256`: exact SHA-256 of the ZIP bytes.
   - `EXESX_PRIVATE_ASSET_TOKEN` (optional): Bearer token for the URL.
3. Push to this branch or dispatch the **Build and smoke-test EXeSX QEMU**
   workflow on this branch. If neither URL nor SHA is configured, the
   private test emits `PRIVATE E2E SKIPPED`; **a skipped run is not a
   firmware boot PASS**. One missing secret without the other fails.
4. Inspect the `private-arm-pattern-screen-<run-id>` artifact for
   `arm-pattern.png`, `factory-menu.png`, `selected-row.png` and the
   sanitized `result.json`. Artifact retention is 3 days.

**Visibility caution:** GitHub Actions artifacts from a public repository
may be downloadable by people with access to the workflow run. The uploaded
PNG images contain original LCD pixels. If these cannot be shared, move E2E
to a private repository/runner and remove screenshot upload. No original
ROMs/media or proprietary decompilation files are uploaded by this job.

## Acceptance criteria

The private runner uses `-accel tcg,thread=single` and the real M4 key
matrix contact file. It holds `0x9c,0x90` at cold start, releases after
four host seconds, and only sends `0x93,0x93,0x94` once the original A7
event wait has executed. Native checkpoints include genuine `0x60010930`
acceptance, TEST MENU entry `0x6003a878`, IPC `0x400B` return at
`0x60006268` and native menu painter at `0x60057668`.

The runner navigates to verified **row 3 ARM PATTERN AUTO CHECK** by real
physical DOWN/UP contacts, checking the inverse-highlighted LCD row
before ENTER. It reads the original 864x480 LCD from QMP after ENTER,
not a fabricated guest framebuffer. The rendered pattern **must** be exactly:

| RGB color | Pixels |
|---|---:|
| White `ffffff`, yellow `ffff00`, magenta `ff00ff` | 55,296 each |
| Red `ff0000`, cyan `00ffff`, green `00ff00`, blue `0000ff` | 55,296 each |
| Black `000000` | 27,648 |

Expected exact original P6 PPM SHA-256:
`5a046dd6d3080c97c0c2bff76f130d4e05199a2d4dbae59e6aa5eb741df4eaaf`.

The original **ARM PATTERN AUTO CHECK display is proven**, not a claim that
unrelated factory hardware diagnostics (WLAN, SD FORMAT, reset, etc.) pass.
The CI performs no destructive menu action or guest RAM/PC/event injection.

## Local verification

Extract the private ZIP, run `python3 reconstruct_media.py` in its
fixture directory, and execute `ci_e2e_arm_pattern.py` with this branch's
`scripts/` on `PYTHONPATH`, providing `--qemu`, `--profile`, `--elf`,
`--emmc`, `--sd`, and `--output` paths as shown in the private README.

Locally validated using the Linux GitHub Actions QEMU built 2026-10-29;
the original A7 menu entry and golden framebuffer checks passed. The
separate post-build private CI test only becomes meaningful once the
repository secrets point at this ZIP; synthetic CI green alone is not
an original-ROM test.
