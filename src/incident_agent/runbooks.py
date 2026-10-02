from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")
CHECK_RE = re.compile(r"(?ms)^\d+\.\s+(.*?)(?=^\d+\.\s+|\Z)")


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class RunbookStore:
    """Retrieve citeable Runbook chunks with BM25; no vector service is needed."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _chunks(self) -> list[dict[str, str]]:
        chunks: list[dict[str, str]] = []
        for path in sorted(self.root.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ") if text.strip() else path.stem
            overview, _, checks = text.partition("Checks:")
            items = [match.group(1).strip() for match in CHECK_RE.finditer(checks)]
            if not items:
                items = [checks.strip() or text.strip()]
            for number, item in enumerate(items, start=1):
                chunks.append(
                    {
                        "title": title,
                        "path": path.name,
                        "citation": f"runbook:{path.name}#check-{number}",
                        "excerpt": f"{overview.strip()}\nCheck {number}: {item}",
                    }
                )
        return chunks

    def search(self, query: str, limit: int = 3) -> list[dict[str, str | float]]:
        terms = set(_tokens(query))
        chunks = self._chunks()
        if not terms or not chunks:
            return []
        counters = [Counter(_tokens(chunk["excerpt"])) for chunk in chunks]
        average_length = sum(sum(counter.values()) for counter in counters) / len(counters)
        document_frequency = Counter(
            term for counter in counters for term in counter if term in terms
        )
        results: list[dict[str, str | float]] = []
        for chunk, counter in zip(chunks, counters, strict=True):
            length = sum(counter.values())
            score = 0.0
            for term in terms:
                frequency = counter[term]
                if not frequency:
                    continue
                idf = math.log(
                    1 + (len(chunks) - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                score += idf * frequency * 2.2 / (
                    frequency + 1.2 * (0.25 + 0.75 * length / average_length)
                )
            if score > 0:
                results.append({**chunk, "score": round(score, 4)})
        return sorted(results, key=lambda item: (-float(item["score"]), str(item["citation"])))[:limit]
