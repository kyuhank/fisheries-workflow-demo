import copy
import json
from pathlib import Path
import tempfile
import unittest

from workflow.spec import CONFIG, load_spec


class ConfigurationTests(unittest.TestCase):
    def reject(self, config, message):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'jobs.json'
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, message):
                load_spec(path)

    def test_duplicate_job(self):
        config = copy.deepcopy(CONFIG)
        config['jobs'].append(config['jobs'][0])
        self.reject(config, 'duplicate job')

    def test_unknown_parent(self):
        config = copy.deepcopy(CONFIG)
        config['jobs'][4]['parents'] = ['unknown_job']
        self.reject(config, 'preceding jobs')

    def test_cycle(self):
        config = copy.deepcopy(CONFIG)
        config['jobs'][0]['parents'] = ['qc']
        self.reject(config, 'preceding jobs')

    def test_stage_cannot_start_before_its_inputs(self):
        config = copy.deepcopy(CONFIG)
        config['stages'][0], config['stages'][1] = config['stages'][1], config['stages'][0]
        self.reject(config, 'ready before')

    def test_entry_point_cannot_escape_job_directory(self):
        config = copy.deepcopy(CONFIG)
        config['jobs'][4]['run'] = '../other.R'
        self.reject(config, 'R entry point')

    def test_handover_requires_an_actual_input(self):
        config = copy.deepcopy(CONFIG)
        config['handovers']['data']['cpue_a'] = ['qc']
        self.reject(config, 'file-transfer boundary')

    def test_duplicate_json_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'jobs.json'
            path.write_text('{"jobs": [], "jobs": []}')
            with self.assertRaisesRegex(ValueError, 'Duplicate configuration field'):
                load_spec(path)


if __name__ == '__main__':
    unittest.main()
