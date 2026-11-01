"""原生调用适配回归；真实子进程不代表真实模型执行。"""
import io
import json
import os
import signal
import threading
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

    def test_behavior_evidence_is_projected_into_run_summary(self):
        project = self.configure('''import json
print(json.dumps({'type':'tool_use','sessionID':'ses_synthetic','part':{
 'type':'tool','tool':'skill','state':{'status':'completed','input':{'name':'systematic-debugging'},'metadata':{'exit':0}}}}))
''')
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['behavior_evidence']['systematic_debugging_invoked'], 'OBSERVED')
        evidence = next((self.root / '.ads/development').glob('*/behavior.json'))
        self.assertEqual(json.loads(evidence.read_text()), result['behavior_evidence'])

    def test_verification_binds_exact_development_and_behavior_artifacts(self):
        project = self.configure('''import json
print(json.dumps({'type':'tool_use','part':{'type':'tool','tool':'skill',
 'state':{'status':'completed','input':{'name':'test-driven-development'},'metadata':{'exit':0}}}}))
print(json.dumps({'type':'step_finish','part':{'reason':'stop'}}))
''')
        development = engineering.develop(project, 'synthetic/model', execute=True)
        run = test_ads_core.evidence.run_checks(project)
        binding = run['development_binding']
        self.assertEqual(binding['status'], 'MATCHED')
        self.assertEqual(binding['run_id'], development['run_id'])
        self.assertEqual(binding['behavior_sha256'], development['behavior_sha256'])
        self.assertEqual(test_ads_core.evidence.load_current(project)['development_binding'], binding)
        self.assertEqual(test_ads_core.evidence.decide(project)['development_binding'], binding)

    def test_cli_verify_exposes_development_binding(self):
        project = self.configure("pass\\n")
        engineering.develop(project, 'synthetic/model', execute=True)
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['--root', str(self.root), 'verify'])
        self.assertEqual(code, 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['development_binding']['status'], 'MATCHED')

    def test_verification_marks_development_stale_when_code_changed_after_run(self):
        project = self.configure("pass\\n")
        development = engineering.develop(project, 'synthetic/model', execute=True)
        with (self.root / 'app.py').open('a') as source:
            source.write('\\n# changed after native development\\n')
        run = test_ads_core.evidence.run_checks(project)
        self.assertEqual(run['status'], 'PASS')
        self.assertEqual(run['development_binding']['status'], 'STALE')
        self.assertEqual(run['development_binding']['run_id'], development['run_id'])

    def test_tampered_behavior_artifact_invalidates_bound_verification(self):
        project = self.configure("pass\\n")
        engineering.develop(project, 'synthetic/model', execute=True)
        run = test_ads_core.evidence.run_checks(project)
        behavior = self.root / '.ads' / 'development' / run['development_binding']['run_id'] / 'behavior.json'
        behavior.write_text('{}')
        with self.assertRaises(test_ads_core.Blocked):
            test_ads_core.evidence.load_current(project)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions only')
    def test_raw_native_evidence_is_private_to_current_user(self):
        project = self.configure("print('{}')\\n")
        engineering.develop(project, 'synthetic/model', execute=True)
        directory = next((self.root / '.ads/development').iterdir())
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((directory / 'native-private.jsonl').stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory / 'stderr-private.log').stat().st_mode & 0o777, 0o600)

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

    def test_explicit_session_is_forwarded_to_native_once(self):
        project = self.configure('''import sys,json
assert sys.argv[sys.argv.index('--session')+1] == 'ses_synthetic'
print(json.dumps({'type':'step_finish','sessionID':'ses_synthetic'}))
''')
        result = engineering.develop(project, 'synthetic/model', execute=True, session='ses_synthetic')
        self.assertEqual(result['session_id'], 'ses_synthetic')
        self.assertEqual(result['requested_session'], 'ses_synthetic')
        self.assertFalse(result['automatic_side_effect_replay'])

    def test_interrupt_persists_receipt_after_process_cleanup(self):
        project = self.configure('import time\ntime.sleep(30)\n')
        timer = threading.Timer(.3, lambda: os.kill(os.getpid(), signal.SIGINT))
        timer.start()
        try:
            result = engineering.develop(project, 'synthetic/model', execute=True)
        finally:
            timer.cancel()
        self.assertEqual(result['error_type'], 'INTERRUPTED')
        summary = next((self.root / '.ads/development').glob('*/summary.json'))
        self.assertEqual(json.loads(summary.read_text())['status'], 'BLOCKED')

    def test_native_corrupting_authority_keeps_failure_summary(self):
        project = self.configure("from pathlib import Path\nPath('contract.json').write_text('invalid JSON')\n")
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['error_type'], 'CONTEXT_UNREADABLE')
        self.assertIsNone(result['output_subject'])
        self.assertFalse(result['authority_unchanged'])

    def test_non_object_native_error_is_not_lost(self):
        project = self.configure('print(\'{"type":"error","error":"synthetic failure"}\')\n')
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['error_type'], 'NATIVE_ERROR')
        self.assertEqual(result['status'], 'BLOCKED')

    def test_native_stream_error_name_is_preserved(self):
        project = self.configure('''import json
print(json.dumps({'type':'error','error':{'name':'APIError','data':{'message':'rate limited','statusCode':429}}}))
''')
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['error_type'], 'APIError')
        self.assertEqual(result['status'], 'BLOCKED')

    def test_executable_start_error_is_recorded(self):
        project = self.configure('pass\n')
        (self.root / 'native-stub').write_text('not an executable format')
        engineering.context(project, freeze=True)
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['error_type'], 'EXECUTION_ERROR')
        self.assertEqual(result['status'], 'BLOCKED')
