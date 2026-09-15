"""Runner transport failures, without network access or credentials."""
import asyncio
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
