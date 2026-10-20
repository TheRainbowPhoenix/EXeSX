// @category EXeSX
// Hash-gated M4 Cortex-M/Thumb I2C annotations and XREF TSV export.
// Run after importing private/m4-firmware.elf (never commit that ELF).
import java.io.*;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ExesxI2CXrefs extends GhidraScript {
    private final long[] functions = {
        0x1ffd2e50L, 0x1ffd3270L, 0x1ffd5712L,
        0x1ffd6c48L, 0x1ffd6cb6L, 0x1ffd6cf8L, 0x1ffd6d52L,
        0x1ffd6da0L, 0x1ffd6e28L, 0x1ffd6f4cL, 0x1ffd6f7eL,
        0x1ffd6fa6L, 0x1ffd6fd8L
    };
    private final String[] names = {
        "M4_Kernel_DispatchRegisteredIRQCallbacks",
        "M4_Kernel_CommonInterruptDispatch", "M4_MU_ReceiveAndGIP_IRQHandler",
        "M4_LPI2C_ClearState", "M4_LPI2C_CheckErrors",
        "M4_LPI2C_SendStart", "M4_LPI2C_WaitComplete",
        "M4_LPI2C_TransmitBytes", "M4_LPI2C_ReceiveBytes",
        "M4_I2C4B_ReadByte", "M4_I2C4B_WriteTwoBytes",
        "M4_I2C6B_ReadByte_Candidate", "M4_I2C6B_WriteTwoBytes_Candidate"
    };
    private final long[] pool = {
        0x1ffd6f34L, 0x1ffd6f38L, 0x1ffd6f3cL, 0x1ffd6f48L
    };
    private final String[] poolNames = {
        "LPI2C2_MSR_ADDR", "LPI2C2_MCR_ADDR",
        "LPI2C2_MFSR_ADDR", "LPI2C2_MIER_ADDR"
    };
    private final long[] expected = {
        0x41035014L, 0x41035010L, 0x4103505cL, 0x41035018L
    };
    private Address at(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }
    private String fingerprint() throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        Memory mem = currentProgram.getMemory();
        byte[] bytes = new byte[4096];
        Address start = at(0x1ffd0000L);
        int remaining = 0x14f70, pos = 0;
        while (remaining > 0) {
            int length = Math.min(remaining, bytes.length);
            if (mem.getBytes(start.add(pos), bytes, 0, length) != length) {
                throw new IOException("Truncated imported M4 image at " + pos);
            }
            md.update(bytes, 0, length);
            pos += length;
            remaining -= length;
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : md.digest()) hex.append(String.format("%02x", b & 255));
        return hex.toString();
    }
    private String clean(String text) {
        return text.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ');
    }
    private void refs(PrintWriter out, String group, long target, String name) {
        Address address = at(target);
        ReferenceIterator items = currentProgram.getReferenceManager().getReferencesTo(address);
        int count = 0;
        while (items.hasNext() && !monitor.isCancelled()) {
            Reference ref = items.next();
            Address from = ref.getFromAddress();
            Function owner = getFunctionContaining(from);
            Instruction instruction = getInstructionAt(from);
            out.println(group + "\t" + name + "\t" + address + "\t" + from + "\t" +
                        (owner == null ? "?" : clean(owner.getName())) + "\t" +
                        clean(ref.getReferenceType().toString()) + "\t" +
                        (instruction == null ? "?" : clean(instruction.toString())));
            count++;
        }
        println(name + ": " + count + " Ghidra references");
    }
    public void run() throws Exception {
        if (getScriptArgs().length != 1) {
            throw new IllegalArgumentException("Pass one absolute destination TSV path");
        }
        if (!"ARM".equals(currentProgram.getLanguage().getProcessor().toString()) ||
            currentProgram.getLanguage().isBigEndian()) {
            throw new IOException("Require ARM little endian/Cortex language");
        }
        if (!fingerprint().equals("25f95e3a5cfe2a898b2110d874075e6da5b288c706c03bc5a051a1f8c8e54fb0")) {
            throw new IOException("M4 fingerprint mismatch; refuse labels");
        }
        Register thumb = currentProgram.getProgramContext().getRegister("TMode");
        if (thumb != null) {
            try {
                currentProgram.getProgramContext().setValue(
                    thumb, at(0x1ffd2e50L), at(0x1ffd75ffL), BigInteger.ONE);
            } catch (Exception e) {
                println("Existing instruction context prevented TMode override: " + e);
            }
        } else {
            println("WARNING: TMode not available; select ARM:LE:32:Cortex");
        }
        for (int i = 0; i < functions.length; i++) {
            if (monitor.isCancelled()) break;
            Address address = at(functions[i]);
            if (getInstructionAt(address) == null) disassemble(address);
            Function f = getFunctionAt(address);
            if (f == null) f = createFunction(address, names[i]);
            if (f != null) {
                f.setName(names[i], SourceType.USER_DEFINED);
            } else {
                createLabel(address, names[i], true);
                println("Function not made at " + address);
            }
            currentProgram.getBookmarkManager().setBookmark(
                address, "Analysis", "EXeSX I2C", "SHA-verified M4 I2C static anchor");
        }
        Memory mem = currentProgram.getMemory();
        for (int i = 0; i < pool.length; i++) {
            Address address = at(pool[i]);
            if (Integer.toUnsignedLong(mem.getInt(address)) != expected[i]) {
                throw new IOException("Unexpected literal at " + address);
            }
            createLabel(address, poolNames[i], true);
            currentProgram.getBookmarkManager().setBookmark(
                address, "Analysis", "EXeSX I2C", "Physical register " + Long.toHexString(expected[i]));
        }
        File dest = new File(getScriptArgs()[0]);
        if (!dest.isAbsolute()) throw new IOException("Absolute TSV output path required");
        if (dest.getParentFile() != null) dest.getParentFile().mkdirs();
        try (PrintWriter out = new PrintWriter(new OutputStreamWriter(
                new FileOutputStream(dest), StandardCharsets.UTF_8))) {
            out.println("group\tlabel\ttarget\tfrom\tcaller_function\treference_type\tinstruction");
            for (int i = 0; i < functions.length; i++) refs(out, "function", functions[i], names[i]);
            for (int i = 0; i < pool.length; i++) refs(out, "literal", pool[i], poolNames[i]);
        }
        println("Saved private Ghidra XREFs to " + dest);
    }
}
