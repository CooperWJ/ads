"""从 OpenCode 原生 JSONL 中提取可观察的开发行为；不把启发式升级为正确性证明。"""
import json
import re


_TEST_COMMAND = re.compile(
    r"(^|[;&|\s])(pytest|unittest|nose2|tox|nox|jest|vitest|mocha|"
    r"playwright|e2e|npm\s+(run\s+)?(test|check)|pnpm\s+(run\s+)?(test|check)|"
    r"yarn\s+(test|check)|cargo\s+test|go\s+test|mvn\s+test|gradle\s+test)(\s|$)",
    re.IGNORECASE,
)
_EDIT_TOOLS = {"write", "edit", "apply_patch", "patch"}
_SKILL_TOOLS = {"skill"}


def inspect_stream(data):
    """Return a low-sensitivity evidence projection from OpenCode run --format json.

    Only event ordering, tool names, skill identifiers and process exit codes survive.
    Prompts, source contents, command strings and tool output are never copied.
    """
    events = []
    malformed = 0
    for line in data.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            malformed += 1
            continue
        if isinstance(item, dict):
            events.append(item)
        else:
            malformed += 1

    observations = []
    for ordinal, event in enumerate(events):
        if event.get("type") != "tool_use":
            continue
        part = event.get("part")
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        tool = part.get("tool")
        state = part.get("state")
        if not isinstance(tool, str) or not isinstance(state, dict):
            continue
        if state.get("status") != "completed":
            continue
        inputs = state.get("input") or {}
        metadata = state.get("metadata") or {}
        if not isinstance(inputs, dict) or not isinstance(metadata, dict):
            continue
        command = inputs.get("command")
        command = command if isinstance(command, str) else ""
        exit_code = metadata.get("exit")
        if type(exit_code) is not int:
            exit_code = None
        skill_name = None
        if tool in _SKILL_TOOLS:
            candidate = inputs.get("name") or inputs.get("skill")
            if isinstance(candidate, str):
                skill_name = candidate.rsplit("/", 1)[-1]
        observations.append({
            "ordinal": ordinal,
            "tool": tool,
            "exit_code": exit_code,
            "is_test_command": tool == "bash" and bool(_TEST_COMMAND.search(command)),
            "is_direct_edit": tool in _EDIT_TOOLS,
            "skill": skill_name,
        })

    test_runs = [o for o in observations if o["is_test_command"]]
    edits = [o for o in observations if o["is_direct_edit"]]
    first_edit = min((o["ordinal"] for o in edits), default=None)
    first_test = min((o["ordinal"] for o in test_runs), default=None)
    failed_before_edit = any(
        o["exit_code"] not in (None, 0) and (first_edit is None or o["ordinal"] < first_edit)
        for o in test_runs
    )
    passed_after_edit = any(
        o["exit_code"] == 0 and first_edit is not None and o["ordinal"] > first_edit
        for o in test_runs
    )
    last_edit = max(edits, key=lambda o: o["ordinal"], default=None)
    last_test = max(test_runs, key=lambda o: o["ordinal"], default=None)
    skills = sorted({o["skill"] for o in observations if o["skill"]})
    final_part = events[-1].get("part") if events else None
    terminal_event = (bool(events) and events[-1].get("type") == "step_finish"
                      and isinstance(final_part, dict) and final_part.get("reason") == "stop")
    if malformed:
        stream_status = "PARTIAL"
    elif not data.strip():
        stream_status = "EMPTY"
    else:
        stream_status = "PARSE_CLEAN"
    ordering_trustworthy = stream_status == "PARSE_CLEAN" and terminal_event
    if not ordering_trustworthy or last_edit is None or last_test is None or last_test["exit_code"] is None:
        final_verification = "INDETERMINATE"
    elif last_test["ordinal"] <= last_edit["ordinal"]:
        final_verification = "NOT_OBSERVED"
    elif last_test["exit_code"] == 0:
        final_verification = "OBSERVED"
    else:
        final_verification = "FAILED"

    def observed(value):
        return "OBSERVED" if value else "NOT_OBSERVED"

    return {
        "schema": "ads-opencode-behavior/v1",
        "stream_status": stream_status,
        "terminal_event_observed": terminal_event,
        "malformed_event_lines": malformed,
        "completed_tool_calls": len(observations),
        "tool_counts": {
            name: sum(o["tool"] == name for o in observations)
            for name in sorted({o["tool"] for o in observations})
        },
        "skills_invoked": skills,
        "systematic_debugging_invoked": observed("systematic-debugging" in skills),
        "test_driven_development_invoked": observed("test-driven-development" in skills),
        "verification_before_completion_invoked": observed("verification-before-completion" in skills),
        "test_commands_observed": len(test_runs),
        "test_command_process_results": {
            "exit_zero": sum(o["exit_code"] == 0 for o in test_runs),
            "nonzero": sum(o["exit_code"] is not None and o["exit_code"] != 0 for o in test_runs),
            "unknown": sum(o["exit_code"] is None for o in test_runs),
        },
        "direct_edit_tools_observed": len(edits),
        "test_before_first_direct_edit": (
            "INDETERMINATE" if not ordering_trustworthy or first_test is None or first_edit is None
            else "OBSERVED" if first_test < first_edit else "NOT_OBSERVED"
        ),
        "observed_red_green_sequence": (
            "INDETERMINATE" if not ordering_trustworthy else
            "OBSERVED" if failed_before_edit and passed_after_edit else "NOT_OBSERVED"
        ),
        "final_verification_after_last_direct_edit": final_verification,
        "evidence_limit": (
            "Event order and tool metadata only. This does not prove test intent, "
            "business correctness, complete file-change coverage, or that a skill's "
            "guidance was followed."
        ),
    }
