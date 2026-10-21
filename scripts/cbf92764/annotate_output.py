"""Mirror a command's output into a GitHub notice when log archives are unavailable.

Use as a pipe with `set -o pipefail`: this filter never masks the producer's exit
status or removes any checks. Notices retain the exact script name and final trace.
"""
import sys

text = sys.stdin.read()
print(text, end='', flush=True)
detail = text[-7000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
title = sys.argv[1] if len(sys.argv) > 1 else 'Command output'
print(f'::notice title={title}::{detail}', flush=True)
