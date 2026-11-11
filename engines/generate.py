"""UUIDs (v4, v7), passwords and passphrases from `secrets` for `eselsbruecke_generate`.

The Desktop half uses `crypto.getRandomValues` with the same rules; tests check shapes and entropy,
not values. The passphrase words are the EFF short wordlist 1 (1,296 words, CC BY 3.0 US,
`data/eff_short_wordlist_1.txt`), loaded at import.
"""
from __future__ import annotations

import math
import secrets
import time
import uuid
from pathlib import Path

LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
SYMBOLS = "!#$%&*+-=?@^_~"
AMBIGUOUS = set("Il1O0o")


class GenerateError(ValueError):
    pass


def _load_words() -> list[str]:
    path = Path(__file__).resolve().parents[1] / "data" / "eff_short_wordlist_1.txt"
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            words.append(parts[1])
    return words


WORDS = _load_words()


def uuid4() -> str:
    return str(uuid.uuid4())


def uuid7(ms: int | None = None) -> str:
    """RFC 9562 UUID v7: 48-bit Unix milliseconds, version 7, 74 random bits."""
    ms = int(time.time() * 1000) if ms is None else int(ms)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


def uuids(version: int = 4, count: int = 1) -> list[str]:
    count = max(1, min(int(count or 1), 100))
    if version not in (4, 7):
        raise GenerateError("version must be 4 or 7")
    return [uuid4() if version == 4 else uuid7() for _ in range(count)]


def password(length: int = 20, lower: bool = True, upper: bool = True, digits: bool = True,
             symbols: bool = True, avoid_ambiguous: bool = False) -> dict:
    length = int(length)
    if not 4 <= length <= 256:
        raise GenerateError("length must be between 4 and 256")
    sets = [s for s, on in ((LOWER, lower), (UPPER, upper), (DIGITS, digits), (SYMBOLS, symbols)) if on]
    if avoid_ambiguous:
        sets = ["".join(c for c in s if c not in AMBIGUOUS) for s in sets]
    if not sets:
        raise GenerateError("switch on at least one character set")
    pool = "".join(sets)
    while True:  # one character from each chosen set, rejection sampling keeps it uniform
        chars = [secrets.choice(pool) for _ in range(length)]
        if length < len(sets) or all(any(c in s for c in chars) for s in sets):
            break
    return {"password": "".join(chars), "entropy_bits": round(length * math.log2(len(pool)), 1),
            "pool_size": len(pool)}


def passphrase(words: int = 6, separator: str = "-", capitalize: bool = False, number: bool = False) -> dict:
    words = int(words)
    if not 3 <= words <= 20:
        raise GenerateError("words must be between 3 and 20")
    if len(separator) > 3:
        raise GenerateError("separator is at most 3 characters")
    picked = [secrets.choice(WORDS) for _ in range(words)]
    if capitalize:
        picked = [w.capitalize() for w in picked]
    bits = words * math.log2(len(WORDS))
    if number:
        picked[secrets.randbelow(words)] += str(secrets.randbelow(10))
        bits += math.log2(10) + math.log2(words)
    return {"passphrase": separator.join(picked), "entropy_bits": round(bits, 1), "wordlist": "EFF short 1",
            "wordlist_size": len(WORDS)}
