# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""Offline privacy/lifecycle acceptance; no credentials or live backend access."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/cognee/scripts'))
import daily_memory as dm
import daily_memory_client as dc
from daily_memory_client import Client, Unavailable


class MemoryClient:
    """Transport double containing only the fields the adapter sends to it."""
    def __init__(self):
        self.events = []
        self.documents = []
        self.search_unavailable = False
        self.write_unconfirmed = False

    def start_existing_runtime(self):
        self.events.append(('start',))

    def register(self, session, dataset):
        self.events.append(('register', session, dataset))

    def unregister(self, session):
        self.events.append(('unregister', session))

    def search(self, query, dataset, task=None):
        self.events.append(('search', query, dataset, task))
        if self.search_unavailable:
            raise Unavailable('synthetic_offline')
        documents = [value for value in self.documents
                     if task is None or value.get('task') == task]
        return {'results': [{'text': json.dumps(value, ensure_ascii=False)}
                            for value in documents]}

    def remember(self, capsule, dataset, content_hash):
        self.events.append(('remember', copy.deepcopy(capsule), dataset, content_hash))
        if self.write_unconfirmed:
            raise Unavailable('synthetic_uncertain_response')
        self.documents.append(copy.deepcopy(capsule))
        return {'accepted': True}

    def writes(self):
        return [event for event in self.events if event[0] == 'remember']


class WorkflowAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cognee-workflow-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project-a'
        self.project.mkdir()
        self.state = self.root / 'state'
        self.env = mock.patch.dict(os.environ, {
            'COGNEE_WORKFLOW_STATE_DIR': str(self.state),
            'COGNEE_WORKFLOW_DATASET_PREFIX': 'workflow_test',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # Avoid even a Git configuration read; these fixtures are non-Git roots.
        self.git = mock.patch.object(dm.subprocess, 'run',
                                     return_value=SimpleNamespace(returncode=1, stdout=b''))
        self.git.start()
        self.addCleanup(self.git.stop)
        self.client = MemoryClient()
        self.workflow = dm.Workflow(self.project, self.client)
        self.proof = self.project / 'qa/proof.json'
        self.proof.parent.mkdir()
        self.proof_canary = 'PROOF-RAW-CONTENT-CANARY'
        self.proof.write_text(json.dumps({'check': 'passed', 'internal': self.proof_canary}))

    def record(self):
        return {
            'schema': 'confirmed-summary-v1', 'reviewed': True,
            'confirmation': 'tool_verified', 'status': 'verified_local',
            'summary': 'Cognee 工作流本地验证完成。',
            'facts': ['验证代号 WFTEST-AB12CD34。'],
            'evidence': [{'kind': 'artifact', 'path': 'qa/proof.json',
                          'sha256': hashlib.sha256(self.proof.read_bytes()).hexdigest(),
                          'result': 'passed'}],
        }

    def payload(self, session='synthetic-session-a', **extra):
        return dict({'session_id': session, 'cwd': str(self.project)}, **extra)

    def hook(self, event, session='synthetic-session-a', **extra):
        return dm.handle_hook(event, self.payload(session, **extra), self.client)

    def snapshot(self):
        return {str(path.relative_to(self.state)): path.read_bytes()
                for path in self.state.rglob('*') if path.is_file()}

    def assert_absent(self, *canaries):
        sent = json.dumps(self.client.events, ensure_ascii=False)
        saved = b'\n'.join(self.snapshot().values())
        for canary in canaries:
            self.assertNotIn(canary, sent)
            self.assertNotIn(canary.encode(), saved)

    def test_raw_event_fields_never_reach_query_storage_or_context(self):
        canaries = ['RAW-PROMPT-CANARY', 'RAW-ASSISTANT-CANARY',
                    'RAW-TOOL-CANARY', 'RAW-TRANSCRIPT-CANARY']
        transcript = self.root / 'synthetic-transcript.txt'
        transcript.write_text(canaries[3])
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == transcript:
                raise AssertionError('transcript must never be opened')
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, 'open', guarded_open):
            self.hook('SessionStart', transcript_path=str(transcript))
            result = self.hook('UserPromptSubmit',
                               prompt='Cognee Python API ' + canaries[0],
                               transcript_path=str(transcript),
                               messages=[{'content': canaries[3]}],
                               tool_result=canaries[2])
            token = self.workflow.current('synthetic-session-a')
            self.assertTrue(self.workflow.stage(token, self.record())['ok'])
            self.hook('PostToolUse', tool_output=canaries[2], transcript_path=str(transcript))
            self.hook('Stop', last_assistant_message=canaries[1], transcript_path=str(transcript))
            self.hook('SessionEnd', transcript_path=str(transcript))
        for canary in canaries:
            self.assertNotIn(canary, json.dumps(result))
        self.assert_absent(*canaries, 'synthetic-session-a', self.proof_canary)
        queries = [event[1] for event in self.client.events if event[0] == 'search']
        self.assertEqual(queries[0], '已确认 决策 验证 待办 Cognee Python API')
        self.assertEqual(len(self.client.writes()), 1)

    def test_unconfirmed_or_sensitive_records_are_rejected_without_persistence(self):
        token = self.workflow.begin('synthetic-session-a')
        before = self.snapshot()
        records = []
        unreviewed = self.record(); unreviewed['reviewed'] = False
        records.append(unreviewed)
        unconfirmed = self.record(); unconfirmed['confirmation'] = 'unconfirmed'
        records.append(unconfirmed)
        sensitive = self.record(); sensitive['facts'] = ['password=REJECTED-ONLY-CANARY']
        records.append(sensitive)
        user_without_evidence = self.record(); user_without_evidence['confirmation'] = 'user_confirmed'
        records.append(user_without_evidence)
        for value in records:
            with self.subTest(kind=value['confirmation'], reviewed=value['reviewed']):
                result = self.workflow.stage(token, value)
                self.assertFalse(result['ok'])
                self.assertNotIn('REJECTED-ONLY-CANARY', json.dumps(result))
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.client.writes())
        self.assertFalse((self.state / 'signing.key').exists())

    def test_real_proof_hash_and_symlink_escape_are_enforced_before_staging(self):
        token = self.workflow.begin('synthetic-session-a')
        original = self.record()
        self.proof.write_text('{"check":"changed"}')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.workflow.stage(token, original)
        self.assertEqual(self.snapshot(), before)
        outside = self.root / 'outside-proof.json'
        outside.write_text('{"check":"passed"}')
        self.proof.unlink()
        self.proof.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.workflow.stage(token, self.record())
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.client.writes())

    def test_key_style_evidence_filename_is_rejected_before_read_or_write(self):
        token = self.workflow.begin('synthetic-session-a')
        synthetic_path = 'qa/' + 'sk-' + ('X' * 31) + '.json'
        forbidden = self.project / synthetic_path
        synthetic_bytes = b'{"check":"passed"}'
        forbidden.write_bytes(synthetic_bytes)
        record = self.record()
        record['evidence'][0].update(path=synthetic_path,
                                     sha256=hashlib.sha256(synthetic_bytes).hexdigest())
        # The old path-shape policy permits this; runtime must reject the name.
        self.assertTrue(dm.validate_summary(record)['ok'])
        before = self.snapshot()
        original_read = Path.read_bytes

        def guarded_read(path):
            if path == forbidden:
                raise AssertionError('sensitive evidence filename must not be read')
            return original_read(path)

        with mock.patch.object(Path, 'read_bytes', guarded_read), \
                mock.patch.object(dm, 'atomic_json', wraps=dm.atomic_json) as writes:
            result = self.workflow.stage(token, record)
            writes.assert_not_called()
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'sensitive_evidence_path')
        self.assertNotIn(synthetic_path, json.dumps(result))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.client.writes())
        self.assertFalse((self.state / 'signing.key').exists())

    def test_staged_summary_is_submitted_once_across_repeated_lifecycle_events(self):
        self.hook('UserPromptSubmit', prompt='Cognee 记忆验证')
        token = self.workflow.current('synthetic-session-a')
        self.assertTrue(self.workflow.stage(token, self.record())['ok'])
        self.assertEqual(self.workflow.task(token)['phase'], 'staged')
        for event in ('Stop', 'Stop', 'PreCompact', 'SessionEnd'):
            self.hook(event)
        self.assertEqual(len(self.client.writes()), 1)
        self.assertEqual(self.workflow.task(token)['phase'], 'indexed')
        capsule = self.client.writes()[0][1]
        self.assertEqual(capsule['record'], self.record())
        self.assertNotIn(self.proof_canary, json.dumps(capsule))

    def test_unknown_write_is_never_reposted_and_can_be_reconciled_read_only(self):
        self.hook('UserPromptSubmit', prompt='Cognee 记忆验证')
        token = self.workflow.current('synthetic-session-a')
        self.workflow.stage(token, self.record())
        self.client.write_unconfirmed = True
        self.client.search_unavailable = True
        self.hook('Stop')
        self.assertEqual(self.workflow.task(token)['phase'], 'unknown')
        self.hook('Stop')
        self.workflow.pending()
        self.assertEqual(len(self.client.writes()), 1)
        self.assertEqual(self.workflow.task(token)['phase'], 'unknown')
        # A later read discovers the first write; there is still no second POST.
        self.client.search_unavailable = False
        self.client.documents.append(self.client.writes()[0][1])
        outcome = self.workflow.flush(token)
        self.assertTrue(outcome['ok'])
        self.assertEqual(outcome['phase'], 'indexed')
        self.assertEqual(len(self.client.writes()), 1)

    def test_newer_skipped_tasks_do_not_starve_an_old_staged_summary(self):
        old_token = self.workflow.begin('synthetic-session-old')
        self.workflow.stage(old_token, self.record())
        os.utime(self.workflow.path(old_token), (1000, 1000))
        skipped = []
        for index in range(9):
            token = self.workflow.begin('synthetic-session-new-' + str(index))
            self.workflow.skip(token)
            os.utime(self.workflow.path(token), (2000 + index, 2000 + index))
            skipped.append(token)
        self.workflow.pending()
        self.assertEqual(self.workflow.task(old_token)['phase'], 'indexed')
        self.assertEqual(len(self.client.writes()), 1)
        self.assertTrue(all(self.workflow.task(token)['phase'] == 'skipped'
                            for token in skipped))

    def test_pending_rotates_old_unknown_receipts_so_new_staged_work_progresses(self):
        with mock.patch.object(dm.time, 'time', return_value=100):
            old_token = self.workflow.begin('synthetic-session-old')
            self.workflow.stage(old_token, self.record())
            self.client.write_unconfirmed = True
            self.client.search_unavailable = True
            self.workflow.flush(old_token)
        # Model a crash before the last-checked timestamp was committed.
        old_state = self.workflow.task(old_token)
        self.assertEqual(old_state['phase'], 'unknown')
        old_state.pop('last_checked', None)
        dm.atomic_json(self.workflow.path(old_token), old_state)
        with mock.patch.object(dm.time, 'time', return_value=200):
            new_token = self.workflow.begin('synthetic-session-new')
            self.workflow.stage(new_token, self.record())
        self.client.write_unconfirmed = False
        self.client.search_unavailable = False
        with mock.patch.object(dm.time, 'time', return_value=300):
            self.workflow.pending()
        self.assertEqual(self.workflow.task(old_token)['phase'], 'unknown')
        self.assertEqual(self.workflow.task(new_token)['phase'], 'staged')
        self.assertEqual(len(self.client.writes()), 1)
        self.workflow.pending()
        self.assertEqual(self.workflow.task(new_token)['phase'], 'indexed')
        self.assertEqual(self.workflow.task(old_token)['phase'], 'unknown')
        self.assertEqual(len(self.client.writes()), 2)
        self.assertEqual([event[1]['task'] for event in self.client.writes()],
                         [old_token, new_token])

    def test_targeted_receipt_lookup_finds_a_capsule_beyond_the_display_six(self):
        with mock.patch.object(dm.time, 'time', return_value=100):
            token = self.workflow.begin('synthetic-session-old')
            self.workflow.stage(token, self.record())
        target_capsule = self.workflow.task(token)['capsule']
        self.client.write_unconfirmed = True
        self.workflow.flush(token)
        self.assertEqual(self.workflow.task(token)['phase'], 'unknown')
        # Six newer legitimate capsules precede the target in backend results.
        for index in range(6):
            with mock.patch.object(dm.time, 'time', return_value=101 + index):
                newer = self.workflow.begin('synthetic-session-new-' + str(index))
                self.workflow.stage(newer, self.record())
            self.client.documents.append(self.workflow.task(newer)['capsule'])
        self.client.documents.append(target_capsule)
        displayed = self.workflow.recall('Cognee 记忆')
        self.assertEqual(len(displayed), 6)
        self.assertNotIn(token, [item['task'] for item in displayed])
        normal_search = self.client.search

        def overreturned_results(query, dataset, task=None):
            # Keep the normal transport's task validation/recording, then model
            # an overinclusive backend response: the desired capsule is seventh.
            normal_search(query, dataset, task)
            return {'results': [{'text': json.dumps(value, ensure_ascii=False)}
                                for value in self.client.documents]}

        with mock.patch.object(self.client, 'search', side_effect=overreturned_results):
            outcome = self.workflow.flush(token)
        self.assertTrue(outcome['ok'])
        self.assertEqual(outcome['phase'], 'indexed')
        self.assertEqual(self.client.events[-1][0], 'search')
        self.assertEqual(self.client.events[-1][3], token)
        self.assertEqual(len(self.client.writes()), 1)

    def test_session_end_unregisters_without_writing_and_precompact_flushes(self):
        self.hook('UserPromptSubmit', prompt='Cognee 记忆')
        token = self.workflow.current('synthetic-session-a')
        self.workflow.stage(token, self.record())
        self.hook('SessionEnd')
        self.assertEqual(self.workflow.task(token)['phase'], 'staged')
        self.assertFalse(self.client.writes())
        self.assertEqual(self.client.events[-1][0], 'unregister')
        self.hook('PreCompact')
        self.assertEqual(self.workflow.task(token)['phase'], 'indexed')
        self.assertEqual(len(self.client.writes()), 1)

    def test_signature_tampering_and_other_project_capsules_are_excluded(self):
        token = self.workflow.begin('synthetic-session-a')
        self.workflow.stage(token, self.record())
        valid = self.workflow.task(token)['capsule']
        tampered = copy.deepcopy(valid)
        tampered['record']['facts'] = ['未经验证的更改。']
        other_project = self.root / 'project-b'
        other_project.mkdir()
        foreign = dm.Workflow(other_project, self.client)
        other_token = foreign.begin('synthetic-session-b')
        record = self.record()
        record.update(confirmation='user_confirmed', status='confirmed',
                      evidence=[{'kind': 'user_confirmation', 'reference': 'current-task'}])
        foreign.stage(other_token, record)
        foreign_capsule = foreign.task(other_token)['capsule']
        self.assertTrue(foreign.valid_capsule(foreign_capsule))
        self.client.documents = [tampered, foreign_capsule,
                                 {'text': 'not a signed summary'}, valid]
        found = self.workflow.recall('Cognee 记忆')
        self.assertEqual([entry['task'] for entry in found], [token])
        self.assertFalse(self.workflow.valid_capsule(tampered))
        self.assertFalse(self.workflow.valid_capsule(foreign_capsule))
        self.assertNotEqual(self.workflow.dataset, foreign.dataset)

    def test_stop_continuation_keeps_task_and_never_uses_it_as_a_new_prompt(self):
        self.hook('UserPromptSubmit', prompt='Cognee 记忆')
        token = self.workflow.current('synthetic-session-a')
        searches = sum(event[0] == 'search' for event in self.client.events)
        response = self.hook('Stop')
        self.assertEqual(response['decision'], 'block')
        self.assertTrue(response['reason'].startswith(dm.CONTINUATION + token + ']'))
        self.assertEqual(self.hook('UserPromptSubmit', prompt=response['reason']), {})
        self.assertEqual(self.workflow.current('synthetic-session-a'), token)
        self.assertEqual(sum(event[0] == 'search' for event in self.client.events), searches)
        self.hook('Stop', stop_hook_active=True)
        self.assertEqual(self.workflow.task(token)['phase'], 'skipped')
        self.assertFalse(self.client.writes())

    def test_independent_instances_retrieve_confirmed_summary_without_prompt_copying(self):
        token = self.workflow.begin('synthetic-session-a')
        self.workflow.stage(token, self.record())
        self.assertTrue(self.workflow.flush(token)['ok'])
        another = dm.Workflow(self.project, self.client)
        next_token = another.begin('synthetic-session-b')
        self.assertNotEqual(token, next_token)
        found = another.recall('Cognee 跨会话验证代号是什么？')
        self.assertEqual(len(found), 1)
        self.assertIn('WFTEST-AB12CD34', found[0]['record']['facts'][0])
        self.assertNotEqual(another.task(next_token)['session'], self.workflow.task(token)['session'])
        self.assertNotIn('WFTEST-AB12CD34', self.client.events[-1][1])
        self.assertEqual(len(self.client.writes()), 1)

    def test_transport_uses_context_only_chunks_and_disables_self_improvement(self):
        # Construct without __init__: neither helpers/config nor credentials load.
        client = Client.__new__(Client)
        client.request = mock.Mock(return_value={'accepted': True})
        client.search('已确认 决策 验证 待办', 'workflow_test')
        route, payload = client.request.call_args.args
        self.assertEqual(route, '/api/v1/search')
        self.assertEqual(payload['searchType'], 'CHUNKS')
        self.assertIs(payload['onlyContext'], True)
        self.assertFalse(any('session' in key.lower() for key in payload))
        task = 'b' * 32
        client.search('已确认 决策 验证 待办', 'workflow_test', task)
        route, payload = client.request.call_args.args
        self.assertEqual(route, '/api/v1/search')
        self.assertEqual(payload['nodeName'], ['confirmed_task_' + task])
        self.assertFalse(any('session' in key.lower() for key in payload))
        client.remember({'task': task, 'record': {'summary': '合成技术摘要。'}},
                        'workflow_test', 'a' * 64)
        args, kwargs = client.request.call_args
        self.assertEqual(args[0], '/api/v1/remember')
        body = kwargs['body'].decode()
        self.assertIn('name="self_improvement"\r\n\r\nfalse\r\n', body)
        self.assertIn('name="chunk_size"\r\n\r\n4096\r\n', body)
        self.assertIn('name="node_set"\r\n\r\nconfirmed_task_' + task + '\r\n', body)
        self.assertNotIn('session', body.lower())
        self.assertIn('合成技术摘要。', body)

    def test_transport_reads_complete_scoped_summary_instead_of_ranked_fragments(self):
        token = self.workflow.begin('synthetic-session-a')
        self.workflow.stage(token, self.record())
        capsule = self.workflow.task(token)['capsule']
        content_hash = hashlib.sha256(dm.canonical(capsule)).hexdigest()
        dataset_id = '11111111-1111-4111-8111-111111111111'
        document_id = '22222222-2222-4222-8222-222222222222'
        raw_route = '/api/v1/datasets/' + dataset_id + '/data/' + document_id + '/raw'
        metadata_canary = '/synthetic/METADATA-FILE-CANARY.json'
        chunks = [{
            'dataset_name': self.workflow.dataset, 'dataset_id': dataset_id,
            'context_result': ['"facts":["BROKEN-CONTEXT-CANARY',
                               '"signature":"middle fragment', '{"schema":'],
            'objects_result': [
                {'payload': {'document_name': 'wf_' + content_hash + '.txt',
                             'document_id': document_id,
                             'file_path': metadata_canary,
                             'metadata': {'raw': 'METADATA-RAW-CANARY'}}},
                {'payload': {'document_name': 'wf_' + content_hash,
                             'document_id': document_id}},
            ],
        }]
        client = Client.__new__(Client)

        def responses(route, *args, **kwargs):
            if route == '/api/v1/search':
                return chunks
            self.assertEqual(route, raw_route)
            self.assertEqual(args, ())
            self.assertEqual(kwargs, {'timeout': 3})
            return copy.deepcopy(capsule)

        client.request = mock.Mock(side_effect=responses)
        recalled = dm.Workflow(self.project, client).recall('Cognee 记忆')
        self.assertEqual(recalled, [capsule])
        self.assertEqual(client.request.call_count, 2)  # duplicate doc read once
        search_payload = client.request.call_args_list[0].args[1]
        self.assertIs(search_payload['verbose'], True)
        self.assertIs(search_payload['onlyContext'], True)
        self.assertEqual(search_payload['searchType'], 'CHUNKS')
        outbound = str(client.request.call_args_list)
        self.assertNotIn(metadata_canary, outbound)
        self.assertNotIn('METADATA-RAW-CANARY', outbound)
        self.assertNotIn('BROKEN-CONTEXT-CANARY', json.dumps(recalled))
        self.assertNotIn(metadata_canary, json.dumps(recalled))

    def test_transport_excludes_foreign_names_ids_and_bad_source_hashes(self):
        token = self.workflow.begin('synthetic-session-a')
        self.workflow.stage(token, self.record())
        capsule = self.workflow.task(token)['capsule']
        content_hash = hashlib.sha256(dm.canonical(capsule)).hexdigest()
        base = {
            'dataset_name': self.workflow.dataset,
            'dataset_id': '11111111-1111-4111-8111-111111111111',
            'context_result': ['SHOULD-NOT-BE-INJECTED'],
            'objects_result': [{'payload': {
                'document_name': 'wf_' + content_hash + '.txt',
                'document_id': '22222222-2222-4222-8222-222222222222',
                'file_path': '/synthetic/NEVER-FORWARD.json',
            }}],
        }
        cases = []
        foreign = copy.deepcopy(base); foreign['dataset_name'] = 'foreign_dataset'
        cases.append(('foreign_dataset', foreign, 0, capsule))
        bad_name = copy.deepcopy(base)
        bad_name['objects_result'][0]['payload']['document_name'] = '../../arbitrary.json'
        cases.append(('unapproved_document_name', bad_name, 0, capsule))
        bad_id = copy.deepcopy(base)
        bad_id['objects_result'][0]['payload']['document_id'] = '../../arbitrary'
        cases.append(('invalid_document_id', bad_id, 0, capsule))
        bad_dataset_id = copy.deepcopy(base); bad_dataset_id['dataset_id'] = '../arbitrary'
        cases.append(('invalid_dataset_id', bad_dataset_id, 0, capsule))
        altered_source = copy.deepcopy(capsule)
        altered_source['record']['summary'] = '内容被更改。'
        cases.append(('source_hash_mismatch', copy.deepcopy(base), 1, altered_source))
        for label, result, expected_fetches, source in cases:
            with self.subTest(label=label):
                client = Client.__new__(Client)
                client.request = mock.Mock(side_effect=lambda route, *args, **kwargs:
                                           [result] if route == '/api/v1/search' else source)
                self.assertEqual(client.search('已确认 决策 验证 待办', self.workflow.dataset), [])
                self.assertEqual(client.request.call_count, 1 + expected_fetches)
                self.assertNotIn('NEVER-FORWARD', str(client.request.call_args_list))

    def test_raw_summary_routes_require_real_uuid_components_and_never_file_paths(self):
        client = Client.__new__(Client)
        client.endpoint = 'http://127.0.0.1:1'
        client.key = 'synthetic-offline-placeholder'
        dataset_id = '11111111-1111-4111-8111-111111111111'
        document_id = '22222222-2222-4222-8222-222222222222'
        valid = '/api/v1/datasets/' + dataset_id + '/data/' + document_id + '/raw'
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"safe":"summary"}'
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(dc.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(client.request(valid), {'safe': 'summary'})
            sent_request = opener.open.call_args.args[0]
            self.assertEqual(sent_request.full_url, client.endpoint + valid)
            self.assertIsNone(sent_request.data)
            invalid = [
                '/api/v1/datasets/not-a-uuid/data/' + document_id + '/raw',
                '/api/v1/datasets/' + dataset_id + '/data/../../private/raw',
                valid + '?file=/synthetic/private.json',
                '/api/v1/datasets/' + 'a' * 36 + '/data/' + document_id + '/raw',
                '/api/v1/datasets/' + dataset_id + '/data/' + '-' * 36 + '/raw',
            ]
            for route in invalid:
                with self.subTest(route=route):
                    build.reset_mock()
                    with self.assertRaises(ValueError):
                        client.request(route)
                    build.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
