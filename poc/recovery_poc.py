#!/usr/bin/env python3
"""OpenCode V2 session-resume PoC: an isolated disposable side-effect counter.

Not a filesystem sandbox, not a production exactly-once transaction manager.
"""
import argparse
import hashlib
import json
import os
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
    return {"commit": rev, "agents_sha256": digest}


def _load(run):
    run = Path(run).resolve(strict=True)
    temp = Path(tempfile.gettempdir()).resolve()
    if run.parent != temp or not run.name.startswith(PREFIX) or run.is_symlink():
        raise ValueError("只允许操作当前系统临时目录下的 ADS PoC 实验目录")
    manifest = run / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("manifest 不得为符号链接")
    data = json.loads(manifest.read_text())
    if data.get("schema") != "ads-opencode-recovery/v1" or not isinstance(data.get("run_id"), str):
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
    return file.read_text().count("apply\n") if file.exists() else 0


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


def _tools(data):
    for m in data.get("messages", []):
        if not isinstance(m, dict) or m.get("type") != "assistant":
            continue
        for item in m.get("content", []):
            if not isinstance(item, dict) or item.get("type") != "tool" or item.get("name") != "shell":
                continue
            state = item.get("state") or {}
            inputs = state.get("input") or {}
            command = inputs.get("command") if isinstance(inputs, dict) else None
            if isinstance(command, str) and state.get("status") == "completed":
                yield command


def audit(before, after, run):
    for export in (before, after):
        if not isinstance(export, dict) or not isinstance(export.get("info"), dict) or not isinstance(export.get("messages"), list):
            raise ValueError("会话导出不是 OpenCode Session JSON")
    before_info, after_info = before["info"], after["info"]
    same_id = (isinstance(before_info.get("id"), str) and
               before_info["id"].startswith("ses_") and before_info["id"] == after_info.get("id"))
    same_project = bool(before_info.get("projectID") and before_info["projectID"] == after_info.get("projectID"))
    old_ids = [m.get("id") for m in before["messages"] if isinstance(m, dict) and m.get("id")]
    new_ids = [m.get("id") for m in after["messages"] if isinstance(m, dict) and m.get("id")]
    preserved = bool(old_ids) and new_ids[:len(old_ids)] == old_ids
    additional = new_ids[len(old_ids):] if preserved else []
    new_message_types = [m.get("type") for m in after["messages"] if isinstance(m, dict) and m.get("id") in additional]
    evidence = verify(run)
    first_calls = list(_tools(before))
    after_calls = list(_tools(after))
    new_calls = after_calls[len(first_calls):] if after_calls[:len(first_calls)] == first_calls else []
    # Only inspect command tokens, never print commands or transcript text.
    first_apply = any("recovery_poc.py" in c and " apply " in f" {c} " for c in first_calls)
    resumed_verify = any("recovery_poc.py" in c and " verify " in f" {c} " for c in new_calls)
    repeated_apply = any("recovery_poc.py" in c and " apply " in f" {c} " for c in new_calls)
    checks = {"same_session_id": same_id, "same_project_id": same_project,
              "original_messages_preserved": preserved,
              "new_user_and_assistant_messages": "user" in new_message_types and "assistant" in new_message_types,
              "phase1_apply_tool_observed": first_apply,
              "phase2_verify_tool_observed": resumed_verify,
              "no_repeated_apply_tool": not repeated_apply,
              "disposable_effect_exactly_once": evidence["status"] == "PASS"}
    return {"schema": "ads-opencode-recovery-audit/v1", "verdict": "PASS" if all(checks.values()) else "NOT_VERIFIED",
            "checks": checks, "effect_attempts": evidence["attempts"],
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
