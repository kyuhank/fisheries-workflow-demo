"""R adapter rejection and failure boundaries with explicitly mocked processes."""
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from workflow.r_bridge import RBridge, kill_process_group, run_command
from workflow.quarto_reports import render_report

IMAGE = 'ghcr.io/example/calculation@sha256:' + 'a' * 64


class RBridgeTests(unittest.TestCase):
    def test_host_marker_absence_blocks_new_calculation_before_runtime_lookup(self):
        with patch.object(Path, 'is_file', return_value=False), \
             patch.dict(os.environ, {'PAPER_RUNTIME_IMAGE': IMAGE}):
            with self.assertRaisesRegex(RuntimeError, 'require the declared Docker container'):
                RBridge.require_container()

    def test_container_requires_valid_resolved_image_digest(self):
        with patch.object(Path, 'is_file', return_value=True):
            for image in ('', 'ghcr.io/example:latest', IMAGE[:-1], IMAGE.replace('a' * 64, 'g' * 64),
                          'repo;echo injected@sha256:' + 'a' * 64):
                with self.subTest(image=image), patch.dict(os.environ, {'PAPER_RUNTIME_IMAGE': image}):
                    with self.assertRaisesRegex(RuntimeError, 'actual resolved container digest'):
                        RBridge.require_container()
            with patch.dict(os.environ, {'PAPER_RUNTIME_IMAGE': IMAGE}):
                self.assertEqual(RBridge.require_container(), IMAGE)

    def test_old_checkpoint_is_retained_and_refused_without_silent_method_mapping(self):
        from workflow.engine import Workflow
        with tempfile.TemporaryDirectory() as directory:
            old = {'settings': {'mortality_2': .3}, 'records': {'old': {'run_id': 'Original'}},
                   'run_number': 1}
            path = Path(directory) / 'state.json'
            saved = json.dumps(old)
            path.write_text(saved)
            with self.assertRaisesRegex(ValueError, 'fresh v1.8 R session'):
                Workflow(directory)
            self.assertEqual(path.read_text(), saved)

    def test_missing_native_R_is_a_hard_failure_without_another_backend(self):
        with patch.object(RBridge, 'require_container', return_value=IMAGE), \
             patch('workflow.r_bridge.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Rscript is required'):
                RBridge().software()

    def test_calculation_sends_exact_JSON_and_reads_the_declared_envelope(self):
        async def exercise():
            process = Mock(returncode=0)
            process.communicate = AsyncMock(return_value=(b'{"result":{"one":[1]},"effects":{}}', b''))
            process.wait = AsyncMock()
            context = {'key': 'cpue_a', 'parents': {'extract': {'sets': []}}}
            with patch.object(RBridge, 'software', return_value={'container': IMAGE}), \
                 patch('workflow.r_bridge.shutil.which', return_value='/usr/bin/make'), \
                 patch('workflow.r_bridge.asyncio.create_subprocess_exec', new_callable=AsyncMock,
                       return_value=process) as launch:
                self.assertEqual(await RBridge().calculate(context), {'result': {'one': [1]}, 'effects': {}})
                args = launch.await_args.args
                self.assertEqual(args[:4], ('/usr/bin/make', '--no-print-directory', '--silent', '--jobs=1'))
                self.assertTrue(args[5].endswith('/workflow/Makefile'))
                self.assertEqual(args[-1], 'calculate')
                self.assertTrue(launch.await_args.kwargs['start_new_session'])
                self.assertEqual(json.loads(process.communicate.await_args.args[0]), context)
        asyncio.run(exercise())

    def test_failed_R_process_cannot_be_saved_as_a_success(self):
        async def exercise():
            process = Mock(returncode=2)
            process.communicate = AsyncMock(return_value=(b'', b'RTMB failed'))
            with patch.object(RBridge, 'software', return_value={}), \
                 patch('workflow.r_bridge.shutil.which', return_value='/usr/bin/make'), \
                 patch('workflow.r_bridge.asyncio.create_subprocess_exec', new_callable=AsyncMock,
                       return_value=process):
                with self.assertRaisesRegex(RuntimeError, 'R job assessment_a1 failed: RTMB failed'):
                    await RBridge().calculate({'key': 'assessment_a1'})
        asyncio.run(exercise())

    def test_undeclared_or_nonfinite_process_envelopes_are_rejected(self):
        async def exercise(response):
            process = Mock(returncode=0)
            process.communicate = AsyncMock(return_value=(response.encode(), b''))
            with patch.object(RBridge, 'software', return_value={}), \
                 patch('workflow.r_bridge.shutil.which', return_value='/usr/bin/make'), \
                 patch('workflow.r_bridge.asyncio.create_subprocess_exec', new_callable=AsyncMock,
                       return_value=process):
                with self.assertRaises(ValueError):
                    await RBridge().calculate({'key': 'cpue_a'})
        for response in ('{}', '{"result":[],"effects":{}}',
                         '{"result":{},"effects":{},"extra":1}',
                         '{"result":{"bad":NaN},"effects":{}}'):
            with self.subTest(response=response):
                asyncio.run(exercise(response))


    def test_cancelled_job_kills_Make_and_its_R_process_group(self):
        async def exercise():
            process = Mock(returncode=None, pid=12345)
            process.communicate = AsyncMock(side_effect=[asyncio.CancelledError, (b'', b'')])
            process.wait = AsyncMock()
            with patch.object(RBridge, 'software', return_value={}), \
                 patch('workflow.r_bridge.shutil.which', return_value='/usr/bin/make'), \
                 patch('workflow.r_bridge.asyncio.create_subprocess_exec', new_callable=AsyncMock,
                       return_value=process), \
                 patch('workflow.r_bridge.os.killpg') as kill:
                with self.assertRaises(asyncio.CancelledError):
                    await RBridge().calculate({'key': 'cpue_a'})
                import signal
                kill.assert_called_once_with(12345, signal.SIGKILL)
                self.assertEqual(process.communicate.await_count, 2)
                self.assertEqual(process.communicate.await_args.args, ())
                process.wait.assert_not_awaited()
        asyncio.run(exercise())

    def test_cancelled_job_drains_a_full_child_pipe_before_reaping(self):
        async def exercise():
            child = None
            launch_native = asyncio.create_subprocess_exec

            async def launch(*args, **options):
                nonlocal child
                # A nonanalytical child fills stdout before the adapter can read.
                options['limit'] = 1024
                child = await launch_native(sys.executable, '-c',
                                            "import os,signal; os.write(1,b'x'*400000); signal.pause()",
                                            **options)
                deadline = asyncio.get_running_loop().time() + 1
                while not child.stdout._paused:
                    if asyncio.get_running_loop().time() > deadline:
                        self.fail('The fixture did not fill its stdout pipe.')
                    await asyncio.sleep(.01)
                asyncio.current_task().cancel()
                return child

            started = time.monotonic()
            try:
                with patch.object(RBridge, 'software', return_value={}), \
                     patch('workflow.r_bridge.shutil.which', return_value='/usr/bin/make'), \
                     patch('workflow.r_bridge.asyncio.create_subprocess_exec', side_effect=launch):
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(RBridge().calculate({'key': 'cpue_a'}), 2)
                self.assertLess(time.monotonic() - started, 1.5)
                self.assertEqual(child.returncode, -signal.SIGKILL)
            finally:
                if child is not None:
                    kill_process_group(child)
                    await asyncio.wait_for(child.communicate(), 1)
        asyncio.run(exercise())

    def test_timed_out_report_kills_the_whole_process_group(self):
        import signal
        import subprocess
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired('make', 120), ('', '')]
        with patch('workflow.r_bridge.subprocess.Popen', return_value=process) as launch, \
             patch('workflow.r_bridge.os.killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_command(['make', 'report'], timeout=120)
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_Quarto_failure_is_not_replaced_by_light_HTML(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(RBridge, 'require_container', return_value=IMAGE), \
             patch('workflow.quarto_reports.shutil.which', return_value='/usr/bin/quarto'), \
             patch('workflow.quarto_reports.run_command', return_value=Mock(
                 returncode=1, stderr='render failed', stdout='')):
            with self.assertRaisesRegex(RuntimeError, 'Quarto report failed: render failed'):
                render_report(root, 'cpue_report', {}, {}, Path(directory), 'fallback')
            self.assertFalse((Path(directory) / 'report.html').exists())
            self.assertTrue((Path(directory) / 'report.qmd').exists())
