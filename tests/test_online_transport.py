"""Public identity GET transport checks; no network, credentials or calculations."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'EXPLICIT-TEST-DOUBLE-NOT-A-CREDENTIAL'


class Response(io.BytesIO):
    status = 200
    headers = {'x-ratelimit-remaining': '999'}


@unittest.skipUnless((ROOT / 'scripts/check-online.py').exists(), 'Hosted checker unavailable')
class OnlineGitHubTransportTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('online_transport_fixture', ROOT / 'scripts/check-online.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.REPORT = {}

    def test_token_is_used_only_for_fixed_public_identity_gets(self):
        for path in ('commits/' + 'a' * 40, 'actions/runs/123'):
            opener = Mock()
            opener.open.return_value = Response(b'{"verified":"fixture"}')
            with patch.dict(os.environ, {'GITHUB_TOKEN': TOKEN}, clear=True), \
                 patch.object(self.module.urllib.request, 'build_opener', return_value=opener) as build:
                self.assertEqual(self.module.github(path), {'verified': 'fixture'})
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.github.com/repos/' + self.module.REPOSITORY + '/' + path)
            self.assertEqual(request.get_method(), 'GET')
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + TOKEN)
            self.assertIsInstance(build.call_args.args[0], self.module.GitHubReadRedirectHandler)
            self.assertNotIn(TOKEN, json.dumps(self.module.REPORT))

    def test_optional_public_access_has_no_authorization_header(self):
        opener = Mock()
        opener.open.return_value = Response(b'{}')
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(self.module.urllib.request, 'build_opener', return_value=opener):
            self.module.github('actions/runs/123')
        self.assertIsNone(opener.open.call_args.args[0].get_header('Authorization'))
        self.assertFalse(self.module.REPORT['github_read_verification'][0]['authenticated'])

    def test_other_paths_are_rejected_before_opening_a_connection(self):
        with patch.object(self.module.urllib.request, 'build_opener') as build:
            for path in ('https://example.invalid', '../actions/runs/123', 'actions/runs/123?token=x',
                         'actions/runs/123/cancel', 'git/refs/heads/main'):
                with self.assertRaisesRegex(ValueError, 'Unsupported public GitHub verification GET'):
                    self.module.github(path)
            build.assert_not_called()

    def test_redirects_cannot_forward_the_verification_token(self):
        handler = self.module.GitHubReadRedirectHandler()
        request = urllib.request.Request('https://api.github.com/repos/' + self.module.REPOSITORY + '/actions/runs/123',
                                         headers={'Authorization': 'Bearer ' + TOKEN})
        for target in ('https://example.invalid/', 'http://api.github.com/', 'https://api.github.com/redirect'):
            self.assertIsNone(handler.redirect_request(request, None, 302, 'fixture', {}, target))

    def test_http_status_and_numeric_rate_headers_are_preserved_without_error_body(self):
        for status in (403, 429, 502):
            self.module.REPORT = {}
            error = urllib.error.HTTPError('https://example.invalid/?token=' + TOKEN, status, TOKEN,
                                          {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1800000000',
                                           'retry-after': TOKEN, 'Authorization': TOKEN}, io.BytesIO(TOKEN.encode()))
            opener = Mock()
            opener.open.side_effect = error
            with patch.dict(os.environ, {'GITHUB_TOKEN': TOKEN}, clear=True), \
                 patch.object(self.module.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(RuntimeError, r'Public GitHub execution verification failed \(HTTP ' + str(status)) as caught:
                    self.module.github('actions/runs/123')
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertEqual(self.module.REPORT['github_read_verification'],
                             [{'endpoint': 'workflow_run', 'authenticated': True, 'http_status': status,
                               'x-ratelimit-remaining': 0, 'x-ratelimit-reset': 1800000000}])
            self.assertEqual(opener.open.call_count, 1)

    def test_connection_and_invalid_json_errors_are_sanitized(self):
        for failure in (urllib.error.URLError(TOKEN), Response(TOKEN.encode())):
            self.module.REPORT = {}
            opener = Mock()
            if isinstance(failure, Exception):
                opener.open.side_effect = failure
            else:
                opener.open.return_value = failure
            with patch.dict(os.environ, {'GITHUB_TOKEN': TOKEN}, clear=True), \
                 patch.object(self.module.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(RuntimeError, 'connection or invalid JSON') as caught:
                    self.module.github('actions/runs/123')
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertNotIn(TOKEN, json.dumps(self.module.REPORT))
            self.assertEqual(opener.open.call_count, 1)

    def test_github_token_does_not_enter_reader_requests_and_post_is_not_retried(self):
        session = {'id': 'explicit-reader-fixture', 'token': 'EXPLICIT-READER-TEST-DOUBLE'}
        with patch.dict(os.environ, {'GITHUB_TOKEN': TOKEN}, clear=True), \
             patch.object(self.module.urllib.request, 'urlopen', return_value=Response(b'{"ok":true}')) as open_url:
            self.assertEqual(self.module.request('/run', {'start': 'fixture'}, session), {'ok': True})
            request = open_url.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + session['token'])
            self.assertNotIn(TOKEN, request.full_url)
            self.assertNotIn(TOKEN.encode(), request.data)
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(open_url.call_count, 1)
        with patch.object(self.module.urllib.request, 'urlopen', side_effect=urllib.error.URLError(TOKEN)) as open_url:
            with self.assertRaisesRegex(RuntimeError, 'Outcome may be unknown; do not repeat this dispatch'):
                self.module.request('/run', {'start': 'fixture'}, session)
            self.assertEqual(open_url.call_count, 1)
