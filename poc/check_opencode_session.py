#!/usr/bin/env python3
"""只读取 OpenCode Session 导出 JSON，输出不含提示词及工具输出的证据摘要。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

SUCCESS = {"completed", "success", "succeeded"}
FAILURE = {"error", "failed", "cancelled", "canceled"}
AGENT_KEYS = ("agent", "agent_id", "agentId", "subagent", "subagent_type", "subagentType")
CHILD_KEYS = ("childSessionId", "child_session_id", "sessionID", "sessionId", "session_id")


def inspect_session(data):
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict) or not isinstance(data.get("messages"), list):
        raise ValueError("导出格式无效：缺少 info 对象或 messages 数组")
    info = data["info"]
    counts = Counter()
    calls, child_ids, child_events = [], set(), set()
    for message in data["messages"]:
        if not isinstance(message, dict):
            continue
        if message.get("type") == "assistant" and message.get("agent") == "explore":
            has_completed_read = any(
                isinstance(part, dict) and part.get("type") == "tool"
                and part.get("name") in {"read", "grep", "glob"}
                and isinstance(part.get("state"), dict)
                and part["state"].get("status") in SUCCESS
                for part in message.get("content", [])
            )
            if has_completed_read:
                for key in CHILD_KEYS:
                    cid = message.get(key)
                    if isinstance(cid, str) and cid.startswith("ses_"):
                        child_events.add(cid)
        for event in message.get("content", []):
            if not isinstance(event, dict) or event.get("type") != "tool":
                continue
            name = event.get("name")
            if not isinstance(name, str):
                continue
            counts[name] += 1
            if name != "subagent":
                continue
            state = event.get("state") if isinstance(event.get("state"), dict) else {}
            inputs = state.get("input") if isinstance(state.get("input"), dict) else {}
            metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
            target = next((inputs[k] for k in AGENT_KEYS
                           if isinstance(inputs.get(k), str) and not inputs[k].startswith("[redacted:")), None)
            ids = [metadata[k] for k in CHILD_KEYS
                   if isinstance(metadata.get(k), str) and metadata[k].startswith("ses_")]
            child_ids.update(ids)
            raw_status = state.get("status")
            calls.append({
                "tool_state": raw_status if raw_status in SUCCESS | FAILURE else "unknown",
                "explore_target_confirmed": target == "explore",
                "different_target_observed": bool(target and target != "explore"),
                "child_session_id_present": bool(ids),
            })
    if not calls:
        invocation, reason = "NOT_VERIFIED", "导出范围内未出现结构化 subagent 工具事件"
    elif any(c["different_target_observed"] for c in calls):
        invocation, reason = "FAIL", "观察到目标为非 explore Agent 的 subagent 事件"
    elif any(c["tool_state"] in FAILURE for c in calls):
        invocation, reason = "FAIL", "subagent 事件明确报告失败或取消"
    elif info.get("agent") == "build" and any(
        c["tool_state"] in SUCCESS and c["explore_target_confirmed"] for c in calls
    ):
        invocation, reason = "PASS", "父会话的已完成 subagent 工具事件明确指向 explore"
    else:
        invocation, reason = "NOT_VERIFIED", "委派目标、执行状态或父 Agent 未能独立证实"
    child_verified = invocation == "PASS" and bool(child_ids.intersection(child_events))
    return {
        "schema": "ads-opencode-subagent-evidence/v1",
        "parent_agent": info.get("agent") if info.get("agent") in {"build", "plan"} else "unknown",
        "session_outcome": info.get("outcome") if info.get("outcome") in {"succeeded", "failed", "cancelled"} else "unknown",
        "tool_counts": {k: counts[k] for k in sorted(counts)},
        "subagent_calls": calls,
        "invocation_verdict": invocation,
        "invocation_reason": reason,
        "child_execution_verdict": "PASS" if child_verified else "NOT_VERIFIED",
        "worktree_readonly_verdict": "NOT_VERIFIED",
        "overall_verdict": "FAIL" if invocation == "FAIL" else "NOT_VERIFIED",
        "next_evidence": "仍需独立子会话执行记录和运行前后 Git 工作区差异；本工具不审阅私有输入/输出。",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="输出 OpenCode 委派事件的低敏证据摘要")
    parser.add_argument("session_json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = inspect_session(json.loads(args.session_json.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": type(exc).__name__}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["invocation_verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
