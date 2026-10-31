"""只读核查实际分支保护与本机依赖；缺权限不是默认通过。"""
import json
import re
import shutil
import subprocess

from .project import require


def audit(project):
    policy = project.config.get('trust', {})
    repo = policy.get('repository')
    expected = policy.get('required_checks')
    require(isinstance(repo, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), '未声明受信仓库')
    require(isinstance(expected, list) and bool(expected) and all(isinstance(x, str) and x for x in expected), '未声明必需 CI 检查集合')
    if not shutil.which('gh'):
        return {'status': 'NOT_VERIFIED', 'reason': 'GH_CLI_UNAVAILABLE'}
    result = subprocess.run(['gh', 'api', f'repos/{repo}/branches/main/protection'], capture_output=True, timeout=30)
    if result.returncode != 0:
        return {'status': 'NOT_VERIFIED', 'reason': 'PROTECTION_UNREADABLE', 'exit_code': result.returncode}
    data = json.loads(result.stdout)
    required = data.get('required_status_checks') or {}
    contexts = set(required.get('contexts', [])) | {c['context'] for c in required.get('checks', [])}
    checks = {'required_checks_present': set(expected) <= contexts,
              'strict_base': required.get('strict') is True,
              'admins_enforced': (data.get('enforce_admins') or {}).get('enabled') is True,
              'force_push_disabled': (data.get('allow_force_pushes') or {}).get('enabled') is False,
              'deletion_disabled': (data.get('allow_deletions') or {}).get('enabled') is False}
    return {'status': 'PROTECTION_OBSERVED' if all(checks.values()) else 'BLOCKED',
            'checks': checks, 'repository': repo,
            'scope': 'observed branch settings; not business correctness or independent reviewer identity'}


def doctor():
    commands = {'git': ['git', '--version'], 'opencode': ['opencode', '--version'],
                'harbor': ['harbor', '--version'], 'node': ['node', '--version'],
                'docker': ['docker', 'version', '--format', '{{.Server.Version}}'],
                'gh': ['gh', '--version'], 'docling': ['docling', '--version']}
    found = {}
    for name, argv in commands.items():
        if not shutil.which(argv[0]):
            found[name] = {'status': 'UNAVAILABLE'}
            continue
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            found[name] = {'status': 'AVAILABLE' if result.returncode == 0 else 'NOT_READY',
                           'version': result.stdout.splitlines()[0][:120] if result.stdout else None}
        except (OSError, subprocess.TimeoutExpired):
            found[name] = {'status': 'NOT_READY'}
    return {'schema': 'ads-tool-availability/v1', 'tools': found,
            'note': '安装或版本可读不代表已集成、模型有额度、容器隔离通过或具备权限'}
