# Boot trace annotations applied to XD-SX9850.0

The connected Ghidra program `/EXWRom/XD-SX9850/XD-SX9850.0` was annotated
and saved on 23 October 2026 using the owner's local XD-SX9850 OSUP.
No firmware, raw instruction bytes, RAM dumps, or private traces are included.

The source container passes the existing header/payload checksums and has
SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
Extracted BIOS SHA256 is
`eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66`.
At each of **90 A7 sites and 16 M4 source-image sites**, 32 bytes read through
the Ghidra memory API exactly matched the local source. This is a per-site
identity check, not a hash of the whole Ghidra database or a new boot run.

Applied changes:

- 43 anonymous functions renamed; four existing analyst names retained as
  primary names, with new descriptive aliases. The scheduler candidate
  `0x601797A8` falls inside the existing `0x601797A0` function and received
  only a site label. No function was split or recreated.
- All 90 A7 sites have descriptive labels and repeatable evidence comments.
- 16 M4 source locations have labels and relocation comments; their runtime
  IPL addresses were not renamed or overwritten.
- 10 boot-state data labels and comments distinguish timer ID/pending,
  callback object/pointer/status, shared permission and IPC request/response.
- 12 focused function prototypes remove spurious paired-register return
  types in the delay, callback, IPC result, DMA and semaphore helpers.

The timer chain is now readable as allocation, start, WFI wait, completion,
stop and release. Static decompilation reveals twelve timer slots at
`0x622CC2D4`, each 16 bytes: state, callback, reload and countdown. Slots
3 through 11 use a shared tick and delay rounding `(argument*1000+24999)/25000`;
the allocator returns one-based IDs. Channel0 reload defaults to 300000
cycles; dedicated slots multiply delay arguments by 12000. This arithmetic
is consistent with a nominal 12 MHz timer and millisecond API arguments,
but the physical LPIT input clock has not been authenticated. The current
QEMU model explicitly uses an uncalibrated 1 MHz timebase. This is a useful
clock-calibration question, not evidence for changing the model by itself.
This supports the earlier observed timer ID 6 without identifying a new
hardware blocker or asserting that its callback ran in this session.

The static dispatch chain is now resolved end to end:
`A7_LPIT1_InitializeTimerService` registers `A7_LPIT1_InterruptHandler`
on uC3 interrupt 57 (GIC SPI25). The ISR calls
`A7_LPIT1_DispatchSharedTimerTick`, which acknowledges LPIT1 MSR bit0,
decrements active slots3..11 and calls the saved function when a countdown
reaches zero. Timer ID6's callback is the previously traced
`A7_TimerDelay_CompletionCallback`; the prior live LR `0x6001AE68` agrees
with this dispatch. Dedicated channels1..3 serve software slots0..2.
The LCD routine `0x601B40CC` now exposes its DMA wait, 864x480 window,
GPIOF13 high/low wait and halfword/packed-word pixel loops by name.

The service path now reads as `A7_Startup_InitializeServiceState` →
`A7_Startup_RetryIPC1808Service` → `A7_Startup_PollIPC1808WithDelay` →
`A7_IPC1808_ReadGPIOB3Predicate` → `A7_IPC_CallService`. Application response
and transport status remain distinct. The GPIOB3 physical default remains
unverified, and the registered callback dispatcher is not assumed to be an
OS launcher merely because a prior RAM snapshot held `0x60400000`.

## M4 source versus runtime address

The current database's IPL code at runtime `0x1FFDBCDE` belongs to a different
static function (`0x1FFDBBC4`, an MMC read path). The GPIOB3 sampling helper
observed there during the prior boot trace comes from **OSUP offset
`0x001F957E`**, mapped in this database at **`0x600B937E`**. Its source-image
label is `M4_IPC1808_SampleGPIOB3FiveTimes_SourceImage`. Matching source
bytes was essential: applying this runtime name to the IPL would mislabel
unrelated code. The same source/destination distinction is recorded for
the fifteen existing M4 peripheral names.

## Reproduction and audit

`reverse/ghidra_boot_annotation_audit.json` records names, addresses, checks,
preserved functions, prototypes and limitations without source bytes.
The existing `ghidra/ExesxA7KernelNames.java` can consume each of these TSVs
as its one absolute-path argument after its full BIOS SHA check:

- `reverse/a7_kernel_named_sites.tsv` (existing trace findings)
- `reverse/boot_trace_named_sites.tsv` (timer/startup/IPC/DMA additions)
- `reverse/m4_boot_source_sites.tsv` (source-image site labels only)

The Java script applies function names/labels/bookmarks; data labels,
prototypes and repeatable comments are detailed in the JSON audit. This
session used native Ghidra MCP operations because inline script execution
is disabled on the bridge. No bridge settings were changed. The supplied
Java script was not executed as part of this annotation pass.
