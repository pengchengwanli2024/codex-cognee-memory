#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""Check public source boundaries without reading user configuration or secrets."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '__pycache__', '.test-tmp'}
DISALLOWED = {'.cognee', '.cognee-plugin', '.cognee-workflow', '.harness2',
              '.harness2-preflight', 'verification', 'node_modules', '.venv'}
PATTERNS = {
    'private_home_path': re.compile(rb'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private_volume_path': re.compile(rb'/Volumes/[A-Za-z0-9_.-]+/'),
    'concrete_api_credential': re.compile(rb'\b(?:sk-(?:proj-)?|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{20,}'),
    'private_key_material': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'private_development_thread_id': re.compile(rb'\b01a[0-9a-f]{5}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
}


def main():
    findings = []
    files = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if path.is_symlink():
            findings.append({'rule': 'symlink_in_release', 'path': str(relative)})
            continue
        if not path.is_file():
            continue
        files.append(path)
        if any(part in DISALLOWED for part in relative.parts) or path.name == '.env' or path.suffix in ('.key', '.pem', '.p12', '.pfx', '.jsonl', '.log', '.pyc'):
            findings.append({'rule': 'runtime_or_secret_file', 'path': str(relative)})
        data = path.read_bytes()
        for name, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.append({'rule': name, 'path': str(relative)})
        if path.suffix == '.py':
            try:
                ast.parse(data, filename=str(relative))
            except (SyntaxError, UnicodeDecodeError):
                findings.append({'rule': 'python_syntax', 'path': str(relative)})

    manifest = json.loads((ROOT / 'plugins/cognee/.codex-plugin/plugin.json').read_text())
    marketplace = json.loads((ROOT / '.agents/plugins/marketplace.json').read_text())
    hooks = json.loads((ROOT / 'plugins/cognee/hooks.json').read_text())['hooks']
    expected_events = {'SessionStart', 'UserPromptSubmit', 'Stop', 'PreCompact', 'SessionEnd'}
    if set(hooks) != expected_events:
        findings.append({'rule': 'automatic_events', 'path': 'plugins/cognee/hooks.json'})
    for event, entries in hooks.items():
        handlers = [handler for entry in entries for handler in entry['hooks']]
        if len(handlers) != 1 or handlers[0]['command'] != 'python3 "${PLUGIN_ROOT}/scripts/daily_memory.py" hook ' + event:
            findings.append({'rule': 'summary_only_entrypoint', 'path': 'plugins/cognee/hooks.json'})
        if event == 'SessionEnd' and any(handler.get('timeout', 100) > 3 for handler in handlers):
            findings.append({'rule': 'session_end_budget', 'path': 'plugins/cognee/hooks.json'})
    if manifest['name'] != 'cognee' or marketplace['name'] != 'cognee-local' or not (ROOT / marketplace['plugins'][0]['source']['path']).is_dir():
        findings.append({'rule': 'marketplace_layout', 'path': '.agents/plugins/marketplace.json'})
    for name in ['README.md', 'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']:
        if not (ROOT / name).is_file():
            findings.append({'rule': 'required_release_file', 'path': name})
    print(json.dumps({'ok': not findings, 'scanned_files': len(files),
                      'finding_count': len(findings), 'findings': findings}, indent=2))
    return 0 if not findings else 1


if __name__ == '__main__':
    raise SystemExit(main())
