"""Annotate a failed command's exact output; the shell returns its original status.

Only invoked on failure so GitHub's ten-annotations-per-step limit cannot hide
later scripts' errors behind successful command output.
"""
import sys

text = sys.stdin.read()
print(text, end='', flush=True)
detail = text[-7000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
title = sys.argv[1] if len(sys.argv) > 1 else 'Command output'
print(f'::error title={title}::{detail}', flush=True)
