"""Disposable process/session recovery experiment: no business logic or credentials."""
import json
import copy
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
        run_id = json.loads((Path(self.run) / "manifest.json").read_text())["run_id"]
        for message in messages:
            for event in message.get("content", []):
                state = event["state"]
                action = "apply" if " apply " in state["input"]["command"] else "verify"
                state["input"]["command"] = f"python3 poc/recovery_poc.py {action} {self.run}"
                receipt = {"status": "APPLIED" if action == "apply" else "PASS",
                           "run_id": run_id, "attempts": 1}
                if action == "verify":
                    receipt.update(marker_valid=True, baseline_drift=False)
                state["output"] = json.dumps(receipt)
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

    def test_shell_spoofing_and_wrong_experiment_are_rejected(self):
        P.apply(self.run)
        commands = [
            "echo recovery_poc.py verify /wrong-experiment",
            f"echo python3 poc/recovery_poc.py verify {self.run}",
            "python3 poc/recovery_poc.py verify /wrong-experiment",
            f"python3 /tmp/recovery_poc.py verify {self.run}",
            f"python3 poc/recovery_poc.py verify {self.run}; echo ok",
            f"python3 poc/recovery_poc.py verify {self.run} > /tmp/fake",
            f"python3 poc/recovery_poc.py verify {self.run}\necho ok",
        ]
        for command in commands:
            with self.subTest(command=command):
                before, after = self.export(), self.export(tail=True)
                after["messages"][-1]["content"][0]["state"]["input"]["command"] = command
                self.assertEqual(P.audit(before, after, self.run)["verdict"], "NOT_VERIFIED")

    def test_historical_message_content_change_is_rejected(self):
        P.apply(self.run)
        before, after = self.export(), self.export(tail=True)
        after["messages"][0]["text"] = "tampered"
        self.assertFalse(P.audit(before, after, self.run)["checks"]["original_messages_preserved"])

    def test_duplicate_or_missing_message_ids_are_rejected(self):
        P.apply(self.run)
        for value in ("m1", "", None):
            after = self.export(tail=True)
            after["messages"][-1]["id"] = value
            self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")

    def test_missing_mismatched_or_failed_receipt_is_rejected(self):
        P.apply(self.run)
        for receipt in (None, "redacted", "{}", json.dumps({"status": "PASS", "attempts": 1, "run_id": "other"})):
            after = self.export(tail=True)
            after["messages"][-1]["content"][0]["state"]["output"] = receipt
            self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")
        after = self.export(tail=True)
        after["messages"][-1]["content"][0]["state"]["status"] = "failed"
        self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")

    def test_additional_shell_command_cannot_hide_replay(self):
        P.apply(self.run)
        after = self.export(tail=True)
        event = copy.deepcopy(after["messages"][-1]["content"][0])
        event["state"]["input"]["command"] = "python3 -c 'print(1)'"
        after["messages"][-1]["content"].append(event)
        self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")


    def test_phase1_spoof_is_rejected(self):
        P.apply(self.run)
        before, after = self.export(), self.export(tail=True)
        for export in (before, after):
            export["messages"][1]["content"][0]["state"]["input"]["command"] = "echo recovery_poc.py apply /wrong-experiment"
        self.assertEqual(P.audit(before, after, self.run)["verdict"], "NOT_VERIFIED")

    def test_receipt_does_not_accept_false_success_or_bool_count(self):
        P.apply(self.run)
        for field, value in (("attempts", True), ("status", "FAIL"), ("marker_valid", False), ("baseline_drift", True)):
            after = self.export(tail=True)
            state = after["messages"][-1]["content"][0]["state"]
            receipt = json.loads(state["output"])
            receipt[field] = value
            state["output"] = json.dumps(receipt)
            self.assertEqual(P.audit(self.export(), after, self.run)["verdict"], "NOT_VERIFIED")

    def test_corrupt_attempt_log_is_invalid(self):
        P.apply(self.run)
        (Path(self.run) / "attempts.log").write_text("junkapply\n")
        with self.assertRaises(ValueError):
            P.verify(self.run)

    def test_symlinked_effect_is_invalid(self):
        P.apply(self.run)
        marker = Path(self.run) / "applied.json"
        original = Path(self.run) / "original.json"
        marker.rename(original)
        marker.symlink_to(original)
        with self.assertRaises(ValueError):
            P.verify(self.run)





class RealCLIProcessTests(unittest.TestCase):
    """跨真实 Python 进程验证副作用记录持久化；不假装运行了 OpenCode。"""

    def test_cli_persists_once_and_rejects_replay_across_processes(self):
        import shutil
        import subprocess
        import sys

        script = str(Path(P.__file__).resolve())

        def invoke(*args):
            result = subprocess.run(
                [sys.executable, script, *args],
                cwd=P.ROOT, capture_output=True, text=True, timeout=15,
            )
            self.assertTrue(result.stdout, result.stderr)
            return result.returncode, json.loads(result.stdout)

        code, created = invoke("init")
        self.assertEqual(code, 0)
        run_dir = created["run_dir"]
        self.addCleanup(lambda: shutil.rmtree(run_dir, ignore_errors=True))
        code, first = invoke("apply", run_dir)
        self.assertEqual((code, first["status"], first["attempts"]), (0, "APPLIED", 1))
        code, verified = invoke("verify", run_dir)
        self.assertEqual((code, verified["status"], verified["attempts"]), (0, "PASS", 1))
        code, replay = invoke("apply", run_dir)
        self.assertEqual((code, replay["status"], replay["attempts"]),
                         (3, "REPEATED_APPLY", 2))
        code, failed = invoke("verify", run_dir)
        self.assertEqual((code, failed["status"], failed["attempts"]),
                         (3, "FAIL", 2))


if __name__ == "__main__":
    unittest.main()
