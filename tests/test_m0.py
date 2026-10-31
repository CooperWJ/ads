"""Deterministic unit and process-level tests for the trust boundary (not a sandbox)."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'evaluator/grade.py'
spec=importlib.util.spec_from_file_location('ads_grade',MODULE)
grade=importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade)

class GraderTests(unittest.TestCase):
    def test_frozen_base_digest(self):
        self.assertEqual(grade.tree_digest(ROOT/'fixtures/project_board/base'),
                         json.loads((ROOT/'fixtures/project_board/case.json').read_text())['base_tree_sha256'])

    def test_reference_patch_whitelist(self):
        path=ROOT/'fixtures/project_board/patches/reference.patch'
        self.assertEqual(grade.validate_patch(path),['app.py'])

    def test_patch_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            attack=Path(temp)/'attack.patch'
            attack.write_text('--- a/../evaluator/grade.py\n+++ b/../evaluator/grade.py\n@@ -1 +1 @@\n-no\n+yes\n')
            with self.assertRaises(grade.CheckFailure):grade.validate_patch(attack)

    def test_patch_cannot_modify_test_script(self):
        with tempfile.TemporaryDirectory() as temp:
            attack=Path(temp)/'attack.patch'
            attack.write_text('--- a/tests/test_m0.py\n+++ b/tests/test_m0.py\n@@ -1 +1 @@\n-no\n+yes\n')
            with self.assertRaises(grade.CheckFailure):grade.validate_patch(attack)

    def test_missing_qa_is_blocked(self):
        for kind in ('pending','failed'):
            with self.subTest(kind=kind):
                with self.assertRaises(grade.CheckFailure):grade.check_qa(kind)

    def test_stale_evidence_rejected(self):
        with self.assertRaises(grade.CheckFailure):grade.check_evidence('stale','f'*64)

    def test_malformed_xlsx_rejected(self):
        with self.assertRaises(Exception):grade.read_xlsx(b'this is not a zip archive')

    def test_xlsx_reads_with_independent_excel_library(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest('optional independent openpyxl XLSX parser not installed')
        import io
        app_path=ROOT/'fixtures/project_board/base/app.py'
        module_spec=importlib.util.spec_from_file_location('synthetic_app',app_path)
        app=importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(app)
        payload=app.xlsx_bytes({key:'Example' for key in app.COLUMN_NAMES})
        workbook=openpyxl.load_workbook(io.BytesIO(payload),read_only=True)
        self.assertEqual(list(next(workbook.active.values)),list(app.COLUMN_NAMES))
        self.assertEqual(len(list(workbook.active.values)),2)

    def test_reference_backend_process_passes(self):
        with tempfile.TemporaryDirectory() as out:
            proc=subprocess.run([sys.executable,str(MODULE),'--candidate','reference','--out',out],capture_output=True,text=True,timeout=20)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            report=json.loads((Path(out)/'grade.json').read_text())
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(len(report['checks']),6)

    def test_empty_patch_fails(self):
        with tempfile.TemporaryDirectory() as out:
            proc=subprocess.run([sys.executable,str(MODULE),'--candidate','empty','--out',out],capture_output=True,text=True,timeout=20)
            self.assertEqual(proc.returncode,1,proc.stdout+proc.stderr)
            report=json.loads((Path(out)/'grade.json').read_text())
            self.assertEqual(report['status'],'FAIL')
            self.assertEqual(next(c for c in report['checks'] if c['check']=='api_contract')['status'],'FAIL')

    def test_no_unauthorized_grader_patch(self):
        with tempfile.TemporaryDirectory() as out:
            attack=Path(out)/'attack.patch'
            attack.write_text('--- a/evaluator/grade.py\n+++ b/evaluator/grade.py\n@@ -1 +1 @@\n-no\n+yes\n')
            proc=subprocess.run([sys.executable,str(MODULE),'--candidate',str(attack),'--out',out],capture_output=True,text=True,timeout=20)
            self.assertEqual(proc.returncode,1,proc.stdout+proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['status'],'REJECTED')

if __name__=='__main__':unittest.main()
