"""派生视图不漏整条规格；业务变化与机械来源重绑定分开。"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from test_ads_core import fixture
from ads import openspec, evidence
from ads.project import Project, Blocked, write_json

SPEC = '''# Specification
### Requirement: 标签规范化
系统必须移除两侧空格。
#### Scenario: 正常标签
- GIVEN 标签为 " x "
- WHEN 执行规范化
- THEN 返回 "x"
#### Scenario: 非空输出
- GIVEN 标签为 " x "
- WHEN 执行规范化
- THEN 输出非空
'''


class OpenSpecAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        project = fixture(self.root)
        specs = self.root/'openspec/specs/labels'
        specs.mkdir(parents=True)
        self.spec = specs/'spec.md'
        self.spec.write_text(SPEC)
        profile = project.config
        profile.update(spec_root='openspec/specs', verification_map='verification-map.json', contract='.ads/contract.json')
        write_json(self.root/'ads.project.json', profile)
        self.project = Project(self.root)
        cases = openspec.scenarios(self.project)
        self.mapping = {'schema':'ads-openspec-verification-map/v1',
                        'spec_inventory':openspec.inventory(self.project),
                        'scenario_semantics':{x['id']:x['semantic_sha256'] for x in cases},
                        'authority':{'reviewer':'synthetic','decision_ref':'synthetic-approved-design'},
                        'bindings':[{'source':c['sources'][0]['path'],'requirement':c['requirement'],
                                     'scenario':c['scenario'],'tests':[{'check':'unit','case':'Contract.'+name}]}
                                    for c,name in zip(cases,('test_normalize','test_nonempty'))]}
        write_json(self.root/'verification-map.json', self.mapping)

    def test_compile_then_execute_existing_professional_report(self):
        result = openspec.compile_contract(self.project)
        self.assertEqual(result['status'], 'COMPILED_DERIVED')
        self.assertFalse(result['approval_created'])
        self.assertEqual(len(self.project.contract()['obligations']), 2)
        run = evidence.run_checks(self.project)
        self.assertEqual(run['status'], 'PASS')
        decision = evidence.decide(self.project)
        self.assertEqual(decision['development'], 'DEV_VERIFIED_LOCAL')
        self.assertEqual(decision['verification_run_id'], run['run_id'])
        self.assertEqual(decision['verification_run_status'], 'PASS')
        self.assertEqual(len(decision['obligations']), 2)
        for obligation, scenario in zip(decision['obligations'], openspec.scenarios(self.project)):
            self.assertEqual(obligation['status'], 'PASS')
            self.assertEqual(obligation['requirement'], scenario['requirement'])
            self.assertEqual(obligation['scenario'], scenario['scenario'])
            self.assertEqual(obligation['sources'], scenario['sources'])
            self.assertEqual(len(obligation['verification_evidence']), 1)
            evidence_ref = obligation['verification_evidence'][0]
            self.assertEqual(evidence_ref['expected'], 'PASS')
            self.assertEqual(evidence_ref['observed'], 'PASS')
            self.assertEqual(evidence_ref['status'], 'PASS')
            self.assertEqual(evidence_ref['reference']['run_id'], run['run_id'])
            self.assertEqual(evidence_ref['reference']['subject_sha256'], run['subject']['sha256'])
            self.assertTrue(evidence_ref['reference']['report_sha256'])


    def test_failed_case_keeps_expected_result_and_exact_failed_report_reference(self):
        openspec.compile_contract(self.project)
        (self.root/'app.py').write_text('def normalize(value):\n    return value\n')
        run = evidence.run_checks(self.project)
        self.assertEqual(run['status'], 'FAIL')
        decision = evidence.decide(self.project)
        self.assertEqual(decision['development'], 'BLOCKED')
        failed = next(x for x in decision['obligations'] if x['id'] == openspec.scenarios(self.project)[0]['id'])
        ref = failed['verification_evidence'][0]
        self.assertEqual(ref['expected'], 'PASS')
        self.assertEqual(ref['observed'], 'FAIL')
        self.assertEqual(ref['status'], 'NOT_VERIFIED')
        self.assertEqual(ref['reference']['run_id'], run['run_id'])
        self.assertEqual(ref['reference']['report_sha256'], run['checks'][0]['report_sha256'])
        self.assertEqual(failed['verification_evidence'][1]['observed'], 'CHECK_FAILED')

    def test_missing_and_ambiguous_test_evidence_never_pass(self):
        openspec.compile_contract(self.project)
        run = evidence.run_checks(self.project)

        missing = copy.deepcopy(run)
        missing['checks'][0]['cases'] = []
        with patch('ads.evidence.load_current', return_value=missing):
            decision = evidence.decide(self.project)
        first = decision['obligations'][0]['verification_evidence'][0]
        self.assertEqual(first['observed'], 'MISSING')
        self.assertEqual(first['status'], 'NOT_VERIFIED')
        self.assertIsNone(first['reference'])
        self.assertEqual(decision['development'], 'BLOCKED')

        ambiguous = copy.deepcopy(run)
        ambiguous['checks'][0]['cases'].append(copy.deepcopy(ambiguous['checks'][0]['cases'][0]))
        with patch('ads.evidence.load_current', return_value=ambiguous):
            decision = evidence.decide(self.project)
        first = decision['obligations'][0]['verification_evidence'][0]
        self.assertEqual(first['observed'], 'AMBIGUOUS')
        self.assertEqual(first['status'], 'NOT_VERIFIED')
        self.assertIsNone(first['reference'])
        self.assertEqual(decision['development'], 'BLOCKED')

    def test_missing_whole_scenario_is_a_gap_not_empty_success(self):
        self.mapping['bindings'].pop()
        write_json(self.root/'verification-map.json', self.mapping)
        result = openspec.compile_contract(self.project)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(len(result['missing']), 1)
        self.assertFalse(result['contract_written'])

    def test_new_spec_invalidates_prior_view_even_before_recompile(self):
        openspec.compile_contract(self.project)
        extra = self.spec.parent/'new/spec.md'
        extra.parent.mkdir()
        extra.write_text('### Requirement: 新要求\n#### Scenario: 新场景\n- THEN 新行为\n')
        with self.assertRaises(Blocked):
            self.project.contract()
        with self.assertRaises(Blocked):
            openspec.compile_contract(self.project)

    def test_blank_line_rebinding_preserves_existing_decision(self):
        self.spec.write_text(SPEC.replace('#### Scenario:', '\n#### Scenario:'))
        self.assertEqual(openspec.compile_contract(self.project)['status'], 'COMPILED_DERIVED')
        self.assertEqual(self.project.contract()['authority'], self.mapping['authority'])

    def test_requirement_rule_change_requires_existing_review(self):
        self.spec.write_text(SPEC.replace('移除两侧空格', '保留两侧空格'))
        with self.assertRaises(Blocked):
            openspec.compile_contract(self.project)

    def test_requirement_without_scenario_cannot_be_dropped(self):
        self.spec.write_text(SPEC+'\n### Requirement: 未设计场景的要求\n系统必须报告未知。\n')
        with self.assertRaises(Blocked):
            openspec.scenarios(self.project)


if __name__ == '__main__':
    unittest.main()
