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


def _safe_error_label(value):
    if not isinstance(value, str) or not 0 < len(value) <= 100:
        return None
    return value if all(ch.isalnum() or ch in '_.-' for ch in value) else None


def summarize_native_error(detail):
    """Expose only stable, non-message fields from a native OpenCode error."""
    if not isinstance(detail, dict):
        return {'type': 'NATIVE_ERROR', 'classification': 'UNKNOWN'}
    data = detail.get('data')
    data = data if isinstance(data, dict) else {}
    name = _safe_error_label(detail.get('type') or detail.get('name')) or 'NATIVE_ERROR'
    status = data.get('statusCode')
    status = status if type(status) is int and 400 <= status <= 599 else None
    code = _safe_error_label(data.get('code') or detail.get('code'))
    provider = _safe_error_label(data.get('providerID') or data.get('providerId') or detail.get('providerID'))
    normalized_code = (code or '').lower()
    if 'free-limit' in normalized_code or 'quota' in normalized_code:
        classification = 'MODEL_QUOTA'
    elif status == 429:
        classification = 'RATE_LIMITED'
    elif status in (401, 403):
        classification = 'AUTH_OR_PERMISSION'
    elif status in (408, 504):
        classification = 'UPSTREAM_TIMEOUT'
    elif status is not None and status >= 500:
        classification = 'UPSTREAM_FAILURE'
    else:
        classification = 'UNKNOWN'
    return {'type': name, 'classification': classification, 'status_code': status,
            'code': code, 'provider_id': provider}


def change_set(before, after):
    """Summarize repository path changes without copying file contents."""
    if not isinstance(after, dict):
        return {'status': 'UNKNOWN', 'added': [], 'modified': [], 'deleted': [],
                'counts': {'added': 0, 'modified': 0, 'deleted': 0}}
    old_repos = {item['name']: item.get('files', {}) for item in before.get('repositories', [])}
    new_repos = {item['name']: item.get('files', {}) for item in after.get('repositories', [])}
    added, modified, deleted = [], [], []
    for repo in sorted(set(old_repos) | set(new_repos)):
        old = old_repos.get(repo, {})
        new = new_repos.get(repo, {})
        for path in sorted(set(new) - set(old)):
            added.append({'repository': repo, 'path': path})
        for path in sorted(set(old) - set(new)):
            deleted.append({'repository': repo, 'path': path})
        for path in sorted(set(old) & set(new)):
            if old[path] != new[path]:
                modified.append({'repository': repo, 'path': path})
    return {'status': 'OBSERVED', 'added': added, 'modified': modified, 'deleted': deleted,
            'counts': {'added': len(added), 'modified': len(modified), 'deleted': len(deleted)}}


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
    run_id = uuid.uuid4().hex
    directory = path_in(project.root, '.ads/development/' + run_id)
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
    native_error = None
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
                native_error = summarize_native_error(detail)
                error = native_error['type']
            types.append(event.get('type'))
    session_confirmation = ('NOT_REQUESTED' if session is None else
                             'CONFIRMED' if session in session_ids else
                             'MISMATCH' if session_ids else 'NOT_OBSERVED')
    if session is not None and session_confirmation != 'CONFIRMED' and error is None:
        error = 'SESSION_MISMATCH' if session_confirmation == 'MISMATCH' else 'SESSION_NOT_CONFIRMED'
    try:
        after = project.snapshot(development=True)
    except (Blocked, OSError, ValueError):
        after = None
        error = error or 'CONTEXT_UNREADABLE'
    authority_unchanged = after is not None and before['files'] == after['files']
    behavior_path = directory / 'behavior.json'
    report = {**plan, 'schema': 'ads-development-run/v1', 'run_id': run_id,
              'behavior_path': str(behavior_path.relative_to(project.root)),
              'behavior_sha256': digest(behavior_path.read_bytes()),
              'status': 'EXECUTED_UNVERIFIED' if code == 0 and not error and authority_unchanged else 'BLOCKED',
              'exit_code': code, 'error_type': error, 'native_error': native_error,
              'duration_seconds': time.monotonic()-started,
              'input_subject': before, 'output_subject': after, 'authority_unchanged': authority_unchanged,
              'change_set': change_set(before, after),
              'native_sessions_observed': len(session_ids), 'session_confirmation': session_confirmation,
              'stream_tool_events': behavior['completed_tool_calls'],
              'behavior_evidence': behavior,
              'session_id': (session if session_confirmation == 'CONFIRMED' else
                            next(iter(session_ids)) if len(session_ids) == 1 else None),
              'completion': 'NOT_VERIFIED', 'verification': '必须运行外部 ads verify 和 QA，不能凭原生退出 0 认可完成'}
    summary_path = directory / 'summary.json'
    write_json(summary_path, report)
    write_json(path_in(project.root, '.ads/latest-development.json'), {
        'run_id': run_id,
        'summary_sha256': digest(summary_path.read_bytes()),
        'behavior_sha256': report['behavior_sha256'],
    })
    return report
