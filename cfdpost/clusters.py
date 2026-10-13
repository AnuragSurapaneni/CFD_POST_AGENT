"""Project-local persistence for reusable cluster launch settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RequestError

REGISTRY = Path(".cfdpost/clusters.json")


def save_cluster(name: str, settings: dict[str, Any]) -> Path:
    if not name or any(character in name for character in "\r\n"):
        raise RequestError("Cluster profile needs a non-empty single-line name.")
    modules = settings.get("modules", [])
    if not isinstance(modules, list) or any(not isinstance(item, str) for item in modules):
        raise RequestError("Cluster modules must be a list of module names.")
    path = REGISTRY.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    profiles[name] = settings
    path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
    return path


def load_cluster(name: str) -> dict[str, Any]:
    path = REGISTRY.resolve()
    if not path.exists():
        raise RequestError(f"No cluster profiles saved in {path}.")
    profiles = json.loads(path.read_text(encoding="utf-8"))
    if name not in profiles:
        raise RequestError(f"Cluster profile {name!r} is not registered. Available: {sorted(profiles)}")
    return profiles[name]
