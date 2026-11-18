"""Section-aware chunking for annual reports (and any plain text).

10-K filings are organised as "PART I / Item 1. Business / Item 1A. Risk
Factors / Item 7. MD&A ..." — each chunk remembers which Item it came from.
That label is (a) prepended to the text that gets embedded, which noticeably
improves retrieval for questions like "what are the main risks", and (b) shown
to the user as a citation.
"""
import re
from dataclasses import dataclass, asdict

ITEM_RE = re.compile(r"^item\s+(\d{1,2}[a-c]?)\s*[.:\-–—]?\s*(.{0,120})$", re.I)
PART_RE = re.compile(r"^part\s+(i{1,3}|iv)\b", re.I)

CHUNK_CHARS = 1400
OVERLAP_CHARS = 200


@dataclass
class Chunk:
    id: int
    text: str
    section: str

    def to_dict(self):
        return asdict(self)


def _section_label(line: str) -> str | None:
    m = ITEM_RE.match(line.strip())
    if not m:
        return None
    title = m.group(2).strip().rstrip(".")
    # Skip table-of-contents rows like "Item 7. Management's Discussion ... 23"
    if re.search(r"\s\d{1,3}$", title):
        return None
    return f"Item {m.group(1).upper()}" + (f". {title}" if title else "")


def split_into_sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = [("Cover / Overview", [])]
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        label = _section_label(line) if len(line) < 160 else None
        if label:
            sections.append((label, []))
        elif PART_RE.match(line) and len(line) < 60:
            continue
        else:
            sections[-1][1].append(line)
    return [(s, lines) for s, lines in sections if lines]


def _pack(lines: list[str], size: int, overlap: int) -> list[str]:
    """Greedy-pack lines into ~size char windows with ~overlap char carry-over.
    Over-long single lines are hard-split on sentence/space boundaries."""
    pieces: list[str] = []
    for line in lines:
        while len(line) > size:
            cut = max(line.rfind(". ", 0, size), line.rfind(" ", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            pieces.append(line[:cut].strip())
            line = line[cut:].strip()
        if line:
            pieces.append(line)

    chunks, current, length = [], [], 0
    for piece in pieces:
        if current and length + len(piece) + 1 > size:
            chunks.append("\n".join(current))
            carry, carry_len = [], 0
            for prev in reversed(current):
                if carry_len + len(prev) > overlap:
                    break
                carry.insert(0, prev)
                carry_len += len(prev) + 1
            current, length = carry, carry_len
        current.append(piece)
        length += len(piece) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def chunk_document(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, lines in split_into_sections(text):
        for body in _pack(lines, size, overlap):
            if len(body) >= 40:  # drop crumbs like lone headings
                chunks.append(Chunk(id=len(chunks), text=body, section=section))
    return chunks
