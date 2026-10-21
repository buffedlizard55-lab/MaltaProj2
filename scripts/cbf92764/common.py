"""Shared, isolated imports; never leaks a generic `core` into other session tests."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/cbf92764'
SITE = ROOT / 'dashboard'

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

CORE = load_module('cbf_odds_core', ROOT / 'scripts/f7279a54/core.py')

def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def now():
    return datetime.now(timezone.utc)

def strict_join(fixture, quote):
    info = CORE.match_quote(fixture, quote)
    return info if info and not info.get('rejected') else None

RULES = load_module("cbf_kalshi_rules", ROOT / "scripts/69e4c06a/kalshi.py")
