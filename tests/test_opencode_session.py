"""OpenCode Session 工具事件校准：拒绝文本自述与脱敏误判。"""
import unittest
from poc.check_opencode_session import inspect_session


def tool(name, status, inputs=None, metadata=None):
    return {"type": "tool", "name": name,
            "state": {"status": status, "input": inputs or {}, "metadata": metadata or {}}}


def session(events, agent="build"):
    return {"info": {"agent": agent, "outcome": "succeeded"},
            "messages": [{"type": "user", "text": "已经调用 Explore"},
                         {"type": "assistant", "agent": agent, "content": events}]}


class OpenCodeEvidenceTests(unittest.TestCase):
    def test_shell_and_text_do_not_prove_subagent(self):
        result = inspect_session(session([tool("shell", "completed")]))
        self.assertEqual(result["invocation_verdict"], "NOT_VERIFIED")
        self.assertEqual(result["tool_counts"], {"shell": 1})

    def test_redacted_args_are_not_verified(self):
        result = inspect_session(session([tool("subagent", "completed", {"redacted": "tool-input:abc"})]))
        self.assertEqual(result["invocation_verdict"], "NOT_VERIFIED")

    def test_completed_explore_invocation_only(self):
        result = inspect_session(session([tool("subagent", "completed", {"agent": "explore"})]))
        self.assertEqual(result["invocation_verdict"], "PASS")
        self.assertEqual(result["child_execution_verdict"], "NOT_VERIFIED")
        self.assertEqual(result["overall_verdict"], "NOT_VERIFIED")

    def test_wrong_agent_or_failure_is_rejected(self):
        for event in [tool("subagent", "completed", {"agent": "general"}),
                      tool("subagent", "failed", {"agent": "explore"})]:
            with self.subTest(event=event):
                self.assertEqual(inspect_session(session([event]))["invocation_verdict"], "FAIL")

    def test_parent_must_be_build(self):
        result = inspect_session(session([tool("subagent", "completed", {"agent": "explore"})], agent="plan"))
        self.assertEqual(result["invocation_verdict"], "NOT_VERIFIED")

    def test_child_id_alone_not_evidence(self):
        data = session([tool("subagent", "completed", {"agent": "explore"},
                             {"childSessionId": "ses_child"})])
        self.assertEqual(inspect_session(data)["child_execution_verdict"], "NOT_VERIFIED")
        data["messages"].append({"type": "assistant", "agent": "explore",
                                 "sessionId": "ses_unrelated", "content": []})
        self.assertEqual(inspect_session(data)["child_execution_verdict"], "NOT_VERIFIED")
        data["messages"][-1]["sessionId"] = "ses_child"
        self.assertEqual(inspect_session(data)["child_execution_verdict"], "PASS")

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            inspect_session({"messages": []})


if __name__ == "__main__":
    unittest.main()
