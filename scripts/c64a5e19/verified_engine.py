"""Reuse the maintained strict engine without leaking generic module names into other tools.

The imported modules are private instances. We do not modify f7279a54's files or outputs.
"""
import importlib.util
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / 'f7279a54'


def load_engine(filename):
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    previous = sys.modules.get('core')
    path = sys.path[:]
    try:
        core = load('every_match_strict_core', ENGINE / 'core.py')
        sys.modules['core'] = core
        return load('every_match_strict_' + filename.removesuffix('.py'), ENGINE / filename)
    finally:
        sys.path[:] = path
        if previous is None:
            sys.modules.pop('core', None)
        else:
            sys.modules['core'] = previous
