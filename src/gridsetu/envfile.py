"""Minimal .env loader (no dependency). Reads KEY=VALUE lines from the project's .env and
the current directory's .env; values already set in the environment win."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env(paths: list[Path] | None = None) -> list[str]:
    loaded = []
    for p in paths or [ROOT / ".env", Path.cwd() / ".env"]:
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if val and val[0] in "'\"" and val[-1:] == val[0]:
                val = val[1:-1]
            elif " #" in val:                      # trailing comment on an unquoted value
                val = val.split(" #", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = val
                loaded.append(key)
    return loaded
