"""Parse HMP physical memory dumps; query them over QMP without console input."""
import json
import re
import socket
import subprocess
import tempfile
import time


def memory_words(output, start, count):
    clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output).replace('\r', '\n')
    words = {}
    for match in re.finditer(r'(?mi)^([0-9a-f]{8,16}):[ \t]*([^\n]*)', clean):
        address = int(match.group(1), 16)
        for index, word in enumerate(re.findall(r'0x([0-9a-fA-F]{1,8})\b', match.group(2))):
            words[address + 4 * index] = int(word, 16)
    missing = [start + 4 * i for i in range(count) if start + 4 * i not in words]
    if missing:
        raise AssertionError(f'Missing HMP word at {missing[0]:#x}: {clean[:1500]} ... {clean[-1500:]}')
    return [words[start + 4 * i] for i in range(count)]


def qmp_memory_words(cmd, env, start, count, delay=2.0):
    """Read guest RAM via loopback QMP, not Windows HMP stdio.

    QEMU's board registration can emit more diagnostics than the Windows PIPE
    buffer holds. Do not attach an unread PIPE to stdout/stderr: a blocked
    diagnostic write prevents the same QEMU process servicing QMP commands.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    qcmd = list(cmd)
    if "-monitor" in qcmd:
        i = qcmd.index("-monitor")
        del qcmd[i:i + 2]
    qcmd += ["-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off"]

    # Disk-backed temporary files cannot block QEMU even if it produces
    # megabytes of early-boot diagnostics before answering qmp_capabilities.
    with tempfile.TemporaryFile(mode="w+b") as diagnostic:
        proc = subprocess.Popen(
            qcmd, env=env, stdin=subprocess.DEVNULL,
            stdout=diagnostic, stderr=subprocess.STDOUT)
        try:
            def recent_diagnostics():
                diagnostic.flush()
                diagnostic.seek(0, 2)
                end = diagnostic.tell()
                diagnostic.seek(max(0, end - 3000))
                return diagnostic.read().decode(errors="replace")

            deadline = time.monotonic() + 20
            conn = None
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError(
                        "QEMU exited before QMP ready: " + recent_diagnostics())
                try:
                    conn = socket.create_connection(("127.0.0.1", port), timeout=1)
                    break
                except OSError:
                    time.sleep(.1)
            if conn is None:
                raise AssertionError(
                    "QEMU QMP listener never became ready: " + recent_diagnostics())

            with conn:
                conn.settimeout(15)
                with conn.makefile("rb") as reader:
                    line = reader.readline()
                    if not line:
                        raise AssertionError(
                            "QEMU closed QMP before greeting: " + recent_diagnostics())
                    greeting = json.loads(line)
                    if "QMP" not in greeting:
                        raise AssertionError(f"Missing QMP greeting: {greeting}")

                    def execute(name, arguments=None):
                        payload = {"execute": name}
                        if arguments is not None:
                            payload["arguments"] = arguments
                        conn.sendall((json.dumps(payload) + "\n").encode())
                        while True:
                            line = reader.readline()
                            if not line:
                                raise AssertionError(
                                    f"QMP {name} disconnected: " + recent_diagnostics())
                            item = json.loads(line)
                            if "event" in item:
                                continue
                            if "error" in item:
                                raise AssertionError(f"QMP {name} failed: {item['error']}")
                            if "return" in item:
                                return item["return"]

                    execute("qmp_capabilities")
                    time.sleep(delay)
                    execute("stop")
                    dump = execute("human-monitor-command", {
                        "command-line": f"xp /{count}wx 0x{start:08x}"})
                    return memory_words(dump, start, count)
        except (OSError, TimeoutError) as error:
            raise AssertionError(
                f"QMP read failed ({error}): " + recent_diagnostics()) from error
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
