"""Make entry points tested with fake executables, without analytical runs."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workflow.engine import ROOT
from workflow.r_bridge import RBridge
from workflow.quarto_reports import render_report


@unittest.skipUnless(shutil.which('make'), 'Make is required for recipe checks.')
class MakefileTests(unittest.TestCase):
    def executable(self, folder, name, source):
        path = folder / name
        path.write_text('#!' + sys.executable + '\n' + source)
        path.chmod(0o755)
        return path

    def recipe(self, folder, target, *settings):
        environment = dict(os.environ)
        environment['PATH'] = str(folder) + os.pathsep + environment['PATH']
        for name in ('MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'):
            environment.pop(name, None)
        result = subprocess.run(['make', '--no-print-directory', '--silent', target, *settings],
                                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_inside_commands_keep_paths_and_selection_as_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.executable(folder, 'python3', 'import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            settings = 'settings with spaces;printf unsafe.json'
            self.assertEqual(self.recipe(folder, 'inside-job', 'JOB=cpue_a', 'SETTINGS=' + settings),
                             ['run.py', '--output', 'runs', '--from', 'cpue_a', '--scope', 'job',
                              '--settings', settings])
            self.assertEqual(self.recipe(folder, 'inside-reproduce'),
                             ['run.py', '--output', 'reproduced', '--from', 'submission',
                              '--scope', 'workflow', '--settings', 'settings.json'])
            self.assertEqual(self.recipe(folder, 'inside-reproduce', 'JOB=cpue_a'),
                             ['run.py', '--output', 'reproduced', '--from', 'cpue_a',
                              '--scope', 'job', '--settings', 'settings.json'])
            self.assertEqual(self.recipe(folder, 'inside-compare', 'JOB=cpue_a'),
                             ['verify.py', 'reference', 'reproduced', '--job', 'cpue_a'])

    def test_container_command_preserves_job_selection_and_reuses_a_pulled_image(self):
        for present in (True, False):
            with self.subTest(image_present=present), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                log = folder / 'docker-calls.jsonl'
                self.executable(folder, 'docker',
                                'import json,os,sys\n'
                                f'with open({str(log)!r}, "a") as log: log.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                                f'if sys.argv[1:3] == ["image", "inspect"]: sys.exit({0 if present else 1})\n'
                                'if sys.argv[1] == "run":\n'
                                ' print(json.dumps({"args":sys.argv[1:], "start":os.environ["START"], '
                                '"scope":os.environ["SCOPE"], "settings":os.environ["SETTINGS"]}))\n')
                result = self.recipe(folder, 'job', 'JOB=cpue_a', 'OUTPUT=' + str(folder / 'results'))
                self.assertEqual((result['start'], result['scope']), ('cpue_a', 'job'))
                self.assertEqual(result['args'][-5:],
                                 ['make', '--no-print-directory', '--silent', 'inside-run', 'OUTPUT=/outputs'])
                self.assertIn('none', result['args'])
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual([call[0] for call in calls],
                                 ['image', 'run'] if present else ['image', 'pull', 'run'])

    def test_R_recipe_returns_only_the_declared_JSON_response(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.executable(folder, 'Rscript',
                            'import json,sys\nrequest=json.load(sys.stdin)\n'
                            'print(json.dumps({"result":{"key":request["key"]},"effects":{}}))\n')
            environment = dict(os.environ)
            environment['PATH'] = str(folder) + os.pathsep + environment['PATH']
            # The actual Make recipe runs a test double, never an R calculation.
            with patch.dict(os.environ, environment), patch.object(RBridge, 'software', return_value={}):
                result = asyncio.run(RBridge().calculate({'key': 'cpue_a'}))
            self.assertEqual(result, {'result': {'key': 'cpue_a'}, 'effects': {}})


    def test_report_recipe_uses_the_requested_folder_as_one_path(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            report = folder / 'report with spaces;safe'
            report.mkdir()
            self.executable(folder, 'quarto',
                            'from pathlib import Path\nimport sys\n'
                            'if sys.argv[1:] == ["--version"]: print("test-double")\n'
                            'else: Path("report.html").write_text("TEST DOUBLE")\n')
            environment = dict(os.environ)
            environment['PATH'] = str(folder) + os.pathsep + environment['PATH']
            with patch.dict(os.environ, environment), patch.object(RBridge, 'require_container', return_value='fixture'):
                value = render_report(ROOT, 'cpue_report', {}, {}, report, 'fallback')
            self.assertEqual(value['version'], 'test-double')
            self.assertEqual((report / 'report.html').read_text(), 'TEST DOUBLE')
            self.assertEqual((report / 'report.qmd').read_bytes(),
                             (ROOT / 'jobs/cpue_report/report.qmd').read_bytes())
