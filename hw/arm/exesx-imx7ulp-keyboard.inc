/* Original DY357 M4 keyboard matrix — opt-in physical contact closure.
 *
 * The unchanged original M4 firmware drives one GPIO row low, samples
 * eight input columns, debounces and sends its own IPC keyboard events.
 * A user-owned file encodes comma-separated simultaneous closed contacts (logical key IDs);
 * this file never supplies an A7 key event or pre-decoded IPC message.
 *
 * Verified original M4 row table @0x1FFD0DA8 (9 x 12 bytes), column
 * table @0x1FFD0D48 (8 x 12 bytes) and key map @0x1FFD0E14
 * (9 x 8 little-endian uint16s). Validated against owner-held OSUP.
 * Geometry is an original firmware lookup, NOT an assertion about the
 * keyboard's physical layout or human-facing key legends.
 */
typedef struct EXeSXM4KeyContact {
    uint16_t keycode;
    uint8_t row, column;
} EXeSXM4KeyContact;

static const EXeSXM4KeyContact exesx_m4_key_contacts[] = {
    { 0x93, 8, 7 }, /* original ROM key table: A21 row / A31 column */
    { 0x94, 6, 6 }, /* original ROM: A17 row / A23 column */
    { 0x95, 5, 6 }, /* original ROM: A16 row / A23 column */
    { 0x80, 0, 0 }, /* original ROM: B2 row  / B6 column  */
    { 0x90, 7, 6 }, /* original ROM: A20 row / A23 column */
    { 0x91, 6, 7 }, /* original ROM: A17 row / A31 column; DOWN key */
    { 0x92, 7, 7 }, /* original ROM: A20 row / A31 column */
    { 0x96, 8, 4 }, /* original ROM: A21 row / A18 column */
};

static const uint8_t exesx_m4_row_bank[] = {
    1, 0, 0, 0, 0, 0, 0, 0, 0
};
static const uint8_t exesx_m4_row_bit[] = {
    2, 9, 2, 11, 15, 16, 17, 20, 21
};
static const uint8_t exesx_m4_col_bank[] = {
    1, 0, 0, 0, 0, 0, 0, 0
};
static const uint8_t exesx_m4_col_bit[] = {
    6, 3, 13, 14, 18, 19, 23, 31
};

/* The real M4 row-drive subroutine 0x1FFD8412 selects the row via
 * GPIO.PCOR (only on its currently configured port). We track that
 * physical output write, never infer a row from a host keycode.
 */
static void exesx_m4_keyboard_row_drive(EXeSXState *board,
                                        uint64_t gpio_base, uint32_t bits)
{
    unsigned row;
    if (!board || !g_getenv("EXESX_M4_KEY_MATRIX_FILE")) {
        return;
    }
    for (row = 0; row < G_N_ELEMENTS(exesx_m4_row_bit); row++) {
        uint64_t base = exesx_m4_row_bank[row] ?
                        UINT64_C(0x4100f040) : UINT64_C(0x4100f000);
        if (base == gpio_base &&
            bits == (UINT32_C(1) << exesx_m4_row_bit[row])) {
            board->m4_keyboard_row = row;
            return;
        }
    }
}

/* No key unless a private file was explicitly provided. A missing or
 * malformed file releases the key. Poll by guest virtual time so the
 * GPIO contact is deterministic relative to M4 timer scheduling.
 */
/* Each bit is one simultaneous physical contact in exesx_m4_key_contacts.
 * A single code file remains backwards-compatible. Unknown or malformed
 * codes release ALL keys rather than synthesizing an input.
 */
