# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""DeepSeek Harness bundle contract; offline, no backend or credentials."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
PLUGIN = Path(__file__).resolve().parents[1] / 'plugins/cognee'
NODE = shutil.which('node')


def node_major():
    if NODE is None:
        return 0
    match = re.match(r'v(\d+)', subprocess.run([NODE, '--version'], capture_output=True, text=True).stdout)
    return int(match.group(1)) if match else 0


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN / 'package.json').read_text())

    def test_version_tracks_the_codex_manifest(self):
        codex = json.loads((PLUGIN / '.codex-plugin/plugin.json').read_text())['version']
        # npm treats "+local.N" as ignorable build metadata, so the bundle uses "-local.N".
        self.assertEqual(self.manifest['version'], codex.replace('+', '-'))

    def test_exports_files_and_patch(self):
        for key, target in self.manifest['exports'].items():
            matches = list(PLUGIN.glob(target[2:])) if '*' in target else [PLUGIN / target]
            self.assertTrue(matches and all(path.is_file() for path in matches), key)
        for entry in self.manifest['files']:
            self.assertTrue(list(PLUGIN.glob(entry)), entry)
        patch = (PLUGIN / self.manifest['dsh']['bundle']['patch']).read_text()
        self.assertIn('name: ' + self.manifest['name'] + '\n', patch)
        self.assertNotIn('dsh-mcp-client', patch)
        self.assertNotIn('dependencies', self.manifest)
        self.assertNotIn('scripts', self.manifest)

    def test_only_the_summary_workflow_is_exposed(self):
        config = json.loads((PLUGIN / 'dsh/skills.json').read_text())
        shown = {name: value for name, value in config['skills'].items() if not value.get('hidden')}
        self.assertEqual(set(shown), {'daily-memory', 'setup'})
        on_disk = {path.name for path in (PLUGIN / 'skills').iterdir() if path.is_dir()}
        self.assertEqual(set(config['skills']), on_disk)
        notes = shown['daily-memory']['preface']
        for action in ('begin', 'recall', 'stage', 'flush', 'status'):
            self.assertIn(action, notes)
        self.assertIn('nothing is recalled or saved automatically', notes)

    def test_locales(self):
        for locale in ('en', 'zh'):
            meta = json.loads((PLUGIN / 'locale' / (locale + '.json')).read_text())['meta']
            self.assertTrue(meta['title'])
            self.assertGreater(len(meta['description']), 40)


@unittest.skipUnless(node_major() >= 22, 'Node.js 22+ is required for the provider tests')
class ProviderTests(unittest.TestCase):
    def test_provider_lists_two_renamed_skills_with_unchanged_bodies(self):
        done = subprocess.run(
            [NODE, '--input-type=module', '-e',
             "import { createProvider } from './dsh/index.mjs';"
             "const p = await createProvider(); const list = await p.list();"
             "const skills = []; for (const c of list) skills.push(await p.get(c));"
             "console.log(JSON.stringify({ list, skills }))"],
            cwd=PLUGIN, capture_output=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors='replace'))
        result = json.loads(done.stdout.decode('utf-8'))
        self.assertEqual([item['name'] for item in result['list']], ['cognee-daily-memory', 'cognee-setup'])
        for item, skill in zip(result['list'], result['skills']):
            body = (PLUGIN / 'skills' / item['locator'] / 'SKILL.md').read_text().split('---\n', 2)[2]
            self.assertTrue(skill['content'].endswith(body))
            notes = skill['content'][:-len(body)]
            self.assertIn(str(PLUGIN), notes)
            self.assertNotIn('{{', notes)


if __name__ == '__main__':
    unittest.main()
