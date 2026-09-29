from __future__ import annotations

import re
from dataclasses import dataclass

LOG_RE = re.compile(
    r"^(?P<source>\S+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(?P<pid>\d+)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\s+"
    r"(?P<logger>\S+)\s*(?P<message>.*)$"
)
REQUEST_RE = re.compile(r"\breq-[0-9a-f-]{36}\b", re.IGNORECASE)
INSTANCE_TAG_RE = re.compile(r"\[instance:\s*(?P<id>[0-9a-f-]{36})\]", re.IGNORECASE)
SERVER_PATH_RE = re.compile(r"/servers/(?P<id>[0-9a-f-]{36})\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedLine:
    timestamp: str | None
    source: str
    level: str
    logger: str
    request_id: str | None
    instance_id: str | None
    message: str
    raw: str


def parse_openstack_line(line: str) -> ParsedLine:
    raw = line.rstrip("\r\n")
    match = LOG_RE.match(raw)
    request = REQUEST_RE.search(raw)
    instance = INSTANCE_TAG_RE.search(raw) or SERVER_PATH_RE.search(raw)
    if not match:
        return ParsedLine(
            timestamp=None,
            source="unknown",
            level="UNKNOWN",
            logger="unknown",
            request_id=request.group(0).lower() if request else None,
            instance_id=instance.group("id").lower() if instance else None,
            message=raw,
            raw=raw,
        )
    values = match.groupdict()
    level = "WARNING" if values["level"] == "WARN" else values["level"]
    return ParsedLine(
        timestamp=f"{values['date']}T{values['time']}",
        source=values["source"],
        level=level,
        logger=values["logger"],
        request_id=request.group(0).lower() if request else None,
        instance_id=instance.group("id").lower() if instance else None,
        message=values["message"],
        raw=raw,
    )
