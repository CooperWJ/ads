#!/usr/bin/env python3
"""只读取 OpenCode Session 导出 JSON，输出不含提示词及工具输出的证据摘要。"""
import argparse
from collections import Counter
import json
import re
from pathlib import Path
import sys

SUCCESS = {"completed", "success", "succeeded"}
FAILURE = {"error", "failed", "cancelled", "canceled"}
AGENT_KEYS = ("agent", "agent_id", "agentId", "subagent", "subagent_type", "subagentType")
CHILD_KEYS = ("childSessionId", "child_session_id", "sessionID", "sessionId", "session_id")


TOKEN_PATTERN = re.compile(r'(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})')
SAFE_TOOLS = {"subagent", "read", "grep", "glob", "shell", "question", "websearch", "webfetch"}
def _secret_seen(data):
    return bool(TOKEN_PATTERN.search(json.dumps(data, ensure_ascii=False)))

def inspect_session(data, child_data=None):
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
    child_verdict = "PASS" if invocation == "PASS" and bool(child_ids.intersection(child_events)) else "NOT_VERIFIED"
    child_reason = "父会话中存在可关联的已完成只读工具事件" if child_verdict == "PASS" else "需要可关联的 Explore 子会话执行证据"
    if child_data is not None:
        if not isinstance(child_data, dict) or not isinstance(child_data.get("info"), dict) or not isinstance(child_data.get("messages"), list):
            raise ValueError("独立子会话导出格式无效")
        child_info = child_data["info"]
        child_id = child_info.get("id")
        child_agent = child_info.get("agent")
        linked_parent_id = child_info.get("parentID") or child_info.get("parentId") or child_info.get("parent_id")
        if not child_ids:
            child_verdict, child_reason = "NOT_VERIFIED", "父会话元数据未包含可关联的子会话 ID"
        elif not isinstance(child_id, str) or child_id not in child_ids:
            child_verdict, child_reason = "FAIL", "子会话 ID 与父工具元数据不一致"
        elif child_agent != "explore":
            child_verdict, child_reason = "FAIL", "独立子会话的 Agent 不是 explore"
        elif linked_parent_id and info.get("id") and linked_parent_id != info["id"]:
            child_verdict, child_reason = "FAIL", "子会话记录的父级 ID 不一致"
        elif child_info.get("projectID") and info.get("projectID") and child_info["projectID"] != info["projectID"]:
            child_verdict, child_reason = "FAIL", "子会话项目 ID 与父会话不一致"
        else:
            completed_read = any(
                isinstance(message, dict) and message.get("type") == "assistant" and message.get("agent") == "explore"
                and any(
                    isinstance(part, dict) and part.get("type") == "tool"
                    and part.get("name") in {"read", "grep", "glob"}
                    and isinstance(part.get("state"), dict) and part["state"].get("status") in SUCCESS
                    for part in message.get("content", [])
                )
                for message in child_data["messages"]
            )
            if invocation == "PASS" and completed_read:
                child_verdict, child_reason = "PASS", "独立 Explore 子会话 ID 关联成功，观察到已完成的只读工具事件"
            else:
                child_verdict, child_reason = "NOT_VERIFIED", "无法同时确认父委派和 Explore 已完成只读工具调用"
    possible_secret = _secret_seen(data) or (child_data is not None and _secret_seen(child_data))
    return {
        "schema": "ads-opencode-subagent-evidence/v1",
        "parent_agent": info.get("agent") if info.get("agent") in {"build", "plan"} else "unknown",
        "session_outcome": info.get("outcome") if info.get("outcome") in {"succeeded", "failed", "cancelled"} else "unknown",
        "tool_counts": {k: counts[k] for k in sorted(counts) if k in SAFE_TOOLS},
        "other_tool_count": sum(count for name, count in counts.items() if name not in SAFE_TOOLS),
        "subagent_calls": calls,
        "invocation_verdict": invocation,
        "invocation_reason": reason,
        "child_execution_verdict": child_verdict,
        "child_execution_reason": child_reason,
        "linked_child_session_id_present": bool(child_ids),
        "worktree_readonly_verdict": "NOT_VERIFIED",
        "potential_credential_exposure": possible_secret,
        "security_warning": "POTENTIAL_GITHUB_TOKEN_IN_EXPORT_REVOKE_AND_DO_NOT_SHARE" if possible_secret else "NONE_DETECTED",
        "overall_verdict": "FAIL" if "FAIL" in {invocation, child_verdict} else "NOT_VERIFIED",
        "next_evidence": "仅本地核验独立子会话与工作区差异；未脱敏导出不得上传。",
    }


def gate_exit_code(report, gate):
    """诊断模式不充当验收门禁；严格模式缺证据必须非零退出。"""
    if gate == "report":
        return 1 if report["overall_verdict"] == "FAIL" else 0
    if gate == "invocation":
        verdicts = [report["invocation_verdict"]]
    elif gate == "child":
        verdicts = [report["invocation_verdict"], report["child_execution_verdict"]]
    else:
        verdicts = [report["overall_verdict"]]
    if "FAIL" in verdicts:
        return 1
    if all(v == "PASS" for v in verdicts):
        return 0
    return 3


def main(argv=None):
    parser = argparse.ArgumentParser(description="输出 OpenCode 委派事件的低敏证据摘要")
    parser.add_argument("session_json", type=Path, help="父会话导出")
    parser.add_argument("--child", type=Path, help="独立 Explore 子会话导出（仅本机使用）")
    parser.add_argument("--gate", choices=("report", "invocation", "child", "overall"),
                        default="report", help="report 为诊断；其余为严格门禁，NOT_VERIFIED 退出 3")
    args = parser.parse_args(argv)
    try:
        parent = json.loads(args.session_json.read_text(encoding="utf-8-sig"))
        child = json.loads(args.child.read_text(encoding="utf-8-sig")) if args.child else None
        report = inspect_session(parent, child)
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": type(exc).__name__}, ensure_ascii=False))
        return 2
    code = gate_exit_code(report, args.gate)
    report["check_mode"] = args.gate
    report["check_exit"] = code
    report["check_exit_semantics"] = (
        "0=report-generated-not-overall-pass" if args.gate == "report" and code == 0
        else "0=required-verdicts-PASS;1=FAIL;2=INVALID_INPUT;3=NOT_VERIFIED"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
