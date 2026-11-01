"""项目 Profile、路径边界与可复核输入快照。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


class Blocked(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Blocked(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink() and not path.parent.is_symlink(), '输出路径不得为符号链接')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.ads-write-')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(canonical(value))
            out.write(b'\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def path_in(root, name, *, exists=False):
    root = Path(root).resolve()
    candidate = Path(name)
    require(not candidate.is_absolute() and '..' not in candidate.parts, '路径必须位于项目内')
    current = root
    for part in candidate.parts:
        current /= part
        require(not current.is_symlink(), '路径不得经过符号链接')
    require(current.resolve().is_relative_to(root), '路径越出项目')
    if exists:
        require(current.exists(), f'缺失项目文件：{name}')
    return current


def git(root, *args):
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *args],
                            cwd=root, capture_output=True, timeout=15)
    require(result.returncode == 0, 'Git 基线不可读取')
    return result.stdout


class Project:
    def __init__(self, root='.', profile='ads.project.json'):
        self.root = Path(root).resolve()
        self.profile_path = path_in(self.root, profile, exists=True)
        self.config = json.loads(self.profile_path.read_text())
        require(self.config.get('schema') == 'ads-project/v1', '未知项目 Profile')
        require(isinstance(self.config.get('repositories'), list) and bool(self.config['repositories']), '必须声明仓库')
        require(isinstance(self.config.get('checks'), list), '必须显式声明检查集合')
        names = [r.get('name') for r in self.config['repositories']]
        require(all(isinstance(x, str) and x for x in names) and len(names) == len(set(names)), '仓库名称缺失或重复')
        for repo in self.config['repositories']:
            path_in(self.root, repo['path'], exists=True)
        ids = [c.get('id') for c in self.config['checks']]
        require(all(isinstance(x, str) and x for x in ids) and len(ids) == len(set(ids)), '检查 ID 缺失或重复')
        for check in self.config['checks']:
            require(check.get('role') in ('dev', 'qa'), '检查必须明确 dev/qa 责任')
            require(isinstance(check.get('argv'), list) and bool(check['argv'])
                    and all(isinstance(x, str) and x for x in check['argv']), '检查命令必须是参数数组')
            require(check.get('report', {}).get('kind') in ('junit', 'playwright'), '必须使用标准测试报告')
            require(isinstance(check.get('timeout_seconds'), int) and 1 <= check['timeout_seconds'] <= 3600, '检查必须有有界超时')
            require(check.get('effect') in ('READ_ONLY', 'IDEMPOTENT'), '验证仅自动执行只读或幂等检查')
            path_in(self.root, check.get('cwd', '.'), exists=True)
        self.state = path_in(self.root, '.ads')

    def contract(self):
        path = path_in(self.root, self.config['contract'], exists=True)
        data = json.loads(path.read_text())
        require(data.get('schema') == 'ads-contract/v1', '未知外部契约')
        if 'spec_root' in self.config:
            from .openspec import inventory
            require(data.get('spec_inventory') == inventory(self), '规格集合变化或派生视图缺少完整规格指纹')
            mapping = path_in(self.root, data['mapping_source'], exists=True)
            require(digest(mapping.read_bytes()) == data['mapping_sha256'], '测试设计映射已变化，必须重新派生')
        authority = data.get('authority', {})
        require(bool(authority.get('decision_ref')) and bool(authority.get('reviewer')), '契约缺少外部确认引用')
        obligations = data.get('obligations')
        require(isinstance(obligations, list) and bool(obligations), '不能以空契约证明完整性')
        ids = [o.get('id') for o in obligations]
        require(all(isinstance(x, str) and x for x in ids) and len(ids) == len(set(ids)), '交付义务缺失或重复')
        for obligation in obligations:
            require(isinstance(obligation.get('tests'), list) and bool(obligation['tests']), '义务必须绑定必验测试集合')
            require(isinstance(obligation.get('sources'), list) and bool(obligation['sources']), '义务必须引用原始来源')
            for source in obligation['sources']:
                material = path_in(self.root, source['path'], exists=True)
                require(digest(material.read_bytes()) == source['sha256'] and bool(source.get('locator')), '义务来源指纹或定位无效')
        return data

    def snapshot(self, *, development=False):
        files = {str(self.profile_path.relative_to(self.root)): digest(self.profile_path.read_bytes())}
        contract = path_in(self.root, self.config['contract'], exists=not development)
        require(contract.is_file() or (development and not contract.exists()), '契约必须为文件')
        files[str(contract.relative_to(self.root))] = digest(contract.read_bytes()) if contract.is_file() else 'MISSING'
        contract_data = json.loads(contract.read_text()) if contract.is_file() else {}
        for obligation in contract_data.get('obligations', []):
            for source in obligation.get('sources', []):
                path = path_in(self.root, source['path'], exists=True)
                files[str(path.relative_to(self.root))] = digest(path.read_bytes())
        if self.config.get('spec_root'):
            specs = path_in(self.root, self.config['spec_root'], exists=not development)
            if not specs.exists():
                files[self.config['spec_root']] = 'MISSING'
            for path in sorted(specs.rglob('spec.md')):
                require(not path.is_symlink(), '规格不得为符号链接')
                files[str(path.relative_to(self.root))] = digest(path.read_bytes())
        for source_dir in self.config.get('source_dirs', []):
            source = path_in(self.root, source_dir, exists=True)
            for path in sorted(source.rglob('*')):
                require(not path.is_symlink(), '来源不得为符号链接')
                if path.is_file():
                    files[str(path.relative_to(self.root))] = digest(path.read_bytes())
        review_paths = [self.config[key] for key in ('source_review', 'verification_map') if self.config.get(key)]
        for name in self.config.get('knowledge_files', []) + self.config.get('data_files', []) + review_paths + [self.config['qa'][key] for key in ('source', 'review') if key in self.config.get('qa', {})]:
            path = path_in(self.root, name, exists=not development)
            require(path.is_file() or (development and not path.exists()), '声明的上下文材料必须为文件')
            files[name] = digest(path.read_bytes()) if path.is_file() else 'MISSING'
        repositories = []
        for entry in self.config['repositories']:
            repo = path_in(self.root, entry['path'], exists=True)
            commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
            names = git(repo, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').decode().split('\0')
            inventory = {}
            for name in sorted(set(x for x in names if x)):
                if '.ads' in Path(name).parts:
                    continue
                path = path_in(repo, name)
                inventory[name] = digest(path.read_bytes()) if path.is_file() else 'MISSING'
            repositories.append({'name': entry['name'], 'commit': commit, 'files': inventory})
        value = {'files': files, 'repositories': repositories}
        return {**value, 'sha256': digest(canonical(value))}
