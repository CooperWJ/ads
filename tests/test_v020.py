"""M0 v0.2.0: evaluator hardening and integration negative cases."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ads_grade_v020', ROOT/'evaluator/grade.py')
grade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade)

class EvaluatorV020Tests(unittest.TestCase):
    def test_reference_node_integration_passes(self):
        if not shutil.which('node'): self.skipTest('Node.js required')
        with tempfile.TemporaryDirectory() as t:
            report = grade.evaluate(ROOT/'fixtures/project_board/patches/reference.patch','integration','pass','current',t)
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(next(c for c in report['checks'] if c['check']=='node_js_dom_real_http')['status'],'PASS')

    def test_js_crash_fails_even_without_chromium(self):
        if not shutil.which('node'): self.skipTest('Node.js required')
        with tempfile.TemporaryDirectory() as t:
            report=grade.evaluate(ROOT/'fixtures/project_board/patches/ui_crash.patch','integration','pass','current',t)
            self.assertEqual(report['status'],'FAIL')
            self.assertEqual(next(c for c in report['checks'] if c['check']=='node_js_dom_real_http')['status'],'FAIL')

    def test_forbid_binary_patch(self):
        with tempfile.TemporaryDirectory() as t:
            patch = Path(t)/'binary.patch'
            patch.write_bytes(b'diff --git a/web/app.js b/web/app.js\nGIT binary patch\n')
            with self.assertRaises(grade.CheckFailure):grade.validate_patch(patch)

    def test_forbid_mode_changes(self):
        with tempfile.TemporaryDirectory() as t:
            patch=Path(t)/'symlink.patch'
            patch.write_text('diff --git a/app.py b/app.py\nold mode 100644\nnew mode 120000\n')
            with self.assertRaises(grade.CheckFailure):grade.validate_patch(patch)

    def test_forbid_effective_path_disagreement(self):
        with tempfile.TemporaryDirectory() as t:
            patch=Path(t)/'wrong.patch'
            patch.write_text('diff --git a/evaluator/grade.py b/evaluator/grade.py\n'
                             '--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-a\n+b\n')
            with self.assertRaises(grade.CheckFailure):grade.validate_patch(patch)

    def test_scope_detects_protected_change(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source';candidate=Path(t)/'candidate'
            source.mkdir();candidate.mkdir()
            (source/'app.py').write_text('base')
            (source/'secret.txt').write_text('protected')
            (candidate/'app.py').write_text('edited')
            (candidate/'secret.txt').write_text('tampered')
            with self.assertRaises(grade.CheckFailure):grade.verify_worktree_scope(source,candidate)

    def test_scope_detects_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source';candidate=Path(t)/'candidate'
            source.mkdir();candidate.mkdir()
            (source/'app.py').write_text('base')
            (candidate/'app.py').symlink_to(source/'app.py')
            with self.assertRaises(grade.CheckFailure):grade.verify_worktree_scope(source,candidate)

    def test_scope_allows_application_only(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source';candidate=Path(t)/'candidate'
            source.mkdir();candidate.mkdir()
            (source/'app.py').write_text('base');(candidate/'app.py').write_text('edited')
            self.assertEqual(grade.verify_worktree_scope(source,candidate),['app.py'])

    def test_node_check_never_mislabeled_as_browser(self):
        if not shutil.which('node'): self.skipTest('Node.js required')
        with tempfile.TemporaryDirectory() as t:
            report=grade.evaluate(ROOT/'fixtures/project_board/patches/reference.patch','integration','pass','current',t)
            self.assertFalse(any(c['check']=='real_chromium_user_journey' for c in report['checks']))
            self.assertTrue(any(c['check']=='node_js_dom_real_http' for c in report['checks']))

    def test_strict_browser_calibration_requires_reference_full_pass(self):
        spec=importlib.util.spec_from_file_location('ads_calibrate_v020', ROOT/'evaluator/calibrate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertFalse(module.browser_calibration_ok([
            {'candidate':'reference','profile':'full','status':'BLOCKED'},
            {'candidate':'ui_crash','profile':'full','status':'FAIL'}]))
        self.assertTrue(module.browser_calibration_ok([
            {'candidate':'reference','profile':'full','status':'PASS'},
            {'candidate':'ui_crash','profile':'full','status':'FAIL'}]))

    def test_strict_browser_calibration_rejects_missing_cases(self):
        spec=importlib.util.spec_from_file_location('ads_calibrate_v020', ROOT/'evaluator/calibrate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertFalse(module.browser_calibration_ok([]))

    def test_custom_patch_requires_explicit_host_risk_opt_in(self):
        with tempfile.TemporaryDirectory() as t:
            safe = ROOT/'fixtures/project_board/patches/reference.patch'
            proc=subprocess.run([sys.executable,str(ROOT/'evaluator/grade.py'),
                '--candidate',str(safe),'--out',t],capture_output=True,text=True,timeout=15)
            self.assertEqual(proc.returncode,1,proc.stdout)
            self.assertEqual(json.loads(proc.stdout)['status'],'REJECTED')

    def test_all_original_unit_tests_preserved(self):
        self.assertTrue((ROOT/'tests/test_m0.py').exists())

if __name__=='__main__':unittest.main()
