"""M1 end-to-end gap closure; reference must work, broken user journeys must fail."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ads_v050_grade',ROOT/'evaluator/grade.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)

class M1AcceptanceTests(unittest.TestCase):
    def evaluate(self,name='reference_m1',profile='integration',m1=True):
        with tempfile.TemporaryDirectory() as td:
            return G.evaluate(ROOT/'fixtures/project_board/patches'/f'{name}.patch',profile,'pass','current',td,m1_enabled=m1)

    def test_new_reference_passes_actual_http_and_node_journey(self):
        result=self.evaluate()
        self.assertEqual(result['status'],'PASS')
        checks={x['check']:x['status'] for x in result['checks']}
        for name in ('menu_route_accessible','error_accessibility','request_error_state'):
            self.assertEqual(checks[name],'PASS')
        self.assertEqual(result['source_discovery']['acceptance_closure']['status'],'NOT_VERIFIED')
        self.assertEqual(result['delivery_verdict']['status'],'NOT_VERIFIED')
        self.assertCountEqual(result['delivery_verdict']['m1_unverified_new_obligations'],
                              ['menu-route-accessible','page-error-state'])
        self.assertEqual(result['delivery_verdict']['total'],20)

    def test_deleted_menu_detected(self):
        result=self.evaluate('m1_missing_menu')
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('menu-route-accessible',[x['id'] for x in result['delivery_verdict']['obligations'] if x['status']=='FAIL'])

    def test_hidden_http_error_detected(self):
        result=self.evaluate('m1_silent_error')
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('page-error-state',[x['id'] for x in result['delivery_verdict']['obligations'] if x['status']=='FAIL'])

    def test_old_reference_cannot_satisfy_new_requirements(self):
        result=self.evaluate('reference')
        self.assertEqual(result['status'],'FAIL')

    def test_old_m0_fixture_unchanged_without_optin(self):
        result=self.evaluate('reference',profile='backend',m1=False)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['source_discovery']['status'],'GAP')
        self.assertEqual(result['delivery_verdict']['total'],18)

    def test_backend_only_cannot_validate_m1_failure_state(self):
        result=self.evaluate(profile='backend')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['delivery_verdict']['status'],'NOT_VERIFIED')
        checks={x['id']:x['status'] for x in result['delivery_verdict']['obligations']}
        self.assertEqual(checks['page-error-state'],'NOT_VERIFIED')

    def test_missing_acceptance_obligation_rejected(self):
        d=json.loads((ROOT/'evaluator/m1_acceptance.json').read_text());d['obligations'].pop()
        original=Path.read_text
        def edited(path,*args,**kwargs):
            if str(path).endswith('/evaluator/m1_acceptance.json'):
                return json.dumps(d)
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',edited):
            with self.assertRaisesRegex(G.CheckFailure,'both M1 requirements'):
                self.evaluate()

    def test_disabled_browser_does_not_claim_complete_delivery(self):
        result=self.evaluate(profile='integration')
        self.assertNotEqual(result['delivery_verdict']['status'],'PASS')
        result2=self.evaluate(profile='backend')
        self.assertNotEqual(result2['delivery_verdict']['status'],'PASS')

    def test_require_delivery_rejects_node_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=subprocess.run([sys.executable,str(ROOT/'evaluator/grade.py'),'--candidate','reference_m1',
                              '--profile','integration','--acceptance-bundle','m1',
                              '--require-delivery','--out',td],capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stderr)
            data=json.loads(p.stdout)
            self.assertEqual(data['status'],'PASS')
            self.assertEqual(data['delivery_verdict']['status'],'NOT_VERIFIED')

    def test_legacy_source_review_not_tampered(self):
        result=self.evaluate()
        self.assertEqual(result['source_discovery']['new_unverified_obligations'],
                         ['menu-route-accessible','page-error-state'])
        self.assertEqual(result['m1_acceptance_sha256'],G.sha256(ROOT/'evaluator/m1_acceptance.json'))

if __name__=='__main__':unittest.main()
