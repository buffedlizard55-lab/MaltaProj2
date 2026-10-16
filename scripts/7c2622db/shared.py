"""Load the maintained shared engine read-only, without leaking module names.

The hub (session 7c2622db) publishes its own numbers from its own raw evidence, but it
uses the same parsing, no-vig and rating formulas as the rest of the repository so a
comparison between boards is meaningful. Nothing in scripts/f7279a54 is modified.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "scripts" / "f7279a54"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def core():
    """The shared pure engine (parsing, no-vig, VRS model, consensus, quote joining)."""
    cached = sys.modules.get("hub_core_7c2622db")
    if cached is not None:
        return cached
    return _load("hub_core_7c2622db", ENGINE / "core.py")


def collector():
    """The shared source collector, imported with `core` resolved to the shared engine."""
    shared_core = core()
    previous = sys.modules.get("core")
    sys.modules["core"] = shared_core
    try:
        return _load("hub_collect_7c2622db", ENGINE / "collect.py")
    finally:
        if previous is None:
            sys.modules.pop("core", None)
        else:
            sys.modules["core"] = previous
