"""原生调用适配回归；真实子进程不代表真实模型执行。"""
import io
import json
import os
from contextlib import redirect_stdout
import unittest

import test_ads_core
from ads import engineering
from ads.cli import main
from ads.project import Project, write_json


@unittest.skipUnless(os.name == 'posix', '可执行脚本需要 POSIX')
class DevelopExecutionTests(unittest.TestCase):
    setUp = test_ads_core.CoreTests.setUp

    def configure(self, body, timeout=10):
        native = self.root / 'native-stub'
        native.write_text('#!/usr/bin/env python3\n' + body)
        native.chmod(0o700)
        (self.root / 'TASK.md').write_text('虚构任务，仅校准执行适配。')
        config = self.project.config
        config['development'] = {'executable': str(native), 'timeout_seconds': timeout}
        write_json(self.root / 'ads.project.json', config)
        project = Project(self.root)
        engineering.context(project, freeze=True)
        return project

    def test_cli_runs_native_once_and_persists_unverified_summary(self):
        self.configure('''import json, sys
from pathlib import Path
assert sys.argv[1:4] == ['run', '--standalone', '--model']
assert sys.argv[4] == 'synthetic/model'
marker = Path('.ads/native-attempts')
marker.write_text(marker.read_text() + '1' if marker.exists() else '1')
print(json.dumps({'type': 'step_finish', 'sessionID': 'synthetic-session'}))
''')
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['--root', str(self.root), 'develop', '--model', 'synthetic/model', '--execute'])
        self.assertEqual(code, 0, output.getvalue())
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'EXECUTED_UNVERIFIED')
        self.assertEqual(report['completion'], 'NOT_VERIFIED')
        self.assertEqual(report['native_sessions_observed'], 1)
        self.assertEqual((self.root / '.ads/native-attempts').read_text(), '1')
        summaries = list((self.root / '.ads/development').glob('*/summary.json'))
        self.assertEqual(len(summaries), 1)
        self.assertEqual(json.loads(summaries[0].read_text()), report)

    def test_native_failure_is_recorded_and_blocked(self):
        project = self.configure('import sys\nsys.exit(7)\n')
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['exit_code'], 7)

    def test_native_timeout_is_recorded_and_blocked(self):
        project = self.configure('import time\ntime.sleep(30)\n', timeout=1)
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['error_type'], 'TIMEOUT')

    def test_plan_does_not_launch_native(self):
        project = self.configure("raise RuntimeError('不应启动')\n")
        self.assertEqual(engineering.develop(project, 'synthetic/model')['status'], 'PLANNED')
        self.assertFalse((self.root / '.ads/development').exists())
