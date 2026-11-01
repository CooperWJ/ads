"""OpenCode 行为证据投影：只验证事件事实，不声称语义正确。"""
import json
import unittest

from ads.behavior import inspect_stream


def tool(name, inputs=None, exit_code=0):
    return {
        "type": "tool_use",
        "sessionID": "ses_fixture",
        "part": {
            "type": "tool", "tool": name,
            "state": {
                "status": "completed",
                "input": inputs or {},
                "metadata": {"exit": exit_code},
                "output": "private output must not be copied",
            },
        },
    }


class BehaviorEvidenceTests(unittest.TestCase):
    def stream(self, *events):
        return "\n".join(json.dumps(e) for e in events)

    def test_observes_skill_use_and_red_green_order_without_copying_commands(self):
        result = inspect_stream(self.stream(
            tool("skill", {"name": "systematic-debugging"}),
            tool("skill", {"name": "test-driven-development"}),
            tool("bash", {"command": "pytest -q"}, 1),
            tool("edit", {"filePath": "src/app.py"}),
            tool("bash", {"command": "pytest -q"}, 0),
            tool("skill", {"name": "verification-before-completion"}),
            {"type": "step_finish", "part": {"reason": "stop"}},
        ))
        self.assertEqual(result["stream_status"], "PARSE_CLEAN")
        self.assertTrue(result["terminal_event_observed"])
        self.assertEqual(result["systematic_debugging_invoked"], "OBSERVED")
        self.assertEqual(result["test_driven_development_invoked"], "OBSERVED")
        self.assertEqual(result["verification_before_completion_invoked"], "OBSERVED")
        self.assertEqual(result["test_before_first_direct_edit"], "OBSERVED")
        self.assertEqual(result["observed_red_green_sequence"], "OBSERVED")
        serialized = json.dumps(result)
        self.assertNotIn("pytest -q", serialized)
        self.assertNotIn("private output", serialized)
        self.assertNotIn("src/app.py", serialized)

    def test_does_not_infer_tdd_when_only_tests_or_only_edits_are_seen(self):
        only_test = inspect_stream(self.stream(tool("bash", {"command": "npm test"}, 0)))
        self.assertEqual(only_test["test_before_first_direct_edit"], "INDETERMINATE")
        self.assertEqual(only_test["observed_red_green_sequence"], "INDETERMINATE")
        only_edit = inspect_stream(self.stream(tool("edit", {"filePath": "x.py"})))
        self.assertEqual(only_edit["test_before_first_direct_edit"], "INDETERMINATE")

    def test_ordering_is_indeterminate_without_terminal_event(self):
        result = inspect_stream(self.stream(
            tool("bash", {"command": "pytest -q"}, 1),
            tool("edit", {"filePath": "src/app.py"}),
            tool("bash", {"command": "pytest -q"}, 0),
        ))
        self.assertEqual(result["observed_red_green_sequence"], "INDETERMINATE")
        self.assertEqual(result["test_before_first_direct_edit"], "INDETERMINATE")

    def test_shell_edit_is_not_claimed_as_direct_edit(self):
        result = inspect_stream(self.stream(
            tool("bash", {"command": "cat > src/app.py <<'EOF'\npass\nEOF"}, 0),
            tool("bash", {"command": "pytest -q"}, 0),
        ))
        self.assertEqual(result["direct_edit_tools_observed"], 0)
        self.assertEqual(result["test_before_first_direct_edit"], "INDETERMINATE")

    def test_malformed_lines_are_partial_and_empty_stream_is_empty(self):
        partial = inspect_stream('{"type":"text"}\nnot-json')
        self.assertEqual(partial["stream_status"], "PARTIAL")
        self.assertEqual(partial["malformed_event_lines"], 1)
        self.assertEqual(inspect_stream("")["stream_status"], "EMPTY")

    def test_uncompleted_or_unknown_tools_are_not_counted(self):
        event = tool("bash", {"command": "pytest"})
        event["part"]["state"]["status"] = "running"
        unknown = {"type": "tool_use", "part": {"type": "tool", "tool": "bash"}}
        result = inspect_stream(self.stream(event, unknown))
        self.assertEqual(result["completed_tool_calls"], 0)
        self.assertEqual(result["test_commands_observed"], 0)


if __name__ == "__main__":
    unittest.main()
