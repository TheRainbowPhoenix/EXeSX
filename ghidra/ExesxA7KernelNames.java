// @category EXeSX
// SHA-guarded names for the private Casio XD-SX9850 A7 BIOS.
// Post-script arg: absolute path to reverse/a7_kernel_named_sites.tsv.
// ATTENTION: eForce uC3 source files provide API terminology, NOT proven
// binary identity. Only rename known entry points; sites get bookmarks.
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.SourceType;

public class ExesxA7KernelNames extends GhidraScript {
    private static final long BIOS_START = 0x60000000L;
    private static final int BIOS_LENGTH = 2447360;
    private static final String BIOS_SHA =
        "eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66";

    private Address at(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private void verifyFirmware() throws Exception {
        if (!"ARM".equals(currentProgram.getLanguage().getProcessor().toString())
                || currentProgram.getLanguage().isBigEndian()) {
            throw new IllegalStateException("Expected ARM little-endian A7 firmware");
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        Memory memory = currentProgram.getMemory();
        byte[] buf = new byte[4096];
        int pos = 0;
        while (pos < BIOS_LENGTH) {
            int count = Math.min(buf.length, BIOS_LENGTH - pos);
            if (memory.getBytes(at(BIOS_START + pos), buf, 0, count) != count) {
                throw new IllegalStateException("Incomplete A7 BIOS memory at " + pos);
            }
            digest.update(buf, 0, count);
            pos += count;
        }
        StringBuilder got = new StringBuilder();
        for (byte b : digest.digest()) got.append(String.format("%02x", b & 255));
        if (!BIOS_SHA.equals(got.toString())) {
            throw new IllegalStateException("Unknown A7 BIOS sha256 " + got +
                "; refusing to apply XD-SX9850 address names");
        }
    }

    public void run() throws Exception {
        if (getScriptArgs().length != 1) {
            throw new IllegalArgumentException("Pass absolute named-sites TSV path");
        }
        File table = new File(getScriptArgs()[0]);
        if (!table.isAbsolute() || !table.isFile()) {
            throw new IllegalArgumentException("Expected existing absolute TSV file");
        }
        verifyFirmware();
        int functions = 0, sites = 0;
        try (BufferedReader reader = new BufferedReader(new FileReader(table, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            if (!"address\tname\tkind\tconfidence\tevidence".equals(line)) {
                throw new IllegalStateException("Unexpected labels TSV schema");
            }
            while ((line = reader.readLine()) != null && !monitor.isCancelled()) {
                if (line.isBlank()) continue;
                String[] cols = line.split("\t", -1);
                if (cols.length != 5 || !cols[0].startsWith("0x") ||
                    !cols[1].matches("[A-Za-z_][A-Za-z0-9_]*") ||
                    !("site".equals(cols[2]) || "function".equals(cols[2]))) {
                    throw new IllegalStateException("Invalid label row: " + line);
                }
                Address address = at(Long.parseUnsignedLong(cols[0].substring(2), 16));
                if (!currentProgram.getMemory().contains(address)) {
                    throw new IllegalStateException("A7 code not mapped at " + address);
                }
                String evidence = cols[3] + " confidence: " + cols[4] +
                    " (names from observed firmware; uC3 API terminology only)";
                if ("function".equals(cols[2])) {
                    if (getInstructionAt(address) == null) disassemble(address);
                    Function fn = getFunctionAt(address);
                    if (fn == null && getFunctionContaining(address) == null)
                        fn = createFunction(address, cols[1]);
                    if (fn != null && (fn.getName().startsWith("FUN_") ||
                            fn.getName().startsWith("sub_"))) {
                        fn.setName(cols[1], SourceType.USER_DEFINED);
                    }
                    functions++;
                } else {
                    sites++;
                }
                // A bookmark never replaces an analyst's own function boundary.
                currentProgram.getBookmarkManager().setBookmark(address,
                    "Analysis", "EXeSX kernel symbol",
                    cols[1] + " — " + evidence);
                try {
                    createLabel(address, cols[1], false);
                } catch (Exception conflict) {
                    println("Label already exists or conflicts at " + address + ": " + conflict);
                }
            }
        }
        println("EXeSX SHA-matched A7 annotations: " + functions +
                " function entry candidates, " + sites + " instruction sites.");
    }
}
