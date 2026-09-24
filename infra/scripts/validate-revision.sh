#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

python3 - "$ROOT/Revision.md" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
lines = text.splitlines()
errors = []

if sum(line.startswith('# ') for line in lines) != 1:
    errors.append('expected exactly one H1')

parts = ''.join(chr(65 + i) for i in range(22))
begin = re.findall(r'<!-- BEGIN PART ([A-V]) -->', text)
end = re.findall(r'<!-- END PART ([A-V]) -->', text)
if begin != list(parts):
    errors.append('BEGIN PART order or inventory is invalid')
if end != list(parts):
    errors.append('END PART order or inventory is invalid')

fences = sum(line.startswith('```') for line in lines)
if fences % 2:
    errors.append('unbalanced Markdown fences')

for marker in ('APPEND-MARKER', 'END FINAL CHECK'):
    if marker in text:
        errors.append(f'legacy marker remains: {marker}')

for heading in ('## Aktueller Status (Momentaufnahme)', '## Aktuelles Finding-Register'):
    if heading not in text:
        errors.append(f'missing required section: {heading}')

patterns = {
    'jwt': r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
    'pem': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github': r'gh[pousr]_[A-Za-z0-9_]{20,}',
    'google': r'AIza[0-9A-Za-z_-]{20,}',
}
for name, pattern in patterns.items():
    count = len(re.findall(pattern, text))
    if count:
        errors.append(f'{name} pattern matches: {count}')

if errors:
    for error in errors:
        print(f'ERROR: {error}')
    raise SystemExit(1)

print(f'Revision validation passed: {len(lines)} lines, {len(begin)} parts')
PY

git diff --check -- Revision.md
