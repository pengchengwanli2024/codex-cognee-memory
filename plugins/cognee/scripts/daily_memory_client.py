# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""Narrow local HTTP transport; never accepts dialogue, tools or transcript paths."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class Unavailable(Exception):
    """No confirmed write result; callers must not blindly replay a write."""


class Client:
    def __init__(self):
        from _env_file import load_env_file
        load_env_file()
        # This transport is stdlib-only. _plugin_common explicitly supports
        # opting out of its import-time venv re-exec. A late re-exec would lose
        # the already-consumed hook stdin; no runtime packages are needed here.
        os.environ['COGNEE_PLUGIN_IN_VENV'] = '1'
        from _plugin_common import _api_key_with_source, _local_api_url_with_source
        self.endpoint, _ = _local_api_url_with_source()
        parsed = urllib.parse.urlsplit(self.endpoint)
        # This workflow is deliberately local. An existing cloud setup is not
        # silently authorized to receive summaries by installing this adapter.
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise Unavailable('local_endpoint_required')
        self.endpoint = self.endpoint.rstrip('/')
        self.key, _ = _api_key_with_source(self.endpoint)
        if not self.key:
            raise Unavailable('authentication_missing')

    def request(self, path, payload=None, *, body=None, content_type=None, timeout=8):
        uuid_part = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        raw_summary = re.fullmatch(r'/api/v1/datasets/' + uuid_part + '/data/' + uuid_part + '/raw', path)
        if path not in ('/health', '/api/v1/agents/register', '/api/v1/agents/unregister', '/api/v1/search', '/api/v1/remember') and not raw_summary:
            raise ValueError('unsupported_route')
        headers = {'X-Api-Key': self.key}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            content_type = 'application/json'
        if content_type:
            headers['Content-Type'] = content_type
        req = urllib.request.Request(self.endpoint + path, data=body, headers=headers)
        # Ignore proxy env for loopback and reject redirects (no credential
        # forwarding even if a service at the configured port is replaced).
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(req, timeout=timeout) as response:
                data = response.read(2_000_001)
                if len(data) > 2_000_000:
                    raise Unavailable('response_limit')
                return json.loads(data)
        except (OSError, ValueError, urllib.error.URLError):
            raise Unavailable('request_unconfirmed') from None

    def start_existing_runtime(self):
        """Boot only the already-installed runtime; no install or server takeover."""
        try:
            self.request('/health', timeout=2)
            return
        except Unavailable:
            pass
        parsed = urllib.parse.urlsplit(self.endpoint)
        port = parsed.port or 80
        from _plugin_common import server_presence, write_server_pidfile
        verdict, _ = server_presence(self.endpoint, confirm_absent=True)
        if verdict == 'ready':
            return
        if verdict != 'absent':
            raise Unavailable('presence_unknown_or_busy')
        python = Path.home() / '.cognee-plugin/venv/bin/python'
        if not python.is_file():
            raise Unavailable('runtime_missing')
        # Share the original plugin's bootstrap mutex. An existing lock is
        # preserved, including ambiguous/dead-owner evidence; never seize it.
        lock = Path.home() / '.cognee-plugin/server-bootstrap.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Unavailable('bootstrap_in_progress') from None
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'owner': 'summary-only', 'pid': os.getpid(), 'created_at': time.time()}, stream)
            verdict, _ = server_presence(self.endpoint, confirm_absent=True)
            if verdict == 'ready':
                return
            if verdict != 'absent':
                raise Unavailable('presence_changed')
            child_env = dict(os.environ)
            child_env.update({'COGNEE_AGENT_MODE': 'true', 'TELEMETRY_DISABLED': 'true'})
            # _plugin_common pins existing data directories on import. Fixed
            # venv cwd prevents a business repo shadowing the installed cognee.
            child = subprocess.Popen([str(python), '-m', 'uvicorn', 'cognee.api.client:app', '--host', parsed.hostname, '--port', str(port)], cwd=str(python.parent.parent), env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            write_server_pidfile(port, child.pid, version='existing-runtime')
        finally:
            lock.unlink()
        deadline = time.monotonic() + 18
        while time.monotonic() < deadline:
            time.sleep(.5)
            try:
                self.request('/health', timeout=1)
                return
            except Unavailable:
                pass
        raise Unavailable('boot_unconfirmed')

    def register(self, session_hash, dataset):
        return self.request('/api/v1/agents/register', {
            'agent_session_name': 'confirmed_' + session_hash,
            'type': 'codex', 'memory_mode': 'cognee',
            'dataset_names': [dataset], 'source': 'agent_memory',
            'origin_function': 'confirmed_summary_workflow',
        })

    def unregister(self, session_hash):
        return self.request('/api/v1/agents/unregister', {'agent_session_name': 'confirmed_' + session_hash}, timeout=1)

    def search(self, query, dataset, task=None):
        payload = {
            'query': query, 'datasets': [dataset], 'searchType': 'CHUNKS',
            'topK': 12, 'onlyContext': True, 'includeReferences': False,
            'verbose': True,
        }
        if task:
            payload['nodeName'] = ['confirmed_task_' + task]
        response = self.request('/api/v1/search', payload)
        # Embedding providers can split a short capsule into several chunks.
        # Never concatenate ranked fragments or inject backend metadata/paths.
        # Retrieve complete originals of strictly named, scoped summary docs.
        documents = []
        seen = set()
        for result in response if isinstance(response, list) else []:
            if result.get('dataset_name') != dataset:
                continue
            try:
                dataset_id = str(uuid.UUID(result['dataset_id']))
            except (KeyError, ValueError, TypeError):
                continue
            for obj in result.get('objects_result') or []:
                node = obj.get('payload') or {}
                name = node.get('document_name', '')
                if not isinstance(name, str) or not re.fullmatch(r'wf_[0-9a-f]{64}(?:\.txt)?', name):
                    continue
                try:
                    document_id = str(uuid.UUID(node['document_id']))
                except (KeyError, ValueError, TypeError):
                    continue
                if document_id in seen:
                    continue
                seen.add(document_id)
                if len(seen) > 6:
                    break
                try:
                    capsule = self.request('/api/v1/datasets/' + dataset_id + '/data/' + document_id + '/raw', timeout=3)
                    encoded = json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
                    if hashlib.sha256(encoded).hexdigest() == name[3:67]:
                        documents.append(capsule)
                except (Unavailable, TypeError, ValueError):
                    continue
        return documents

    def remember(self, capsule, dataset, digest):
        boundary = 'cognee_' + uuid.uuid4().hex
        fields = {'datasetName': dataset, 'self_improvement': 'false',
                  'run_in_background': 'true', 'chunk_size': '4096',
                  'node_set': 'confirmed_task_' + capsule['task']}
        parts = []
        for name, value in fields.items():
            parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + value + '\r\n').encode())
        parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="data"; filename="wf_' + digest + '.txt"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n').encode())
        parts += [json.dumps(capsule, ensure_ascii=False, separators=(',', ':')).encode(), ('\r\n--' + boundary + '--\r\n').encode()]
        return self.request('/api/v1/remember', body=b''.join(parts), content_type='multipart/form-data; boundary=' + boundary, timeout=12)
