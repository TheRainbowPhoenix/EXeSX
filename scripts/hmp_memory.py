"""Parse HMP xp word dumps, including Windows console control sequences."""
import re


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
    """Query guest RAM using QMP, avoiding Windows HMP stdio line-editor echoes.

    Replaces -monitor stdio with a loopback QMP socket. No MSYS2 dependency.
    QMP human-monitor-command executes XP atomically and returns plain text.
    """
    import json
    import socket
    import subprocess
    import time

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    qcmd = list(cmd)
    try:
        i = qcmd.index("-monitor")
        del qcmd[i:i + 2]
    except ValueError:
        pass
    qcmd += ["-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off"]
    proc = subprocess.Popen(qcmd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 20
        conn = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = proc.communicate()[0].decode(errors="replace")
                raise AssertionError("QEMU exited before QMP ready: " + output[-2000:])
            try:
                conn = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except OSError:
                time.sleep(.1)
        if conn is None:
            raise AssertionError("QEMU QMP listener never became ready")
        with conn:
            conn.settimeout(15)
            reader = conn.makefile("rb")
            greeting = json.loads(reader.readline())
            if "QMP" not in greeting:
                raise AssertionError(f"Missing QMP greeting: {greeting}")
            def execute(name, arguments=None):
                payload = {"execute": name}
                if arguments is not None:
                    payload["arguments"] = arguments
                conn.sendall((json.dumps(payload) + "\n").encode())
                while True:
                    item = json.loads(reader.readline())
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
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=10)
