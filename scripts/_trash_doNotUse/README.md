# _trash_doNotUse — historical, NON-AUTHENTIC factory menu experiments

**Do not run these scripts for original-ROM acceptance tests.** They are
retained for historical investigation only, outside active scripts paths.

- `force_factory_menu_experimental.py`: redirects guest A7 PC through GDB.
- `probe_synthetic_factory_menu.py`: synthesizes original A7 event-return
  records rather than using physical M4 keyboard contacts.

Both approaches invalidate a claim that the original firmware independently
accepted the startup chord, physical keyboard sequence, or menu. Use
`scripts/ci_e2e_arm_pattern.py` for owner-private CI E2E regression, or
`scripts/drive_physical_menu_qmp.py` for genuine matrix input research.

The existing eMMC/media, WLAN, display and kernel probe tools in `scripts/`
are deliberately **not** relocated: they are referenced by build, tests or
other analysis and have not been proven unused.
