"""切片输入与隔离适配：不使用参考解冒充真实 Agent 开发。"""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from poc.development_slice import workspace as W
from poc.development_slice import docker_grade as D
from evaluator import grade as G


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / 'run'
        W.prepare(self.run)
        self.work = self.run / 'workspace'

    def test_only_raw_seed_and_development_protocol_are_given(self):
        self.assertTrue((self.work / 'raw/data_dictionary.xlsx').is_file())
        for path in ('evaluator', 'patches', 'tests', 'discovery'):
            self.assertFalse((self.work / path).exists())
        with self.assertRaises(ValueError):
            W.export(self.run, Path(self.tmp.name) / 'empty')

    def test_committed_code_changes_are_exported_without_executing(self):
        source = self.work / 'app.py'
        source.write_text(source.read_text() + '\n# synthetic export fixture\n')
        W.git(self.work, 'add', 'app.py')
        W.git(self.work, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture edit')
        result = W.export(self.run, Path(self.tmp.name) / 'export')
        self.assertEqual(result['status'], 'EXPORTED')
        self.assertEqual(result['opencode_execution'], 'NOT_VERIFIED')
        self.assertTrue((Path(self.tmp.name) / 'export/candidate.patch').is_file())

    def test_raw_modification_cannot_be_exported(self):
        (self.work / 'raw/brief.md').write_text('changed expectation')
        with self.assertRaises(ValueError):
            W.export(self.run, Path(self.tmp.name) / 'export')

    def test_unauthorized_file_and_symlink_are_rejected(self):
        source = self.work / 'app.py'
        source.write_text(source.read_text() + '\n# fixture\n')
        extra = self.work / 'evaluator.py'
        extra.write_text('fake gate')
        with self.assertRaises(ValueError):
            W.export(self.run, Path(self.tmp.name) / 'extra')
        extra.unlink()
        source.unlink()
        source.symlink_to(self.work / 'TASK.md')
        with self.assertRaises(ValueError):
            W.export(self.run, Path(self.tmp.name) / 'symlink')


class RuntimeAdapterTests(unittest.TestCase):
    def test_missing_docker_never_falls_back_to_host_execution(self):
        with patch.object(D.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Docker'):
                with D.service(Path('/unused'), Path('/unused'), image='python@sha256:' + 'a' * 64):
                    self.fail('不能启动宿主候选')

    def test_existing_evaluator_uses_injected_service(self):
        observed = []
        @contextmanager
        def factory(work, out):
            observed.append(True)
            with G.service(work, out) as base:
                yield base
        with tempfile.TemporaryDirectory() as directory:
            result = G.evaluate(G.CASE / 'patches/reference_m1.patch', 'backend', 'pass', 'current', directory,
                                m1_enabled=True, service_factory=factory)
        self.assertEqual(observed, [True])
        self.assertEqual(result['status'], 'PASS')
        self.assertNotEqual(result['delivery_verdict']['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
