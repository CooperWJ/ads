"""M0 v0.3.0: fixture-specific completeness audit and fail-closed delivery verdict."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ads_grade_v030',ROOT/'evaluator/grade.py')
grade=importlib.util.module_from_spec(spec);spec.loader.exec_module(grade)
requirements=sys.modules['requirements']
RUBRIC=json.loads((ROOT/'evaluator/raw_obligations.json').read_text())
RAW=ROOT/'fixtures/project_board/raw'

class RawCompletenessTests(unittest.TestCase):
    def test_complete_svg_fixture_audited(self):
        result=requirements.audit_inventory(RAW,RUBRIC)
        self.assertEqual(result['source_svg_labels'],13)
        self.assertEqual(result['mapped_svg_labels'],13)
        self.assertEqual(result['obligations'],18)

    def test_omitted_whole_ui_obligation_fails_even_if_not_in_test_plan(self):
        changed=deepcopy(RUBRIC)
        changed['obligations']=[x for x in changed['obligations'] if x['id']!='export-xlsx']
        with self.assertRaisesRegex(requirements.ObligationError,'unmapped raw SVG labels'):
            requirements.audit_inventory(RAW,changed)

    def test_omitted_one_of_seven_attributes_fails(self):
        changed=deepcopy(RUBRIC)
        changed['obligations']=[x for x in changed['obligations'] if x['id']!='field-ref']
        with self.assertRaisesRegex(requirements.ObligationError,'Reference code'):
            requirements.audit_inventory(RAW,changed)

    def test_duplicate_mapping_not_allowed(self):
        changed=deepcopy(RUBRIC)
        changed['obligations'].append(deepcopy(changed['obligations'][0]))
        with self.assertRaisesRegex(requirements.ObligationError,'duplicate'):
            requirements.audit_inventory(RAW,changed)

    def test_unknown_orphan_source_cannot_be_accepted(self):
        changed=deepcopy(RUBRIC)
        changed['obligations'][0]['source_text']='Invisible invented element'
        with self.assertRaisesRegex(requirements.ObligationError,'source anchor missing'):
            requirements.audit_inventory(RAW,changed)

    def test_unknown_check_cannot_make_missing_test_look_passed(self):
        changed=deepcopy(RUBRIC)
        changed['obligations'][0]['checks']=['made_up_test']
        with self.assertRaisesRegex(requirements.ObligationError,'unknown check'):
            requirements.audit_inventory(RAW,changed)

    def test_cannot_disable_browser_requirement_for_visible_ui(self):
        changed=deepcopy(RUBRIC)
        changed['obligations'][0]['browser_required']=False
        with self.assertRaisesRegex(requirements.ObligationError,'cannot avoid real browser'):
            requirements.audit_inventory(RAW,changed)

    def test_adding_new_raw_svg_item_without_rubric_update_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)
            (target/'brief.md').write_bytes((RAW/'brief.md').read_bytes())
            src=(RAW/'wireframe.svg').read_text()
            (target/'wireframe.svg').write_text(src.replace('</svg>','<text>Missing a whole new control</text></svg>'))
            with self.assertRaisesRegex(requirements.ObligationError,'Missing a whole new control'):
                requirements.audit_inventory(target,RUBRIC)

    def test_missing_check_is_not_verified_not_pass(self):
        rows=[{'check':k,'status':'PASS'} for k in requirements.VERIFICATION_TYPES if k!='real_chromium_user_journey']
        report=requirements.adjudicate(RUBRIC,rows)
        self.assertEqual(report['status'],'NOT_VERIFIED')
        self.assertEqual(next(x for x in report['obligations'] if x['id']=='export-xlsx')['status'],'NOT_VERIFIED')

    def test_failed_browser_prevents_delivery_success(self):
        rows=[{'check':k,'status':'PASS'} for k in requirements.VERIFICATION_TYPES]
        rows=[dict(x,status='FAIL') if x['check']=='real_chromium_user_journey' else x for x in rows]
        report=requirements.adjudicate(RUBRIC,rows)
        self.assertEqual(report['status'],'FAIL')

    def test_all_requirements_pass_only_with_all_required_check_results(self):
        rows=[{'check':k,'status':'PASS'} for k in requirements.VERIFICATION_TYPES]
        report=requirements.adjudicate(RUBRIC,rows)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['passed'],18)

    def test_backend_reference_pass_not_mislabeled_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=grade.evaluate(ROOT/'fixtures/project_board/patches/reference.patch','backend','pass','current',tmp)
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(report['raw_source_inventory']['status'],'PASS')
            self.assertEqual(report['delivery_verdict']['status'],'NOT_VERIFIED')
            self.assertEqual(report['delivery_verdict']['total'],18)

    def test_strict_cli_refuses_to_grant_delivery_without_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(ROOT/'evaluator/grade.py'),'--candidate','reference',
                '--profile','backend','--require-delivery','--out',tmp],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,2,result.stderr)
            report=json.loads((Path(tmp)/'grade.json').read_text())
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(report['delivery_verdict']['status'],'NOT_VERIFIED')

    def test_real_bad_variant_reports_failed_obligations(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=grade.evaluate(ROOT/'fixtures/project_board/patches/missing_ui_field.patch','integration','pass','current',tmp)
            self.assertEqual(report['status'],'FAIL')
            self.assertEqual(report['delivery_verdict']['status'],'FAIL')
            self.assertIn('ui_structure',next(x for x in report['delivery_verdict']['obligations'] if x['id']=='field-ref')['missing_or_failed_checks'])

if __name__=='__main__':unittest.main()

class BriefCompletenessTests(unittest.TestCase):
    def test_all_brief_sentences_linked(self):
        audit=requirements.audit_inventory(RAW,RUBRIC)
        self.assertEqual(audit['brief_sentences'],6)

    def test_whole_business_sentence_cannot_disappear_from_rubric(self):
        changed=deepcopy(RUBRIC)
        changed['brief_sentences']=[x for x in changed['brief_sentences'] if not x['text'].startswith('A viewer')]
        with self.assertRaisesRegex(requirements.ObligationError,'unmapped brief sentence count'):
            requirements.audit_inventory(RAW,changed)

    def test_brief_sentence_requires_existing_obligation(self):
        changed=deepcopy(RUBRIC)
        changed['obligations']=[x for x in changed['obligations'] if x['id']!='viewer-write-rejected']
        with self.assertRaisesRegex(requirements.ObligationError,'no valid obligation links'):
            requirements.audit_inventory(RAW,changed)

    def test_new_requirement_sentence_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp)
            (t/'wireframe.svg').write_bytes((RAW/'wireframe.svg').read_bytes())
            text=(RAW/'brief.md').read_text().replace('This is a fictional test case',
                'A new mandatory feature must be available.\n\nThis is a fictional test case')
            # This injection is in a new paragraph, so cannot be silently marked covered.
            (t/'brief.md').write_text(text)
            with self.assertRaisesRegex(requirements.ObligationError,'synthetic brief format|unmapped'):
                requirements.audit_inventory(t,RUBRIC)

class CrossCuttingAssuranceTests(unittest.TestCase):
    def test_qa_pending_invalidates_delivery_even_if_all_other_checks_pass(self):
        rows=[{'check':k,'status':'PASS'} for k in requirements.VERIFICATION_TYPES]
        rows=[dict(x,status='FAIL') if x['check']=='independent_qa' else x for x in rows]
        report=requirements.adjudicate(RUBRIC,rows)
        self.assertEqual(report['status'],'FAIL')
        self.assertIn('independent_qa',report['obligations'][0]['missing_or_failed_checks'])

    def test_stale_source_identity_invalidates_delivery(self):
        rows=[{'check':k,'status':'PASS'} for k in requirements.VERIFICATION_TYPES]
        rows=[dict(x,status='FAIL') if x['check']=='source_bound_evidence' else x for x in rows]
        report=requirements.adjudicate(RUBRIC,rows)
        self.assertEqual(report['status'],'FAIL')

    def test_protected_rubric_hash_in_real_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=grade.evaluate(ROOT/'fixtures/project_board/patches/reference.patch','backend','pass','current',tmp)
            self.assertEqual(report['protected_rubric_sha256'],grade.sha256(ROOT/'evaluator/raw_obligations.json'))
            self.assertEqual(report['delivery_verdict']['status'],'NOT_VERIFIED')
