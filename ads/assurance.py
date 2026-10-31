"""调用标准出处校验与部署只读探测，不自研签名协议或发布系统。"""
import json
import re
import shutil
import subprocess
from urllib.parse import urlparse
from urllib.request import urlopen

from .project import require, path_in, digest, git


def attest(project, artifact):
    path = path_in(project.root, artifact, exists=True)
    policy = project.config.get('trust', {})
    repo, workflow = policy.get('repository'), policy.get('signer_workflow')
    require(isinstance(repo, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), '必须指定可信仓库')
    require(isinstance(workflow, str) and workflow.startswith(repo + '/.github/workflows/'), '必须指定可信签署工作流')
    if not shutil.which('gh'):
        return {'status': 'NOT_VERIFIED', 'reason': 'GH_ATTESTATION_CLI_UNAVAILABLE'}
    repositories = project.config['repositories']
    primary_name = policy.get('source_repository', repositories[0]['name'])
    entry = next((r for r in repositories if r['name'] == primary_name), None)
    require(entry is not None, '找不到出处对应代码仓库')
    source = path_in(project.root, entry['path'], exists=True)
    require(not git(source, 'status', '--porcelain', '--untracked-files=all').strip(), '源码工作区不干净，不能套用提交出处')
    commit = git(source, 'rev-parse', 'HEAD').decode().strip()
    before_digest = digest(path.read_bytes())
    argv = ['gh', 'attestation', 'verify', str(path), '--repo', repo,
            '--cert-identity', f'https://github.com/{workflow}@refs/heads/main',
            '--source-digest', commit, '--source-ref', 'refs/heads/main',
            '--deny-self-hosted-runners', '--format', 'json']
    result = subprocess.run(argv, capture_output=True, timeout=60)
    if result.returncode != 0:
        return {'status': 'NOT_VERIFIED', 'reason': 'ATTESTATION_OR_POLICY_FAILED', 'exit_code': result.returncode}
    parsed = json.loads(result.stdout)
    require(isinstance(parsed, list) and bool(parsed), '出处校验没有实际验证记录')
    require(before_digest == digest(path.read_bytes()), '出处校验期间产物发生变化')
    return {'status': 'PROVENANCE_VERIFIED', 'artifact_sha256': digest(path.read_bytes()),
            'repository': repo, 'signer_workflow': workflow, 'source_commit': commit,
            'unattested_repositories': [r['name'] for r in repositories if r['name'] != primary_name],
            'business_correctness': 'NOT_IMPLIED',
            'release_authorization': 'NOT_GRANTED'}


def smoke(project):
    config = project.config.get('deployment', {})
    url, expected = config.get('health_url'), config.get('expected_build_digest')
    require(isinstance(url, str), '未配置部署后探测')
    parsed = urlparse(url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password,
            '部署探测只接受无凭据 HTTP(S) URL')
    require(isinstance(expected, str) and re.fullmatch(r'sha256:[a-f0-9]{64}', expected), '必须固定预期构建摘要')
    try:
        with urlopen(url, timeout=5) as response:
            body = response.read(16385)
            require(response.status == 200 and len(body) <= 16384, '部署探测响应无效')
        observed = json.loads(body).get(config.get('digest_field', 'build_digest'))
    except (OSError, ValueError):
        return {'status': 'FAIL', 'reason': 'RUNTIME_PROBE_FAILED'}
    return {'status': 'PASS' if observed == expected else 'FAIL',
            'expected_build_digest': expected, 'observed_build_digest': observed,
            'scope': 'configured endpoint advertised identity; not binary attestation or release authorization'}
