from __future__ import annotations

import re
from pathlib import Path

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")


class RunbookStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def search(self, query: str, limit: int = 3) -> list[dict[str, str | float]]:
        query_tokens = {token.lower() for token in TOKEN_RE.findall(query)}
        results: list[dict[str, str | float]] = []
        for path in self.root.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            tokens = {token.lower() for token in TOKEN_RE.findall(text)}
            overlap = len(query_tokens & tokens)
            if not overlap:
                continue
            score = overlap / max(len(query_tokens), 1)
            results.append(
                {
                    "title": text.splitlines()[0].lstrip("# "),
                    "path": path.name,
                    "score": round(score, 4),
                    "excerpt": text[:1_200],
                }
            )
        return sorted(results, key=lambda item: float(item["score"]), reverse=True)[:limit]
