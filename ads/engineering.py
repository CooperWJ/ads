"""OpenCode 单次原生调用与上下文核对；不创建 Agent Loop。"""
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from .project import require, path_in, write_json, digest
from .process import execute as execute_process


def route(description):
    text = description.lower()
    if any(word in text for word in ('bug', '缺失', '不显示', '不可用', '错误', '回归', '失败')):
        return {'route': 'bug-fix', 'next': '复现既有行为 → systematic-debugging → 回归',
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
    current = project.snapshot()
    target = path_in(project.root, '.ads/context.json')
    if freeze:
        write_json(target, current)
        return {'status': 'FROZEN_LOCAL', 'sha256': current['sha256'], 'semantic_authority': 'NOT_GRANTED'}
    require(target.is_file(), '缺少已加载上下文快照')
    previous = json.loads(target.read_text())
    return {'status': 'CURRENT' if previous == current else 'REPLAN_REQUIRED',
            'previous_sha256': previous.get('sha256'), 'current_sha256': current['sha256'],
            'automatic_side_effect_replay': False}


def develop(project, model, execute=False):
    require(isinstance(model, str) and '/' in model, '必须明确选择已授权模型')
    config = project.config.get('development', {})
    native = config.get('executable', 'opencode')
    require(isinstance(native, str), '无效原生可执行文件')
    prompt_path = path_in(project.root, config.get('prompt', 'TASK.md'), exists=True)
    prompt = prompt_path.read_text()
    argv = [native, 'run', '--standalone', '--model', model, '--agent', 'build', '--format', 'json', prompt]
    plan = {'status': 'PLANNED', 'host': 'OpenCode native CLI', 'model': model,
            'prompt_sha256': digest(prompt.encode()), 'budget_seconds': config.get('timeout_seconds', 600),
            'next': '显式 --execute 仅运行一次，不自动切换模型、权限或付费账户'}
    if not execute:
        return plan
    require(shutil.which(native) is not None, 'OpenCode 未安装')
    context_report = context(project)
    require(context_report['status'] == 'CURRENT', '上下文漂移，不能使用旧快照实施')
    timeout = config.get('timeout_seconds', 600)
    require(type(timeout) is int and 1 <= timeout <= 1800, '开发调用必须有界')
    before = project.snapshot()
    directory = path_in(project.root, '.ads/development/' + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    code, error = None, None
    with (directory / 'native-private.jsonl').open('wb') as out, (directory / 'stderr-private.log').open('wb') as err:
        try:
            code = execute_process(argv, cwd=project.root, stdout=out, stderr=err, timeout=timeout)
        except subprocess.TimeoutExpired:
            error = 'TIMEOUT'
    types, tools, session_ids = [], 0, set()
    for line in (directory / 'native-private.jsonl').read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            if isinstance(event.get('sessionID'), str):
                session_ids.add(event['sessionID'])
            if event.get('type') == 'error':
                error = (event.get('error') or {}).get('type', 'NATIVE_ERROR')
            part = event.get('part') or {}
            if isinstance(part, dict) and part.get('type') == 'tool':
                tools += 1
            types.append(event.get('type'))
    after = project.snapshot()
    authority_unchanged = before['files'] == after['files']
    report = {**plan, 'status': 'EXECUTED_UNVERIFIED' if code == 0 and not error and authority_unchanged else 'BLOCKED',
              'exit_code': code, 'error_type': error, 'duration_seconds': time.monotonic()-started,
              'input_subject': before, 'output_subject': after, 'authority_unchanged': authority_unchanged,
              'native_sessions_observed': len(session_ids), 'stream_tool_events': tools,
              'completion': 'NOT_VERIFIED', 'verification': '必须运行外部 ads verify 和 QA，不能凭原生退出 0 认可完成'}
    write_json(directory / 'summary.json', report)
    return report
