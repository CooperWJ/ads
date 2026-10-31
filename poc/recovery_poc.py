#!/usr/bin/env python3
"""OpenCode V2 session-resume PoC: an isolated disposable side-effect counter.

Not a filesystem sandbox, not a production exactly-once transaction manager.
"""
import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "ads-oc-recovery-"


def _baseline():
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                         capture_output=True, timeout=5, check=True).stdout.strip()
    digest = hashlib.sha256((ROOT / "AGENTS.md").read_bytes()).hexdigest()
    diff = subprocess.run(["git", "diff", "HEAD", "--binary", "--no-ext-diff"], cwd=ROOT,
                          capture_output=True, timeout=5, check=True).stdout
    return {"commit": rev, "agents_sha256": digest,
            "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _load(run):
    original = Path(run)
    if original.is_symlink():
        raise ValueError("实验目录不得为符号链接")
    run = original.resolve(strict=True)
    temp = Path(tempfile.gettempdir()).resolve()
    if run.parent != temp or not run.name.startswith(PREFIX) or run.is_symlink():
        raise ValueError("只允许操作当前系统临时目录下的 ADS PoC 实验目录")
    manifest = run / "manifest.json"
    if any((run / name).is_symlink() for name in ("manifest.json", "attempts.log", "applied.json")):
        raise ValueError("实验文件不得为符号链接")
    data = json.loads(manifest.read_text())
    if data.get("schema") != "ads-opencode-recovery/v1" or not isinstance(data.get("run_id"), str) or not isinstance(data.get("baseline"), dict):
        raise ValueError("无效实验目录")
    return run, data


def init():
    run = Path(tempfile.mkdtemp(prefix=PREFIX))
    manifest = {"schema": "ads-opencode-recovery/v1", "run_id": uuid.uuid4().hex,
                "baseline": _baseline()}
    (run / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return {"status": "READY", "run_dir": str(run), "run_id": manifest["run_id"]}


def apply(run):
    run, data = _load(run)
    if _baseline() != data["baseline"]:
        return {"status": "BASELINE_DRIFT", "attempts": None}
    with (run / "attempts.log").open("a", encoding="utf8") as fh:
        fh.write("apply\n")
        fh.flush()
        os.fsync(fh.fileno())
    marker = run / "applied.json"
    content = json.dumps({"run_id": data["run_id"], "effect": "ONE_DISPOSABLE_MARKER"}, sort_keys=True)
    try:
        with marker.open("x", encoding="utf8") as fh:
            fh.write(content + "\n")
        result = "APPLIED"
    except FileExistsError:
        result = "REPEATED_APPLY"
    return {"status": result, "attempts": _count(run), "run_id": data["run_id"]}


def _count(run):
    file = run / "attempts.log"
    lines = file.read_text().splitlines() if file.exists() else []
    if any(line != "apply" for line in lines):
        raise ValueError("副作用尝试记录损坏")
    return len(lines)


def verify(run):
    run, data = _load(run)
    drift = _baseline() != data["baseline"]
    attempts = _count(run)
    marker = run / "applied.json"
    try:
        payload = json.loads(marker.read_text())
        good_marker = payload == {"run_id": data["run_id"], "effect": "ONE_DISPOSABLE_MARKER"}
    except (OSError, ValueError):
        good_marker = False
    result = "PASS" if good_marker and attempts == 1 and not drift else "FAIL"
    return {"status": result, "attempts": attempts, "marker_valid": good_marker,
            "baseline_drift": drift, "run_id": data["run_id"]}


def _messages_valid(messages):
    ids = [m.get("id") for m in messages if isinstance(m, dict)]
    return (len(ids) == len(messages) and all(isinstance(x, str) and x for x in ids)
            and len(ids) == len(set(ids)))


def _tools(messages):
    for message in messages:
        if not isinstance(message, dict) or message.get("type") != "assistant":
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            raise ValueError("无效消息内容")
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool" and item.get("name") == "shell":
                yield item


def _bound_call(item, action, run, run_id):
    # 仅接受直接 Python 调用；包装器、复合 shell、重定向均不能作为证明。
    state = item.get("state")
    if not isinstance(state, dict) or state.get("status") != "completed":
        return False
    inputs = state.get("input")
    command = inputs.get("command") if isinstance(inputs, dict) else None
    if not isinstance(command, str) or any(c in command for c in "\n\r;&|<>`$"):
        return False
    try:
        tokens = shlex.split(command)
        if len(tokens) != 4 or tokens[0] not in {"python", "python3", sys.executable}:
            return False
        script = Path(tokens[1])
        script = script if script.is_absolute() else ROOT / script
        if script.resolve() != Path(__file__).resolve() or tokens[2] != action:
            return False
        if not Path(tokens[3]).is_absolute() or Path(tokens[3]).resolve() != run:
            return False
        # 缺 stdout、脱敏 stdout、其他实验回执均不能升级为已执行证据。
        output = state.get("output")
        receipt = json.loads(output) if isinstance(output, str) else None
        if not isinstance(receipt, dict) or receipt.get("run_id") != run_id:
            return False
        if type(receipt.get("attempts")) is not int or receipt["attempts"] != 1:
            return False
        if action == "apply":
            return receipt.get("status") == "APPLIED"
        return (receipt.get("status") == "PASS" and receipt.get("marker_valid") is True
                and receipt.get("baseline_drift") is False)
    except (OSError, ValueError):
        return False


def audit(before, after, run):
    for export in (before, after):
        if not isinstance(export, dict) or not isinstance(export.get("info"), dict) or not isinstance(export.get("messages"), list):
            raise ValueError("会话导出不是 OpenCode Session JSON")
    run, manifest = _load(run)
    before_info, after_info = before["info"], after["info"]
    same_id = (isinstance(before_info.get("id"), str) and
               before_info["id"].startswith("ses_") and before_info["id"] == after_info.get("id"))
    same_project = bool(before_info.get("projectID") and before_info["projectID"] == after_info.get("projectID"))
    old, current = before["messages"], after["messages"]
    valid = _messages_valid(old) and _messages_valid(current)
    preserved = valid and bool(old) and current[:len(old)] == old
    new = current[len(old):] if preserved else []
    new_types = [m.get("type") for m in new]
    first_calls, new_calls = list(_tools(old)), list(_tools(new))
    first_apply = (len(first_calls) == 1 and
                   _bound_call(first_calls[0], "apply", run, manifest["run_id"]))
    resumed_verify = (len(new_calls) == 1 and
                      _bound_call(new_calls[0], "verify", run, manifest["run_id"]))
    evidence = verify(run)
    checks = {"same_session_id": same_id, "same_project_id": same_project,
              "unique_message_ids": valid,
              "original_messages_preserved": preserved,
              "new_user_and_assistant_messages": "user" in new_types and "assistant" in new_types,
              "phase1_apply_tool_observed": first_apply,
              "phase2_verify_tool_observed": resumed_verify,
              "resume_shell_scope_verified": resumed_verify,
              "disposable_effect_exactly_once": evidence["status"] == "PASS"}
    return {"schema": "ads-opencode-recovery-audit/v2", "verdict": "PASS" if all(checks.values()) else "NOT_VERIFIED",
            "checks": checks, "effect_attempts": evidence["attempts"],
            "evidence_trust": "LOCAL_EXPORT_CONSISTENCY_ONLY",
            "scope": "CLI/TUI client re-entry for same session, NOT mid-tool crash recovery"}


def main(argv=None):
    p = argparse.ArgumentParser(description="ADS disposable OpenCode session continuation probe")
    subs = p.add_subparsers(dest="action", required=True)
    subs.add_parser("init")
    for action in ("apply", "verify"):
        subs.add_parser(action).add_argument("run_dir")
    a = subs.add_parser("audit")
    a.add_argument("before", type=Path)
    a.add_argument("after", type=Path)
    a.add_argument("run_dir")
    args = p.parse_args(argv)
    try:
        if args.action == "init":
            report = init()
        elif args.action == "apply":
            report = apply(args.run_dir)
        elif args.action == "verify":
            report = verify(args.run_dir)
        else:
            report = audit(json.loads(args.before.read_text()), json.loads(args.after.read_text()), args.run_dir)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INVALID_INPUT", "error_type": type(error).__name__}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") in {"READY", "APPLIED", "PASS"} or report.get("verdict") == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
