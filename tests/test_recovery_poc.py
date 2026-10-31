"""Disposable process/session recovery experiment: no business logic or credentials."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from poc import recovery_poc as P


class RecoveryPoCTests(unittest.TestCase):
    def setUp(self):
        self.baseline = patch.object(P, "_baseline", return_value={"commit": "x", "agents_sha256": "hash"})
        self.baseline.start()
        self.addCleanup(self.baseline.stop)
        self.run = P.init()["run_dir"]
        self.addCleanup(lambda: __import__("shutil").rmtree(self.run, ignore_errors=True))

    def export(self, session_id="ses_test", project="p1", tail=False):
        messages = [{"id": "m1", "type": "user", "text": "phase1"},
                    {"id": "m2", "type": "assistant", "content": [
                        {"type": "tool", "name": "shell", "state": {"status": "completed", "input": {"command": "python3 poc/recovery_poc.py apply /tmp/fictional"}}}]}]
        if tail:
            messages += [{"id": "m3", "type": "user", "text": "phase2"},
                         {"id": "m4", "type": "assistant", "content": [
                             {"type": "tool", "name": "shell", "state": {"status": "completed", "input": {"command": "python3 poc/recovery_poc.py verify /tmp/fictional"}}}]}]
        return {"info": {"id": session_id, "projectID": project}, "messages": messages}

    def test_disposable_effect_once(self):
        self.assertEqual(P.verify(self.run)["status"], "FAIL")
        self.assertEqual(P.apply(self.run)["status"], "APPLIED")
        self.assertEqual(P.verify(self.run)["status"], "PASS")

    def test_replay_is_observable_failure(self):
        P.apply(self.run)
        repeated = P.apply(self.run)
        self.assertEqual(repeated["status"], "REPEATED_APPLY")
        self.assertEqual(P.verify(self.run)["attempts"], 2)
        self.assertEqual(P.verify(self.run)["status"], "FAIL")

    def test_baseline_drift_fails_closed(self):
        with patch.object(P, "_baseline", return_value={"commit": "changed", "agents_sha256": "hash"}):
            self.assertEqual(P.apply(self.run)["status"], "BASELINE_DRIFT")
            self.assertEqual(P.verify(self.run)["status"], "FAIL")
        self.assertEqual(P.verify(self.run)["attempts"], 0)

    def test_reject_random_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                P._load(d)

    def test_audit_good_resume(self):
        P.apply(self.run)
        report = P.audit(self.export(), self.export(tail=True), self.run)
        self.assertEqual(report["verdict"], "PASS")
        self.assertTrue(all(report["checks"].values()))

    def test_audit_wrong_session_fails(self):
        P.apply(self.run)
        result = P.audit(self.export(), self.export(session_id="ses_wrong", tail=True), self.run)
        self.assertEqual(result["verdict"], "NOT_VERIFIED")
        self.assertFalse(result["checks"]["same_session_id"])

    def test_audit_missing_resume_tool_fails(self):
        P.apply(self.run)
        after = self.export(tail=True)
        after["messages"][-1]["content"] = []
        self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")

    def test_audit_repeated_apply_fails(self):
        P.apply(self.run)
        P.apply(self.run)
        self.assertEqual(P.audit(self.export(), self.export(tail=True), self.run)["verdict"], "NOT_VERIFIED")

    def test_audit_redacted_tool_input_fails(self):
        P.apply(self.run)
        a, b = self.export(), self.export(tail=True)
        b["messages"][-1]["content"][0]["state"]["input"] = {"redacted": "tool-input"}
        self.assertEqual(P.audit(a, b, self.run)["verdict"], "NOT_VERIFIED")

    def test_no_transcript_in_result(self):
        P.apply(self.run)
        before, after = self.export(), self.export(tail=True)
        before["messages"][0]["text"] = "confidential_example_DO_NOT_ECHO"
        out = json.dumps(P.audit(before, after, self.run))
        self.assertNotIn("confidential_example_DO_NOT_ECHO", out)


if __name__ == "__main__":
    unittest.main()