static uint16_t exesx_m4_keyboard_code(EXeSXState *board)
{
    const char *path = g_getenv("EXESX_M4_KEY_MATRIX_FILE");
    gchar *contents = NULL;
    gchar **tokens;
    uint16_t contacts = 0;
    unsigned n;
    int64_t now;
    if (!board || !path || !*path) {
        return 0;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now >= board->m4_keyboard_next_poll_ns) {
        board->m4_keyboard_code = 0;
        if (g_file_get_contents(path, &contents, NULL, NULL)) {
            tokens = g_strsplit(g_strstrip(contents), ",", -1);
            for (n = 0; tokens[n]; n++) {
                char *token = g_strstrip(tokens[n]);
                char *end;
                uint64_t code;
                unsigned i;
                if (!*token || n >= G_N_ELEMENTS(exesx_m4_key_contacts)) {
                    contacts = 0;
                    break;
                }
                code = g_ascii_strtoull(token, &end, 0);
                if (end == token || *end != '\0' || code > 0xffff) {
                    contacts = 0;
                    break;
                }
                for (i = 0; i < G_N_ELEMENTS(exesx_m4_key_contacts); i++) {
                    if (exesx_m4_key_contacts[i].keycode == code) {
                        contacts |= (uint16_t)(1U << i);
                        break;
                    }
                }
                if (i == G_N_ELEMENTS(exesx_m4_key_contacts)) {
                    contacts = 0;
                    break;
                }
            }
            g_strfreev(tokens);
            g_free(contents);
        }
        board->m4_keyboard_code = contacts;
        /* Real electrical contacts, refreshed once per millisecond of
         * guest virtual time; no original firmware event is injected. */
        board->m4_keyboard_next_poll_ns = now + INT64_C(1000000);
    }
    return board->m4_keyboard_code;
}

/* M4 GPIO.PDIR reflects the actual wired voltage. A closed key only
 * grounds the sampled column when the original firmware has selected
 * the matching output row (PDDR=output, PDOR=low). Guest-written
 * columns configured as outputs retain their own PDOR/PDDR priority.
 */
static uint32_t exesx_m4_keyboard_column_levels(EXeSXProfileWindow *w,
                                                  uint32_t external_inputs)
{
    EXeSXState *b = w->board;
    uint16_t contacts;
    unsigned i;
    if (!b || !(contacts = exesx_m4_keyboard_code(b))) {
        return external_inputs;
    }
    for (i = 0; i < G_N_ELEMENTS(exesx_m4_key_contacts); i++) {
        const EXeSXM4KeyContact *k = &exesx_m4_key_contacts[i];
        EXeSXProfileWindow *row_gpio;
        uint32_t row_mask, iomux_pin;
        uint64_t col_base;
        /*
         * A physical closed key joins a column to its row only while
         * the guest configures that row as a GPIO output AND selects
         * its IOMUX function. Original M4 FUN_1FFD8412 writes
         * IOMUXC0[pin + 32*bank] = 0x20100 for a selected row,
         * and writes zero to de-select it. PDOR/PDDR alone persist
         * after de-selection and led to erroneous keycode 0xC5
         * (column 7, wrong row) in the original-ROM QEMU trace.
         * Consult the serialized MMIO register, not last-PCOR state.
         */
        if (!(contacts & (1U << i))) {
            continue;
        }
        row_gpio = exesx_m4_row_bank[k->row] ? b->m4_gpio_b : b->m4_gpio_a;
        if (!row_gpio) {
            continue;
        }
        row_mask = UINT32_C(1) << exesx_m4_row_bit[k->row];
        iomux_pin = exesx_m4_row_bit[k->row] +
                    (exesx_m4_row_bank[k->row] ? 32 : 0);
        if (!b->m4_iomuxc0 ||
            b->m4_iomuxc0->regfile[iomux_pin] != UINT32_C(0x20100) ||
            !(row_gpio->regfile[0x14 / 4] & row_mask) ||
            (row_gpio->regfile[0] & row_mask)) {
            continue; /* row is unmuxed, not output, or not low */
        }
        col_base = exesx_m4_col_bank[k->column] ?
                   UINT64_C(0x4100f040) : UINT64_C(0x4100f000);
        if (w->base == col_base) {
            external_inputs &= ~(UINT32_C(1) << exesx_m4_col_bit[k->column]);
        }
    }
    return external_inputs;
}
