"""OpenCode Session 工具事件校准：拒绝文本自述与脱敏误判。"""
import unittest
import json
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
        self.assertEqual(inspect_session(data)["child_execution_verdict"], "NOT_VERIFIED")
        data["messages"][-1]["content"] = [tool("read", "completed")]
        self.assertEqual(inspect_session(data)["child_execution_verdict"], "PASS")


    def test_independent_child_export_with_completed_read(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"}, {"sessionID": "ses_child"})])
        parent["info"].update({"id": "ses_parent", "projectID": "p1"})
        child = {"info": {"id": "ses_child", "agent": "explore", "parentID": "ses_parent", "projectID": "p1"},
                 "messages": [{"type": "assistant", "agent": "explore",
                               "content": [tool("read", "completed"), tool("grep", "completed")]}]}
        result = inspect_session(parent, child)
        self.assertEqual(result["invocation_verdict"], "PASS")
        self.assertEqual(result["child_execution_verdict"], "PASS")
        self.assertEqual(result["worktree_readonly_verdict"], "NOT_VERIFIED")
        self.assertEqual(result["overall_verdict"], "NOT_VERIFIED")

    def test_unrelated_child_session_fails(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"}, {"sessionID": "ses_child"})])
        child = {"info": {"id": "ses_wrong", "agent": "explore"}, "messages": []}
        self.assertEqual(inspect_session(parent, child)["child_execution_verdict"], "FAIL")

    def test_wrong_child_agent_fails(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"}, {"sessionID": "ses_child"})])
        child = {"info": {"id": "ses_child", "agent": "general"}, "messages": []}
        self.assertEqual(inspect_session(parent, child)["overall_verdict"], "FAIL")

    def test_wrong_parent_reference_fails(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"}, {"sessionID": "ses_child"})])
        parent["info"]["id"] = "ses_parent"
        child = {"info": {"id": "ses_child", "agent": "explore", "parentID": "ses_other"},
                 "messages": []}
        self.assertEqual(inspect_session(parent, child)["child_execution_verdict"], "FAIL")

    def test_child_without_completed_read_is_not_verified(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"}, {"sessionID": "ses_child"})])
        child = {"info": {"id": "ses_child", "agent": "explore"},
                 "messages": [{"type": "assistant", "agent": "explore",
                               "content": [tool("read", "failed")]}]}
        self.assertEqual(inspect_session(parent, child)["child_execution_verdict"], "NOT_VERIFIED")

    def test_token_flag_never_repeats_secret(self):
        parent = session([tool("subagent", "completed", {"agent": "explore"})])
        parent["messages"].append({"type": "user", "text": "ghp_" + "Z" * 31})
        result = inspect_session(parent)
        self.assertTrue(result["potential_credential_exposure"])
        self.assertNotIn("Z" * 31, json.dumps(result))

    def test_sanitized_parent_does_not_prove_child_execution(self):
        parent = session([tool("subagent", "completed", {"redacted": "secret"}, {"redacted": "metadata"})])
        child = {"info": {"id": "ses_child", "agent": "explore"},
                 "messages": [{"type": "assistant", "agent": "explore",
                               "content": [tool("read", "completed")]}]}
        self.assertEqual(inspect_session(parent, child)["child_execution_verdict"], "NOT_VERIFIED")

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            inspect_session({"messages": []})


if __name__ == "__main__":
    unittest.main()
