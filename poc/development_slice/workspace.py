"""只准备候选输入和导出补丁；不代替 OpenCode 实现，不运行候选代码。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ('app.py', 'web/index.html', 'web/app.js')
PROMPT = '''请从 raw/ 全部原始资料独立核对要求，修复虚构项目的完整用户旅程。
先列出资料范围、功能遗漏和未知，再实现页面菜单、七个只读持久化字段、加载失败提示、备注保存/刷新、保存后导出 XLSX、权限拒绝。
不读取框架仓库、参考补丁或外部验收答案，不根据现有实现反推预期。
修改交付代码仅限 app.py、web/index.html、web/app.js；可在 dev_tests/ 编写并运行开发自测。
保留 raw/、AGENTS.md、TASK.md、opencode.json、.gitignore 不变。失败要定位原因，禁止通过降低预期自称通过。
必须启动真实服务并运行自测；记录执行命令、失败、修复和未验证部分。最后报告真实结果，不声称独立 QA 或发布完成。
'''


def git(root, *args):
    return subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *args], cwd=root, check=True, capture_output=True).stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(run):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    workspace = run / 'workspace'
    shutil.copytree(ROOT / 'fixtures/project_board/base', workspace)
    shutil.copytree(ROOT / 'fixtures/project_board/raw', workspace / 'raw')
    (workspace / 'TASK.md').write_text(PROMPT)
    (workspace / 'AGENTS.md').write_text('这是可丢弃的虚构开发实验。以 raw/ 为需求来源，执行 TASK.md。不得读取上级框架、评分器或参考解。开发自测不等于独立验收。\n')
    (workspace / '.gitignore').write_text('__pycache__/\n*.pyc\nruntime.sqlite*\n.ads-runtime/\n')
    (workspace / 'opencode.json').write_text(json.dumps({
        '$schema': 'https://opencode.ai/config.json', 'update': 'disable', 'share': 'disabled',
        'permissions': [
            {'action': '*', 'resource': '*', 'effect': 'ask'},
            {'action': 'read', 'resource': '*', 'effect': 'allow'},
            {'action': 'edit', 'resource': '*', 'effect': 'allow'},
            {'action': 'shell', 'resource': '*', 'effect': 'ask'},
            {'action': 'subagent', 'resource': '*', 'effect': 'deny'},
        ],
    }, indent=2))
    git(workspace, 'init', '-q')
    git(workspace, 'add', '.')
    git(workspace, '-c', 'user.name=ADS synthetic experiment', '-c', 'user.email=ads@example.invalid',
        'commit', '-qm', 'frozen fictional development input')
    baseline = git(workspace, 'rev-parse', 'HEAD').decode().strip()
    files = [p for p in workspace.rglob('*') if p.is_file() and '.git' not in p.relative_to(workspace).parts]
    manifest = {'schema': 'ads-development-workspace/v1', 'base_commit': baseline,
                'framework_commit': git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
                'protected_files': {p.relative_to(workspace).as_posix(): sha(p) for p in files
                                    if p.relative_to(workspace).as_posix() not in SOURCE},
                'source_files': {name: sha(workspace / name) for name in SOURCE},
                'scope': 'local input preparation; not a filesystem sandbox',
                'development_status': 'NOT_RUN'}
    (run / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return {'status': 'READY', 'workspace': str(workspace), 'development_status': 'NOT_RUN'}


def export(run, out):
    run, out = Path(run).resolve(), Path(out).resolve()
    workspace = run / 'workspace'
    manifest = json.loads((run / 'manifest.json').read_text())
    if manifest.get('schema') != 'ads-development-workspace/v1':
        raise ValueError('未知工作区')
    for name, digest in manifest['protected_files'].items():
        path = workspace / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError('原始资料或开发协议被修改')
    # 提交后的修改同样从最初基线取差异，不能只看 staged/unstaged。
    changed = git(workspace, 'diff', '--no-ext-diff', '--no-textconv', '--name-only', manifest['base_commit']).decode().splitlines()
    if any(name not in SOURCE and not name.startswith('dev_tests/') for name in changed):
        raise ValueError('候选修改了交付白名单之外的文件')
    for path in workspace.rglob('*'):
        rel = path.relative_to(workspace)
        if '.git' in rel.parts or '__pycache__' in rel.parts or '.ads-runtime' in rel.parts:
            continue
        if path.is_symlink():
            raise ValueError('不接受候选符号链接')
        if path.is_file() and rel.as_posix() not in SOURCE and rel.as_posix() not in manifest['protected_files']:
            if not rel.as_posix().startswith('dev_tests/') and not rel.name.startswith('runtime.sqlite'):
                raise ValueError('候选新增未授权文件')
    for name in SOURCE:
        if not (workspace / name).is_file():
            raise ValueError('候选删除交付文件')
    patch = git(workspace, 'diff', '--no-ext-diff', '--no-textconv', '--binary', manifest['base_commit'], '--', *SOURCE)
    if not patch:
        raise ValueError('没有实际候选改动')
    out.mkdir(parents=True, exist_ok=False)
    target = out / 'candidate.patch'
    target.write_bytes(patch)
    from evaluator.grade import validate_patch
    validate_patch(target)
    report = {'status': 'EXPORTED', 'base_commit': manifest['base_commit'],
              'candidate_patch_sha256': sha(target), 'source_files': {name: sha(workspace / name) for name in SOURCE},
              'opencode_execution': 'NOT_VERIFIED', 'independent_acceptance': 'NOT_RUN',
              'note': '补丁存在不证明由 OpenCode 生成，也不证明开发测试或交付通过'}
    (out / 'candidate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('prepare').add_argument('run', type=Path)
    exp = sub.add_parser('export')
    exp.add_argument('run', type=Path)
    exp.add_argument('out', type=Path)
    args = parser.parse_args()
    try:
        report = prepare(args.run) if args.action == 'prepare' else export(args.run, args.out)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {'status': 'BLOCKED', 'error_type': type(exc).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] in ('READY', 'EXPORTED') else 3


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
