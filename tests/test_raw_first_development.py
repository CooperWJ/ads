"""原始资料先启动开发；缺少确认契约不能借用开发记录完成验收。"""
import os
import unittest

import test_ads_core
from ads import engineering, evidence
from ads.cli import init, main
from contextlib import redirect_stdout
import io
import json
from ads.project import Project, Blocked, write_json


class RawFirstTests(unittest.TestCase):
    setUp = test_ads_core.CoreTests.setUp

    def raw_project(self):
        (self.root / 'contract.json').unlink()
        config = self.project.config
        config.update(spec_root='openspec/specs', verification_map='mapping.json')
        write_json(self.root / 'ads.project.json', config)
        return Project(self.root)

    def test_missing_authority_allows_context_but_never_verification(self):
        project = self.raw_project()
        engineering.context(project, freeze=True)
        self.assertEqual(engineering.context(project)['status'], 'CURRENT')
        with self.assertRaises(Blocked):
            evidence.run_checks(project)
        with self.assertRaises(Blocked):
            project.snapshot()
        (self.root / 'mapping.json').write_text('{}')
        self.assertEqual(engineering.context(project)['status'], 'REPLAN_REQUIRED')

    @unittest.skipUnless(os.name == 'posix', '真实可执行脚本')
    def test_raw_inputs_can_reach_native_process_without_contract(self):
        project = self.raw_project()
        native = self.root / 'native-stub'
        native.write_text('#!/usr/bin/env python3\nprint(\'{"type":"step_finish"}\')\n')
        native.chmod(0o700)
        (self.root / 'TASK.md').write_text('从原始资料探索虚构功能')
        project.config['development'] = {'executable': str(native), 'timeout_seconds': 5}
        write_json(self.root / 'ads.project.json', project.config)
        project = Project(self.root)
        engineering.context(project, freeze=True)
        result = engineering.develop(project, 'synthetic/model', execute=True)
        self.assertEqual(result['status'], 'EXECUTED_UNVERIFIED')
        self.assertEqual(result['completion'], 'NOT_VERIFIED')

    def test_init_keeps_existing_task(self):
        target = self.root / 'new-project'
        target.mkdir()
        (target / 'TASK.md').write_text('用户的任务')
        init(target)
        self.assertEqual((target / 'TASK.md').read_text(), '用户的任务')

    def test_qa_quality_import_does_not_require_contract(self):
        project = self.raw_project()
        (self.root / 'qa.csv').write_text('用例名称,操作步骤,预期结果\n去空格,输入文本,两侧无空格\n')
        project.config['qa'] = {'source': 'qa.csv'}
        write_json(self.root / 'ads.project.json', project.config)
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['--root', str(self.root), 'qa', 'import'])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['quality'], 'VALID')
        self.assertEqual(report['requirement_reconciliation'], 'BLOCKED')
        self.assertEqual(report['approval'], 'NOT_GRANTED')
        self.assertEqual(len(report['cases']), 1)
        self.assertTrue((self.root / '.ads/qa-intake.json').exists())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--root', str(self.root), 'qa', 'evaluate']), 3)
