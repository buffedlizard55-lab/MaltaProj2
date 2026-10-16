"""Load the maintained shared engine read-only (session 6484426f).

This session publishes its own numbers from its own raw evidence, but it uses the same
parsing, no-vig and official-rating formulas as the rest of the repository so that a
comparison between boards is meaningful. Nothing in ``scripts/f7279a54`` is modified.
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
    """The shared pure engine (parsing, no-vig, VRS model, consensus)."""
    cached = sys.modules.get("desk_core_6484426f")
    if cached is not None:
        return cached
    return _load("desk_core_6484426f", ENGINE / "core.py")
