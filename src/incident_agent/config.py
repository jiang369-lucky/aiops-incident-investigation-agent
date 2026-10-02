from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: str) -> Path:
    raw = Path(os.getenv(name, default))
    return raw if raw.is_absolute() else project_root() / raw


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "AGENT_DATABASE_URL",
            "postgresql://incident:incident_dev_password@127.0.0.1:55432/incident_agent",
        )
    )
    raw_data_path: Path = field(
        default_factory=lambda: _path_from_env("AGENT_RAW_DATA_PATH", "data/raw")
    )
    skills_path: Path = field(default_factory=lambda: _path_from_env("AGENT_SKILLS_PATH", "skills"))
    runbooks_path: Path = field(
        default_factory=lambda: _path_from_env("AGENT_RUNBOOKS_PATH", "knowledge/runbooks")
    )
    artifacts_path: Path = field(
        default_factory=lambda: _path_from_env("AGENT_ARTIFACTS_PATH", "artifacts")
    )
    model_mode: str = field(default_factory=lambda: os.getenv("AGENT_MODEL_MODE", "heuristic"))
    tool_transport: str = field(default_factory=lambda: os.getenv("AGENT_TOOL_TRANSPORT", "local"))
    model_base_url: str = field(
        default_factory=lambda: os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    )
    model_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    model_name: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "gpt-4.1-mini"))
