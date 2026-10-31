"""Harbor 适配正反例；本地真实 HTTP 运行不冒充容器隔离。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from poc.harbor_export.prepare import prepare
from poc.harbor_export.collect import collect
from poc.harbor_export.grader import grade
from poc.harbor_export.check_results import check, EXPECTED

IMAGE = 'python@sha256:' + 'a' * 64


class HarborExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prepared = self.root / 'prepared'
        self.manifest = prepare(self.prepared, IMAGE)

    def results(self):
        job = self.root / 'job'
        for name, expected in EXPECTED.items():
            trial = job / name
            (trial / 'verifier').mkdir(parents=True)
            (trial / 'result.json').write_text(json.dumps({
                'task_name': name, 'finished_at': '2026-10-31T00:00:00Z',
                'verifier_environment_mode': 'separate', 'exception_info': None,
                'agent_info': {'name': 'oracle'}, 'config': {'environment': {'type': 'docker'}},
                'verifier_result': {'rewards': {'reward': expected}},
            }))
            (trial / 'verifier/boundary.json').write_text(json.dumps({
                'run_id': self.manifest['run_id'], 'passed': bool(expected)}))
        return job

    def test_task_context_does_not_include_grader(self):
        for task in (self.prepared / 'tasks').iterdir():
            self.assertFalse((task / 'environment/tests').exists())
            self.assertFalse(list((task / 'environment').rglob('grader.py')))
            self.assertIn('environment_mode = "separate"', (task / 'task.toml').read_text())

    def test_real_http_reference_export_and_bad_export(self):
        for name, passes in (('reference', True), ('bad-export', False)):
            task = self.prepared / 'tasks' / name
            candidate = task / 'solution/candidate'
            (candidate / 'challenge.txt').write_text(self.manifest['run_id'])
            out = self.root / name
            collect(candidate, out)
            if passes:
                grade(out, self.manifest['run_id'])
                with self.assertRaises(ValueError):
                    grade(out, 'stale-run')
            else:
                with self.assertRaises(ValueError):
                    grade(out, self.manifest['run_id'])

    def test_complete_synthetic_native_result_shape_passes(self):
        self.assertEqual(check(self.prepared, self.results())['status'], 'PASS')

    def test_infra_failure_is_not_a_successful_negative(self):
        job = self.results()
        p = job / 'bad-export/result.json'
        data = json.loads(p.read_text())
        data['exception_info'] = {'exception_type': 'BuildError'}
        p.write_text(json.dumps(data))
        self.assertEqual(check(self.prepared, job)['status'], 'FAIL')

    def test_shared_verifier_stale_run_and_fake_reward_are_rejected(self):
        job = self.results()
        p = job / 'gate-tamper/result.json'
        original = json.loads(p.read_text())
        for field, value in (('verifier_environment_mode', 'shared'), ('verifier_result', {'rewards': {'reward': 1}})):
            data = copy.deepcopy(original)
            data[field] = value
            p.write_text(json.dumps(data))
            self.assertEqual(check(self.prepared, job)['status'], 'FAIL')
        p.write_text(json.dumps(original))
        b = job / 'reference/verifier/boundary.json'
        b.write_text(json.dumps({'run_id': 'old', 'passed': True}))
        self.assertEqual(check(self.prepared, job)['status'], 'FAIL')

    def test_missing_trial_and_modified_grader_are_blocked(self):
        job = self.results()
        (job / 'reference/result.json').unlink()
        with self.assertRaises(ValueError):
            check(self.prepared, job)
        grader = self.prepared / 'tasks/reference/tests/grader.py'
        grader.write_text('print("fake")')
        with self.assertRaises(ValueError):
            check(self.prepared, job)

    def test_floating_image_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.root / 'floating', 'python:latest')


if __name__ == '__main__':
    unittest.main()
