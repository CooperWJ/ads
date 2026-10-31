"""M1 independent-source discovery: behavior tests and deliberate omissions."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discovery.sources import collect, SourceError
from discovery.audit import audit, load_and_audit

RAW=ROOT/'fixtures/project_board/raw'
REVIEW=json.loads((ROOT/'evaluator/source_review.json').read_text())
BASE={x['id'] for x in json.loads((ROOT/'evaluator/raw_obligations.json').read_text())['obligations']}

class MultiSourceDiscoveryTests(unittest.TestCase):
    def test_real_excel_multi_sheet_and_formula_extraction(self):
        inventory=collect(RAW)
        self.assertEqual(inventory['source_count'],4)
        self.assertEqual(inventory['unit_count'],44)
        data=next(x for x in inventory['sources'] if x['source'].endswith('.xlsx'))
        self.assertEqual([s['sheet'] for s in data['meta']['sheets']],['Fields','Actions','Examples'])
        self.assertEqual(data['meta']['formulas'],1)
        self.assertEqual(next(x for x in inventory['units'] if x['locator']=='Examples!R2')['contains_formula'],True)
        self.assertIn('C2==A2+B2', next(x for x in inventory['units'] if x['locator']=='Examples!R2')['text'])

    def test_independent_review_detects_new_unverified_obligations(self):
        report=audit(RAW,REVIEW,BASE)
        self.assertEqual(report['status'],'GAP')
        self.assertEqual(report['reviewed_units'],44)
        self.assertEqual(report['new_unverified_obligations'],['menu-route-accessible','page-error-state'])

    def test_omitted_new_page_error_is_not_a_satisfied_delivery(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if '/L6' in x['decision_ref'] and 'prd.md' in x['decision_ref'])
        row['disposition']='CONTEXT';row['obligations']=[]
        with self.assertRaisesRegex(SourceError,'requires rationale'):
            audit(RAW,review,BASE)

    def test_whole_prd_bullet_removed_from_review_is_blocked(self):
        review=copy.deepcopy(REVIEW)
        review['decisions']=[x for x in review['decisions'] if 'prd.md/L6' not in x['decision_ref']]
        with self.assertRaisesRegex(SourceError,'unreviewed or phantom'):
            audit(RAW,review,BASE)

    def test_forged_source_fragment_is_rejected(self):
        review=copy.deepcopy(REVIEW)
        review['decisions'][0]['text_sha256']='0'*64
        with self.assertRaisesRegex(SourceError,'source fragment changed'):
            audit(RAW,review,BASE)

    def test_review_must_not_auto_promote_missing_coverage(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if 'prd.md/L6' in x['decision_ref'])
        row['disposition']='REQUIRED';row['obligations']=['page-error-state']
        self.assertIn('page-error-state',audit(RAW,review,BASE)['new_unverified_obligations'])

    def test_source_modified_after_review_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);shutil.copytree(RAW,target/'raw')
            file=target/'raw/prd.md';file.write_text(file.read_text()+'\n- A new required user action.\n')
            with self.assertRaisesRegex(SourceError,'source hash drift'):
                audit(target/'raw',REVIEW,BASE)

    def test_new_file_not_in_review_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);shutil.copytree(RAW,target/'raw')
            (target/'raw/new-screen.md').write_text('## New screen\n- New button required.\n')
            with self.assertRaisesRegex(SourceError,'source inventory'):
                audit(target/'raw',REVIEW,BASE)

    def test_unsupported_or_unreadable_document_cannot_count_as_zero(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);shutil.copytree(RAW,target/'raw')
            (target/'raw/unreadable.pdf').write_bytes(b'%PDF-1.7\n')
            with self.assertRaisesRegex(SourceError,'unreadable source type'):
                collect(target/'raw')

    def test_corrupted_xlsx_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);shutil.copytree(RAW,target/'raw')
            (target/'raw/data_dictionary.xlsx').write_bytes(b'not-a-zip')
            with self.assertRaisesRegex(SourceError,'unreadable XLSX'):
                collect(target/'raw')

    def test_removed_entire_excel_source_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);shutil.copytree(RAW,target/'raw')
            (target/'raw/data_dictionary.xlsx').unlink()
            with self.assertRaisesRegex(SourceError,'source inventory'):
                audit(target/'raw',REVIEW,BASE)

    def test_visible_field_cannot_be_dismissed_as_context(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if 'wireframe.svg/text[10]' in x['decision_ref'])
        row['disposition']='CONTEXT';row['obligations']=[]
        with self.assertRaisesRegex(SourceError,'SVG visible label'):
            audit(RAW,review,BASE)

    def test_required_unit_without_obligation_is_invalid(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if 'prd.md/L6' in x['decision_ref'])
        row['obligations']=[]
        with self.assertRaisesRegex(SourceError,'required fragments must map'):
            audit(RAW,review,BASE)

    def test_exclusion_needs_independent_reason(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if 'prd.md/L6' in x['decision_ref'])
        row['disposition']='EXCLUDED';row['obligations']=[]
        with self.assertRaisesRegex(SourceError,'requires rationale'):
            audit(RAW,review,BASE)

    def test_same_input_produces_stable_unit_ids(self):
        a,b=collect(RAW),collect(RAW)
        self.assertEqual([x['id'] for x in a['units']],[x['id'] for x in b['units']])

    def test_readonly_cli_is_nonzero_when_unverified_scope_exists(self):
        result=subprocess.run([sys.executable,'-m','discovery.cli'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['status'],'GAP')

    def test_inventory_only_not_claim_full_coverage(self):
        result=subprocess.run([sys.executable,'-m','discovery.cli','--inventory-only'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema'],'ads-source-discovery/v1')
        self.assertNotIn('status',json.loads(result.stdout))

    def test_evaluator_keeps_profile_and_new_delivery_gap_separate(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('ads_grade_v040',ROOT/'evaluator/grade.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            report=module.evaluate(ROOT/'fixtures/project_board/patches/reference.patch','backend','pass','current',td)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['source_discovery']['status'],'GAP')
        self.assertEqual(report['delivery_verdict']['status'],'NOT_VERIFIED')
        self.assertIn('page-error-state',report['delivery_verdict']['m1_unverified_new_obligations'])

if __name__=='__main__':unittest.main()

class SourceDimensionTests(unittest.TestCase):
    def test_gap_is_only_coverage_of_acceptance_not_unread_files(self):
        report=audit(RAW,REVIEW,BASE)
        self.assertEqual(report['coverage_dimensions']['material_inventory'],'PASS')
        self.assertEqual(report['coverage_dimensions']['source_extraction'],'PASS')
        self.assertEqual(report['coverage_dimensions']['source_decisions'],'PASS')
        self.assertEqual(report['coverage_dimensions']['accepted_obligation_verification'],'GAP')

    def test_formula_example_cannot_silently_become_approved_rule(self):
        review=copy.deepcopy(REVIEW)
        row=next(x for x in review['decisions'] if 'Examples!R2' in x['decision_ref'])
        self.assertEqual(row['disposition'],'CONTEXT')
        self.assertIn('not an approved oracle',row['reason'])
        row.pop('reason')
        with self.assertRaisesRegex(SourceError,'requires rationale'):
            audit(RAW,review,BASE)
