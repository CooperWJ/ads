"""OpenCode 单次原生调用与上下文核对；不创建 Agent Loop。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from .project import Blocked, require, path_in, write_json, digest
from .process import execute as execute_process
from .behavior import inspect_stream


def route(description):
    text = description.lower()
    if any(word in text for word in ('bug', '缺失', '不显示', '不可用', '错误', '回归', '失败')):
        return {'route': 'bug-fix', 'next': '复现既有行为 → systematic-debugging → 回归',
                'skills': ['systematic-debugging', 'test-driven-development', 'verification-before-completion'],
                'requires_new_spec': '仅在既有预期不存在或语义改变时'}
    if any(word in text for word in ('恢复', '继续会话', 'resume')):
        return {'route': 'recovery', 'next': '先 ads context check，再使用 OpenCode 原生 Session 续接',
                'automatic_side_effect_replay': False}
    if any(word in text for word in ('qa', '用例', '验收')):
        return {'route': 'qa-intake', 'next': 'ads qa import → 外部质量/一致性复审 → ads verify --role qa'}
    if any(word in text for word in ('新增', '新功能', 'feature')):
        return {'route': 'new-feature', 'next': '来源发现 → 业务裁决 → OpenSpec → 垂直切片'}
    return {'route': 'review', 'next': '只读检查已有来源、规格、实现与测试，不自动开始需求访谈'}


def context(project, freeze=False):
    current = project.snapshot(development=True)
    target = path_in(project.root, '.ads/context.json')
    if freeze:
        write_json(target, current)
        return {'status': 'FROZEN_LOCAL', 'sha256': current['sha256'], 'semantic_authority': 'NOT_GRANTED'}
    require(target.is_file(), '缺少已加载上下文快照')
    previous = json.loads(target.read_text())
    return {'status': 'CURRENT' if previous == current else 'REPLAN_REQUIRED',
            'previous_sha256': previous.get('sha256'), 'current_sha256': current['sha256'],
            'automatic_side_effect_replay': False}


def develop(project, model, execute=False, session=None):
    require(isinstance(model, str) and '/' in model, '必须明确选择已授权模型')
    config = project.config.get('development', {})
    native = config.get('executable', 'opencode')
    require(isinstance(native, str), '无效原生可执行文件')
    prompt_path = path_in(project.root, config.get('prompt', 'TASK.md'), exists=True)
    prompt = prompt_path.read_text()
    argv = [native, 'run', '--standalone', '--model', model, '--agent', 'build', '--format', 'json', prompt]
    if session is not None:
        require(isinstance(session, str) and session.startswith('ses_') and session.isascii()
                and all(c.isalnum() or c in '_-' for c in session), '必须使用原生 Session ID')
        argv[-1:-1] = ['--session', session]
    plan = {'status': 'PLANNED', 'host': 'OpenCode native CLI', 'model': model,
            'prompt_sha256': digest(prompt.encode()), 'budget_seconds': config.get('timeout_seconds', 600),
            'requested_session': session, 'automatic_side_effect_replay': False,
            'next': '显式 --execute 仅运行一次，不自动切换模型、权限或付费账户'}
    if not execute:
        return plan
    require(shutil.which(native) is not None, 'OpenCode 未安装')
    context_report = context(project)
    require(context_report['status'] == 'CURRENT', '上下文漂移，不能使用旧快照实施')
    timeout = config.get('timeout_seconds', 600)
    require(type(timeout) is int and 1 <= timeout <= 1800, '开发调用必须有界')
    before = project.snapshot(development=True)
    directory = path_in(project.root, '.ads/development/' + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    if os.name == 'posix':
        directory.chmod(0o700)
    started = time.monotonic()
    code, error = None, None
    with (directory / 'native-private.jsonl').open('wb') as out, (directory / 'stderr-private.log').open('wb') as err:
        try:
            code = execute_process(argv, cwd=project.root, stdout=out, stderr=err, timeout=timeout)
        except subprocess.TimeoutExpired:
            error = 'TIMEOUT'
        except KeyboardInterrupt:
            error = 'INTERRUPTED'
        except OSError:
            error = 'EXECUTION_ERROR'
    if os.name == 'posix':
        (directory / 'native-private.jsonl').chmod(0o600)
        (directory / 'stderr-private.log').chmod(0o600)
    stream = (directory / 'native-private.jsonl').read_text(errors='replace')
    behavior = inspect_stream(stream)
    write_json(directory / 'behavior.json', behavior)
    types, session_ids = [], set()
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            if isinstance(event.get('sessionID'), str):
                session_ids.add(event['sessionID'])
            if event.get('type') == 'error':
                detail = event.get('error')
                kind = (detail.get('type') or detail.get('name')) if isinstance(detail, dict) else None
                error = kind if isinstance(kind, str) and kind else 'NATIVE_ERROR'
            types.append(event.get('type'))
    try:
        after = project.snapshot(development=True)
    except (Blocked, OSError, ValueError):
        after = None
        error = error or 'CONTEXT_UNREADABLE'
    authority_unchanged = after is not None and before['files'] == after['files']
    report = {**plan, 'status': 'EXECUTED_UNVERIFIED' if code == 0 and not error and authority_unchanged else 'BLOCKED',
              'exit_code': code, 'error_type': error, 'duration_seconds': time.monotonic()-started,
              'input_subject': before, 'output_subject': after, 'authority_unchanged': authority_unchanged,
              'native_sessions_observed': len(session_ids), 'stream_tool_events': behavior['completed_tool_calls'],
              'behavior_evidence': behavior,
              'session_id': next(iter(session_ids)) if len(session_ids) == 1 else None,
              'completion': 'NOT_VERIFIED', 'verification': '必须运行外部 ads verify 和 QA，不能凭原生退出 0 认可完成'}
    write_json(directory / 'summary.json', report)
    return report
