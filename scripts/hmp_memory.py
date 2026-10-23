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
