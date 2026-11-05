"""Deterministic configurable chunking: paragraph-accumulation with hard cap."""
from __future__ import annotations

import re

TARGET_CHARS = 320
HARD_CAP = 800
MIN_CHARS = 24

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(content: str, target_chars: int = TARGET_CHARS) -> list[dict]:
    """Returns [{index, start, end, text}] with offsets into the original content."""
    paragraphs: list[tuple[int, str]] = []
    offset = 0
    for para in re.split(r"(\n\s*\n)", content):
        if not para:
            offset += 0
            continue
        if re.fullmatch(r"\n\s*\n", para):
            offset += len(para)
            continue
        paragraphs.append((offset, para))
        offset += len(para)

    chunks: list[dict] = []
    buf: list[str] = []
    buf_start: int | None = None
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_start, buf_len
        text = "\n\n".join(buf).strip()
        if len(text) >= MIN_CHARS:
            start = content.find(text, buf_start or 0)
            # fall back to exact buf_start when content was whitespace-trimmed
            if start < 0:
                start = buf_start or 0
            chunks.append({
                "index": len(chunks),
                "start": start,
                "end": start + len(text),
                "text": text,
            })
        buf, buf_start, buf_len = [], None, 0

    for p_start, para in paragraphs:
        if len(para) > HARD_CAP:
            flush()
            # split long paragraph by sentences into target-sized pieces
            piece: list[str] = []
            piece_len = 0
            cursor = p_start
            for sentence in _SENTENCE_RE.split(para):
                if piece_len + len(sentence) > target_chars and piece:
                    text = " ".join(piece).strip()
                    chunks.append({"index": len(chunks), "start": cursor,
                                   "end": cursor + len(text), "text": text})
                    cursor = cursor + len(text) + 1
                    piece, piece_len = [], 0
                piece.append(sentence)
                piece_len += len(sentence)
            if piece:
                text = " ".join(piece).strip()
                chunks.append({"index": len(chunks), "start": cursor,
                               "end": cursor + len(text), "text": text})
            buf_start = None
        else:
            if buf_start is None:
                buf_start = p_start
            if buf_len + len(para) > target_chars and buf:
                flush()
                buf_start = p_start
            buf.append(para.strip())
            buf_len += len(para)
    flush()
    return chunks


def split_sentences(text: str) -> list[dict]:
    """Sentence split with offsets — used for claims and strict repair evidence."""
    out: list[dict] = []
    cursor = 0
    for sentence in _SENTENCE_RE.split(text):
        start = text.find(sentence, cursor)
        if start < 0:
            start = cursor
        cursor = start + len(sentence)
        s = sentence.strip()
        if s:
            out.append({"text": s, "start": start, "end": start + len(s)})
    return out


def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)
