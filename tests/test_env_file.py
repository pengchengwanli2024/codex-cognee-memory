# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""NO_PROXY normalization: the in-process httpx clients cannot parse bracketed IPv6 entries."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/cognee/scripts'
sys.path.insert(0, str(SCRIPTS))


def fresh_module():
    """Re-import _env_file so its process-global `_loaded` flag starts clear."""
    for name in ('_env_file',):
        sys.modules.pop(name, None)
    import _env_file
    return importlib.reload(_env_file)


class NoProxyTests(unittest.TestCase):
    def setUp(self):
        self.module = fresh_module()

    def tearDown(self):
        for name in ('_env_file',):
            sys.modules.pop(name, None)

    def test_bracketed_ipv6_entries_lose_their_brackets(self):
        self.assertEqual(
            self.module._unbracket_ipv6_entries('localhost,127.0.0.1,::1,[::1]'),
            'localhost,127.0.0.1,::1,::1',
        )

    def test_a_parseable_value_is_unchanged(self):
        for value in ('localhost,127.0.0.1,::1', '*', '', '10.0.0.0/8,[2001:db8::1]'):
            fixed = self.module._unbracket_ipv6_entries(value)
            self.assertNotIn('[', fixed)
            self.assertNotIn(']', fixed)

    def test_normalize_rewrites_both_spellings_in_place(self):
        with mock.patch.dict(os.environ, {'NO_PROXY': 'a,[::1]', 'no_proxy': '[::1],b'}, clear=False):
            self.module.normalize_no_proxy()
            self.assertEqual(os.environ['NO_PROXY'], 'a,::1')
            self.assertEqual(os.environ['no_proxy'], '::1,b')

    def test_an_absent_variable_stays_absent(self):
        env = {k: v for k, v in os.environ.items() if k not in ('NO_PROXY', 'no_proxy')}
        with mock.patch.dict(os.environ, env, clear=True):
            self.module.normalize_no_proxy()
            self.assertNotIn('NO_PROXY', os.environ)
            self.assertNotIn('no_proxy', os.environ)

    def test_a_parseable_value_is_what_httpx_gets(self):
        """The regression itself: httpx parses each no_proxy entry as a URL pattern and
        rejects `[::1]`. The suite is stdlib-only, so assert the property httpx needs —
        no brackets anywhere in the list — rather than importing httpx."""
        with mock.patch.dict(os.environ, {'NO_PROXY': 'localhost,127.0.0.1,::1,[::1]'}, clear=False):
            self.module.normalize_no_proxy()
            entries = os.environ['NO_PROXY'].split(',')
            self.assertTrue(all('[' not in entry and ']' not in entry for entry in entries))
            self.assertIn('::1', entries)
            self.assertIn('127.0.0.1', entries)

    def test_load_env_file_normalizes_after_loading_the_file(self):
        with mock.patch.dict(os.environ, {'NO_PROXY': '[::1]'}, clear=False):
            module = fresh_module()
            module.load_env_file()
            self.assertEqual(os.environ['NO_PROXY'], '::1')


if __name__ == '__main__':
    unittest.main()
