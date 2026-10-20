"""Runner transport failures, without network access or credentials."""
import asyncio
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'cloud/run.py').exists(), 'Hosted adapter unavailable')
class RunnerTransportTest(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {'PAPER_REQUEST_ID': '00000000-0000-4000-8000-000000000001'}):
            spec = importlib.util.spec_from_file_location('runner_transport_test', ROOT / 'cloud/run.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module._token, self.module._expires = 'test-only', float('inf')

    def error(self, code, message):
        return HTTPError('https://example.invalid', code, 'test', {},
                         io.BytesIO(json.dumps({'error': message}).encode()))

    def test_hosted_runner_forwards_job_scope_to_the_calculation_engine(self):
        runner = self.module.HostedWorkflow.__new__(self.module.HostedWorkflow)
        runner.pool = None
        with patch.object(self.module.Workflow, 'run', new_callable=AsyncMock,
                          return_value={'scope': 'job'}) as run:
            result = asyncio.run(runner.run('prepare_a', 'job'))
        run.assert_awaited_once_with('prepare_a', 'job')
        self.assertEqual(result, {'scope': 'job'})

    def test_registered_scope_reaches_runner_and_legacy_context_keeps_workflow_scope(self):
        for supplied, expected in [({}, 'workflow'), ({'scope': 'job'}, 'job'),
                                   ({'scope': 'workflow'}, 'workflow')]:
            with self.subTest(context=supplied):
                context = {'checkpoint': 'saved inputs', 'start_job': 'prepare_a', **supplied}
                runner = MagicMock()
                runner.run = AsyncMock(return_value={'scope': expected})
                runner.bundle.return_value = b'bundle'
                runner.state.return_value = {'records': {}}
                runner.delivery.pending = []
                with patch.object(self.module, 'api', side_effect=[context, {'ok': True}]), \
                        patch.object(self.module, 'Path'), \
                        patch.object(self.module, 'restore'), \
                        patch.object(self.module, 'checkpoint', return_value='checkpoint'), \
                        patch.object(self.module, 'HostedWorkflow', return_value=runner):
                    asyncio.run(self.module.main())
                runner.run.assert_awaited_once_with('prepare_a', expected)

    def test_event_retry_preserves_operation_and_payload(self):
        calls = []

        def transport(request, **_kwargs):
            calls.append(request.data)
            if len(calls) == 1:
                raise self.error(503, 'The database request could not be completed (HTTP 504).')
            return io.BytesIO(b'{"ok":true}')

        with patch.object(self.module, 'urlopen', transport), patch.object(self.module.time, 'sleep'):
            self.assertEqual(self.module.api('event', {'event': {'state': 'running'}}), {'ok': True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertTrue(json.loads(calls[0])['operation_id'])

    def test_legacy_database_504_is_retryable_but_invalid_requests_are_not(self):
        for code, message, retryable in [
            (400, 'The database request could not be completed (HTTP 504).', True),
            (400, 'Different code version.', False),
            (400, 'Invalid request containing HTTP 504.', False),
            (401, 'Runner identity required.', False),
            (403, 'Access denied.', False),
        ]:
            with self.subTest(code=code, message=message):
                with patch.object(self.module, 'urlopen', side_effect=lambda *_a, **_k: (_ for _ in ()).throw(
                    self.error(code, message))) as transport, patch.object(self.module.time, 'sleep') as sleep:
                    with self.assertRaises(self.module.TemporaryAPIError if retryable else RuntimeError) as failure:
                        self.module.api('context')
                self.assertEqual(transport.call_count, 3 if retryable else 1)
                self.assertEqual(sleep.call_count, 2 if retryable else 0)
                if not retryable:
                    self.assertNotIsInstance(failure.exception, self.module.TemporaryAPIError)

    def test_finish_recovers_from_lost_response_with_same_receipt(self):
        with patch.object(self.module, 'urlopen', side_effect=[
            URLError('private URL and credential'), io.BytesIO(b'{"ok":true}'),
        ]) as transport, patch.object(self.module.time, 'sleep'):
            self.module.api('finish', {'result': {'run_id': 'Run 001'}, 'pending_events': []})
        requests = [call.args[0] for call in transport.call_args_list]
        self.assertEqual(requests[0].data, requests[1].data)

    def test_slow_finish_acknowledges_the_same_committed_receipt(self):
        body = {'checkpoint': 'preserved checkpoint', 'bundle': 'preserved bundle',
                'state': {'records': {'mse_report': {'run_id': 'Run 001'}}},
                'result': {'run_id': 'Run 001'}, 'error': None, 'pending_events': []}
        receipts, calls = {}, []

        def transport(request, *, timeout):
            calls.append((request.data, timeout))
            operation = json.loads(request.data)['operation_id']
            if operation not in receipts:
                # Model a committed receipt whose acknowledgement was lost.
                receipts[operation] = request.data
                body['state']['records'].clear()
                raise URLError('private connection detail')
            if receipts[operation] != request.data:
                raise self.error(400, 'Operation identifier already used.')
            # Advance no real clock: the response arrives after the server's
            # 100.5s explicit database retry window, beyond the old 30s limit.
            if timeout < 101:
                raise TimeoutError('private slow response detail')
            return io.BytesIO(b'{"ok":true}')

        with patch.object(self.module, 'urlopen', transport), patch.object(self.module.time, 'sleep'):
            self.assertEqual(self.module.api('finish', body), {'ok': True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], calls[1][0])
        self.assertEqual(json.loads(calls[1][0])['state']['records'],
                         {'mse_report': {'run_id': 'Run 001'}})
        self.assertTrue(self.module.uuid.UUID(json.loads(calls[1][0])['operation_id']))
        self.assertTrue(all(101 <= timeout <= 120 for _, timeout in calls))

    def test_finish_keeps_short_identity_and_other_operation_timeouts(self):
        self.module._expires = 0
        environment = {'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://example.invalid/identity?request=test',
                       'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'test-only'}
        with patch.dict(os.environ, environment), patch.object(self.module, 'urlopen', side_effect=[
            io.BytesIO(b'{"value":"test-only"}'), io.BytesIO(b'{"ok":true}'),
            io.BytesIO(b'{"ok":true}'),
        ]) as transport:
            self.assertEqual(self.module.api('finish', {'result': {}}), {'ok': True})
            self.assertEqual(self.module.api('event', {'event': {'state': 'running'}}), {'ok': True})
        self.assertEqual([call.kwargs['timeout'] for call in transport.call_args_list], [30, 120, 30])

    def test_finish_rejects_invalid_receipts_and_untrusted_identity_without_retry(self):
        for code, message in [(400, 'Operation identifier already used.'),
                              (400, 'Different code version.'),
                              (401, 'Runner identity required.'), (403, 'Untrusted runner.')]:
            with self.subTest(code=code, message=message):
                with patch.object(self.module, 'urlopen', side_effect=lambda *_a, **_k: (_ for _ in ()).throw(
                    self.error(code, message))) as transport, patch.object(self.module.time, 'sleep') as sleep:
                    with self.assertRaises(RuntimeError) as failure:
                        self.module.api('finish', {'result': {}})
                self.assertNotIsInstance(failure.exception, self.module.TemporaryAPIError)
                self.assertEqual(transport.call_count, 1)
                sleep.assert_not_called()

    def test_finish_without_acknowledgement_still_fails_after_three_attempts(self):
        with patch.object(self.module, 'urlopen', side_effect=TimeoutError('private detail')) as transport, \
                patch.object(self.module.time, 'sleep') as sleep:
            with self.assertRaises(self.module.TemporaryAPIError) as failure:
                self.module.api('finish', {'result': {}})
        self.assertEqual(transport.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.5, 1])
        self.assertEqual(len({call.args[0].data for call in transport.call_args_list}), 1)
        self.assertTrue(all(call.kwargs['timeout'] == 120 for call in transport.call_args_list))
        self.assertNotIn('private', str(failure.exception))

    def test_exhausted_network_failure_is_bounded_and_private(self):
        with patch.object(self.module, 'urlopen', side_effect=URLError('private credential')) as transport, \
                patch.object(self.module.time, 'sleep') as sleep:
            with self.assertRaises(self.module.TemporaryAPIError) as failure:
                self.module.api('data')
        self.assertEqual(transport.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.5, 1])
        self.assertNotIn('private', str(failure.exception))

    def test_queued_events_are_immutable_and_keep_their_order(self):
        delivery = self.module.EventDelivery()
        state = {'records': {}}
        calls = []

        def send(_path, body):
            calls.append(body)
            if len(calls) == 1:
                raise self.module.TemporaryAPIError('unavailable')

        with patch.object(self.module, 'api', send):
            delivery.publish({'event': {'state': 'running'}, 'state': state})
            state['records']['cpue_a'] = {'run_id': 'Run 001'}
            delivery.publish({'event': {'state': 'complete'}, 'state': state})
            self.assertEqual(len(calls), 1)
            delivery.flush(required=True)
        self.assertEqual([c['event']['state'] for c in calls], ['running', 'running', 'complete'])
        self.assertEqual(calls[0]['operation_id'], calls[1]['operation_id'])
        self.assertEqual(calls[1]['state'], {'records': {}})
        self.assertEqual(delivery.pending, [])

    def test_status_authentication_failure_is_never_deferred(self):
        delivery = self.module.EventDelivery()
        with patch.object(self.module, 'api', side_effect=RuntimeError('Untrusted runner.')):
            with self.assertRaisesRegex(RuntimeError, 'Untrusted runner'):
                delivery.publish({'event': {'state': 'running'}})

    def test_optional_startup_telemetry_does_not_prevent_docker_setup(self):
        fake = types.ModuleType('run')
        fake.TemporaryAPIError = self.module.TemporaryAPIError
        for error, expected in [(self.module.TemporaryAPIError('temporary'), False),
                                (RuntimeError('Untrusted runner.'), True)]:
            with patch.object(fake, 'api', side_effect=error, create=True), \
                    patch.dict(sys.modules, {'run': fake}):
                if expected:
                    with self.assertRaisesRegex(RuntimeError, 'Untrusted runner'):
                        runpy.run_path(str(ROOT / 'cloud/announce.py'))
                else:
                    runpy.run_path(str(ROOT / 'cloud/announce.py'))


    def finish_body(self, error=None):
        return {'checkpoint': base64.b64encode(b'checkpoint\x00').decode(),
                'bundle': base64.b64encode(b'bundle\xff').decode(),
                'state': {'records': {}}, 'result': None if error else {'run_id': 'Run 003'},
                'error': error, 'pending_events': []}

    def receipt(self, body, operation):
        return {'request_id': self.module.REQUEST, 'operation_id': operation,
                'payload_hash': 'd' * 64, 'github_run': '39365433531', 'commit_sha': 'a' * 40,
                'status': 'failed' if body['error'] else 'complete', 'error': body['error'],
                'run_id': body['result']['run_id'] if body['result'] else None,
                **{key + '_sha256': hashlib.sha256(base64.b64decode(body[key])).hexdigest()
                   for key in ('bundle', 'checkpoint')}}

    def test_lost_committed_finish_is_read_back_without_rerunning_analysis(self):
        for error in (None, 'Original calculation failed.'):
            with self.subTest(error=error):
                calls, writes = [], []
                context = {'checkpoint': '', 'start_job': 'submission'}
                runner = MagicMock()
                runner.run = AsyncMock(side_effect=RuntimeError(error) if error else None,
                                       return_value={'run_id': 'Run 003'})
                runner.bundle.return_value = b'bundle\xff'
                runner.state.return_value = {'records': {}}
                runner.delivery.pending = []

                def transport(request, *, timeout):
                    calls.append(request)
                    if urlparse(request.full_url).path.endswith('/context'):
                        return io.BytesIO(json.dumps(context).encode())
                    if request.data is not None:
                        writes.append(json.loads(request.data))
                        raise self.error(503, 'The database request could not be completed (HTTP 504).')
                    query = parse_qs(urlparse(request.full_url).query)
                    self.assertEqual(query, {'request': [self.module.REQUEST],
                                            'operation_id': [writes[0]['operation_id']]})
                    self.assertTrue(urlparse(request.full_url).path.endswith('/finish-receipt'))
                    self.assertEqual(timeout, 30)
                    return io.BytesIO(json.dumps({'receipt': self.receipt(writes[0], query['operation_id'][0])}).encode())

                with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': 'a' * 40}), \
                        patch.object(self.module, 'urlopen', transport), \
                        patch.object(self.module, 'restore'), patch.object(self.module, 'Path'), \
                        patch.object(self.module, 'HostedWorkflow', return_value=runner), \
                        patch.object(self.module, 'checkpoint', return_value=self.finish_body()['checkpoint']), \
                        patch.object(self.module.time, 'sleep') as sleep:
                    if error:
                        with self.assertRaisesRegex(RuntimeError, 'Original calculation failed'):
                            asyncio.run(self.module.main())
                    else:
                        asyncio.run(self.module.main())
                self.assertEqual(len(calls), 3)  # Context, original finish, one readback.
                self.assertEqual(len(writes), 1)
                runner.run.assert_awaited_once_with('submission', 'workflow')
                sleep.assert_not_called()

    def test_receipt_missing_or_unavailable_keeps_exact_three_write_and_probe_budget(self):
        for unavailable in (False, True):
            with self.subTest(unavailable=unavailable):
                calls, writes = [], []

                def transport(request, *, timeout):
                    calls.append((request, timeout))
                    if request.data is not None:
                        writes.append(request.data)
                        raise self.error(503, 'The database request could not be completed (HTTP 504).')
                    if unavailable:
                        raise URLError('private lookup failure')
                    return io.BytesIO(b'{"receipt":null}')

                with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': 'a' * 40}), \
                        patch.object(self.module, 'urlopen', transport), \
                        patch.object(self.module.time, 'sleep') as sleep:
                    with self.assertRaises(self.module.TemporaryAPIError):
                        self.module.api('finish', self.finish_body())
                self.assertEqual(len(calls), 6)
                self.assertEqual(len(writes), 3)
                self.assertEqual(len(set(writes)), 1)
                self.assertEqual([timeout for _, timeout in calls], [120, 30] * 3)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [.5, 1])

    def test_receipt_can_acknowledge_after_one_missing_probe_without_a_new_uuid(self):
        writes, probes = [], []

        def transport(request, **_kwargs):
            if request.data is not None:
                writes.append(request.data)
                raise TimeoutError('lost finish response')
            probes.append(request)
            operation = json.loads(writes[0])['operation_id']
            receipt = None if len(probes) == 1 else self.receipt(self.finish_body(), operation)
            return io.BytesIO(json.dumps({'receipt': receipt}).encode())

        with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': 'a' * 40}), \
                patch.object(self.module, 'urlopen', transport), patch.object(self.module.time, 'sleep'):
            self.assertEqual(self.module.api('finish', self.finish_body()), {'ok': True})
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0], writes[1])
        self.assertEqual(probes[0].full_url, probes[1].full_url)

    def test_mismatched_receipt_fails_closed_before_another_finish_write(self):
        changes = {'request_id': 'other-request', 'operation_id': 'other-operation',
                   'github_run': 'other-run', 'commit_sha': 'b' * 40, 'status': 'failed',
                   'error': 'unexpected failure', 'run_id': 'Run 004',
                   'bundle_sha256': '0' * 64, 'checkpoint_sha256': '0' * 64,
                   'payload_hash': 'not-a-64-character-digest'}
        for key, value in changes.items():
            with self.subTest(field=key):
                writes = []

                def transport(request, **_kwargs):
                    if request.data is not None:
                        writes.append(json.loads(request.data))
                        raise TimeoutError('lost response')
                    receipt = self.receipt(writes[0], writes[0]['operation_id'])
                    receipt[key] = value
                    return io.BytesIO(json.dumps({'receipt': receipt}).encode())

                with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': 'a' * 40}), \
                        patch.object(self.module, 'urlopen', transport), \
                        patch.object(self.module.time, 'sleep') as sleep:
                    with self.assertRaisesRegex(RuntimeError, 'receipt did not match'):
                        self.module.api('finish', self.finish_body())
                self.assertEqual(len(writes), 1)
                sleep.assert_not_called()

    def test_permanent_finish_failure_is_not_reconciled_even_with_known_artifacts(self):
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': 'a' * 40}), \
                patch.object(self.module, 'urlopen', side_effect=self.error(403, 'Untrusted runner.')) as send:
            with self.assertRaises(RuntimeError):
                self.module.api('finish', self.finish_body())
        self.assertEqual(send.call_count, 1)

    def test_unknown_source_binding_never_accepts_a_receipt(self):
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '39365433531', 'GITHUB_SHA': ''}), \
                patch.object(self.module, 'urlopen', side_effect=TimeoutError()) as send, \
                patch.object(self.module.time, 'sleep'):
            with self.assertRaises(self.module.TemporaryAPIError):
                self.module.api('finish', self.finish_body())
        self.assertEqual(send.call_count, 3)
        self.assertTrue(all(c.args[0].data is not None for c in send.call_args_list))
