# Headless factory TEST MENU smoke test: native entry succeeds, factory items gated (2026-10-25)

This reproduces the owner's Windows observation **without proprietary firmware/guest RAM dumps in GitHub**. Owner original `OSUP.BIN` SHA256 is `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Native QEMU Linux artifact source `046058cd15332486ec2c3742de60b2abfb412b23`; source-derived synthetic eMMC and disposable 2GiB SD, both `snapshot=on`.

The read-only main-thread/worker test uses the original M4 electrical contacts `0x9C+0x90` and subsequently `0x93,0x93,0x94` only once A7 executes event wait `0x600108A8`. There are **no firmware, guest PC/RAM, RTOS event or mailbox injections**. Headless QMP samples the original shared IPC words on the same worker thread as framebuffer `pmemsave`.

## Independent original-ROM replay

Original A7 execution confirmed **all** of: version-dialog entry `0x60010868`, event wait `0x600108A8`, first-key check `0x60010910`, final-key acceptance `0x60010930`, native factory-menu entry `0x6003A878`, and synchronous service `0x400B` wrapper `0x60006240`.

The original M4/A7 shared slot at `0x2F02800C` was sampled as request **`0x0001400B`**, with original argument **2** at `0x2F028010` and slot state **`0x04010800`** at `0x2F028008`. Read-only host monitor samples do not modify M4/A7 guest state.

| Test item | Actual result |
| --- | --- |
| Original version dialog entered | PASS |
| Original keyboard event wait | PASS |
| First menu-key check | PASS |
| Final 0x94 accepted | PASS |
| Genuine A7 factory-menu code entry | PASS |
| Original 0x400B service invoked | PASS |
| Original 0x400B service completion / A7 `0x60006268` | **BLOCKED** |
| Original menu painter `0x60057668` | **BLOCKED** |
| Non-destructive DOWN-key navigation | **BLOCKED, NOT ISSUED** |
| Visible menu selection change | **BLOCKED, NOT CLAIMED** |

The QEMU process remained alive throughout; 14 real LCD frames were captured. Its RGB PPM SHA256 is `c3a539130372499fe3fda848fe70bf86444c0b04041734f7fc5fbd88ca4ae573`, the previously observed version popup, not a visible TEST MENU. This is an **uncompleted factory initialization IPC service**, **not a QEMU crash**. A separate first attempt did not reach the dialog within its bounded horizon; clean retries are needed because original firmware timing is experimental.

**No manual factory menu items were run:** without menu paint, pressing uncertain navigation/confirmation keys would be blind. In particular, no SD FORMAT, WRITE or MEDIA FULL TEST was sent, and none of the twelve SD factory tests is classified PASS or FAIL.

## Repeat on Windows using the latest successful CI artifact

~~~powershell
py -3 .\scripts\headless_factory_menu_checks.py `
    "C:\Casio\OSUP.BIN" `
    --qemu ".\qemu-system-arm.exe" `
    --profile ".\profiles\imx7ulp-early-boot.ini" `
    --output-dir ".\private\factory-menu-tests" `
    --seconds 85 --retries 3 --post-menu-seconds 8
~~~

Optionally add `--sd "C:\Casio\disposable-sd-2g.raw"` only for an actual disposable image. Original-media eMMC and SD are passed with `snapshot=on`.

The test reuses the floating keyboard's actual QEMU subprocess, original guest trace and **read-only** monitor. It waits for the original A7 menu-painter PC before permitting **one non-destructive DOWN (0x91) contact**; only then can a visible selection-change test be evaluated. It explicitly never issues OK/ENTER or a destructive factory test. It writes `private/factory-menu-tests/menu-checks-private.json`, alongside private guest console/trace and LCD frames.

Exit codes: **0** only if genuine menu entry, painter and safe DOWN test all ran; **2** if menu entry wasn't observed; **3** if native entry occurred but a service/painter prevented meaningful navigation. The check summary intentionally doesn't call timer stalls QEMU crashes.

**Next engineering step:** follow the original M4 RTOS event-object-7 service consumer and `0x400B(2)` completion/response envelope; after original A7 resumes at `0x60006268` and actually paints `0x60057668`, expand **non-destructive** factory checks on a disposable SD image. The 0x400B message must not be overwritten or unconditionally acknowledged.
