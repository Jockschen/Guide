from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Iterable

import numpy as np


DIMENSIONS = 256


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str, max_chars: int = 520) -> list[str]:
    text = clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    parts = re.split(r"(?<=[。！？；])", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= max_chars:
            current += part
            continue
        if current:
            chunks.append(current.strip())
        current = part
    if current:
        chunks.append(current.strip())
    return chunks


def tokens(text: str) -> list[str]:
    text = clean_text(text).lower()
    latin = re.findall(r"[a-z0-9]+", text)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = [text[i : i + 2] for i in range(max(0, len(text) - 1)) if all("\u4e00" <= c <= "\u9fff" for c in text[i : i + 2])]
    return latin + chinese + bigrams


def hash_embedding(text: str) -> list[float]:
    vector = np.zeros(DIMENSIONS, dtype=np.float32)
    for token in tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(digest, "little") % DIMENSIONS
        vector[idx] += 1.0
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return vector.round(6).tolist()


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    av = list(a)
    bv = list(b)
    if not av or not bv or len(av) != len(bv):
        return 0.0
    dot = sum(x * y for x, y in zip(av, bv))
    an = math.sqrt(sum(x * x for x in av))
    bn = math.sqrt(sum(y * y for y in bv))
    if an == 0 or bn == 0:
        return 0.0
    return dot / (an * bn)


def keyword_score(query: str, text: str) -> float:
    q_tokens = set(tokens(query))
    if not q_tokens:
        return 0.0
    t_tokens = set(tokens(text))
    hits = q_tokens & t_tokens
    return len(hits) / len(q_tokens)
