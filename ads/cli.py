"""ADS 统一薄入口：复用宿主、项目审批与专业测试器。"""
import argparse
import json
from pathlib import Path
import sys
import subprocess

from .project import Blocked, Project, require, path_in, write_json
from . import assurance, benchmark, engineering, evidence, qa, sources, gates, openspec, alignment, integrations, delivery


def init(root, superpowers=False, e2e=False):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = path_in(root, 'ads.project.json')
    if superpowers and target.exists():
        result = integrations.superpowers(root)
        if e2e:
            result['e2e'] = integrations.e2e(root)
        return result
    if e2e and target.exists():
        return integrations.e2e(root)
    require(not target.exists(), '已有 Profile 不可覆盖，请增量修改')
    integration = integrations.superpowers(root) if superpowers else None
    e2e_integration = integrations.e2e(root) if e2e else None
    write_json(target, {'schema': 'ads-project/v1', 'repositories': [{'name': 'main', 'path': '.'}],
                        'source_dirs': ['docs/project/sources'], 'contract': '.ads/contract.json',
                        'spec_root': 'openspec/specs', 'verification_map': 'docs/project/verification-map.json',
                        'knowledge_files': [], 'checks': []})
    path_in(root, 'docs/project/sources').mkdir(parents=True, exist_ok=True)
    task = path_in(root, 'TASK.md')
    if not task.exists():
        task.write_text('读取 docs/project/sources/ 原始资料和已有 OpenSpec。先说明要交付的用户行为及关键歧义；沿用已有确认，不从实现反推预期。按一个可操作功能切片实现、启动、调试和自测。缺陷优先使用 Superpowers systematic-debugging，实现使用 test-driven-development，完成前使用 verification-before-completion。仅对影响实现的业务选择提问；未知不得假称确认。记录真实结果与未验证项，不替代独立 QA 或发布授权。\n')
    # 原生入口只委托同一 CLI，不复制 OpenSpec/QA 生命周期，不覆盖任何已有路由。
    commands = path_in(root, '.opencode/commands')
    commands.mkdir(parents=True, exist_ok=True)
    for name, body in {
        'ads-status': '先运行 `ads status`，只读报告实际阻断和未验证项，不补造 PASS。',
        'ads-develop': '先运行 `ads context check`。漂移时重新读取来源并规划，禁止回放旧副作用。读取项目原始来源与已确认规格，按用户切片实际开发和自测。使用 Superpowers 时通过 OpenCode 原生 skill 工具加载：疑似缺陷先 systematic-debugging，再 test-driven-development；新增能力仅在需求不明确时 brainstorming，已有 OpenSpec 规格不重复访谈，writing-plans 只安排实现步骤。交付前加载 verification-before-completion，实际运行测试并核对结果。缺少插件时明确报告，不能假称调用成功。禁止改变验收预期换 PASS。完成后运行 `ads verify`，开发结果不能替代 QA 或发布授权。',
        'ads-qa': '先运行 `ads qa import`，分别核对用例质量与需求一致性。只消费既有 QA 决策投影，不自行批准。运行 `ads verify --role qa` 和 `ads qa evaluate`；DEV 结果不能替代 QA 执行。',
    }.items():
        path = commands / (name + '.md')
        if not path.exists():
            path.write_text('---\ndescription: "ADS 项目原生薄入口"\nagent: build\n---\n\n' + body + '\n')
    return {'status': 'INITIALIZED', 'next': '将原始资料放入 docs/project/sources，编辑 TASK.md 后开始探索与开发；正式验收另用确认契约和项目测试',
            'contract_created_or_approved': False, 'superpowers': integration, 'e2e': e2e_integration}


def main(argv=None):
    parser = argparse.ArgumentParser(description='ADS 项目工程与证据薄适配 CLI')
    parser.add_argument('--root', default='.')
    sub = parser.add_subparsers(dest='command', required=True)
    initialize = sub.add_parser('init')
    initialize.add_argument('--superpowers', action='store_true', help='接入官方 OpenCode V2 Superpowers 插件；保留已有配置')
    initialize.add_argument('--e2e', action='store_true', help='注册已安装的官方 e2e MCP 和技能；不自动安装依赖')
    route = sub.add_parser('route')
    route.add_argument('description')
    sub.add_parser('discover')
    align = sub.add_parser('reconcile')
    align.add_argument('--preview', action='store_true')
    compiler = sub.add_parser('compile')
    compiler.add_argument('--preview', action='store_true')
    context = sub.add_parser('context')
    context.add_argument('action', choices=('freeze', 'check'))
    verify = sub.add_parser('verify')
    verify.add_argument('--role', choices=('dev', 'qa'), default='dev')
    state = sub.add_parser('status')
    state.add_argument('--gate', choices=('development', 'release'), default='development')
    sub.add_parser('gate')
    sub.add_parser('doctor')
    intake = sub.add_parser('qa')
    intake.add_argument('action', choices=('import', 'evaluate', 'defects'))
    intake.add_argument('--gate', choices=('execution', 'independent'), default='execution')
    develop = sub.add_parser('develop')
    develop.add_argument('--model', required=True)
    develop.add_argument('--execute', action='store_true')
    develop.add_argument('--session', help='明确续接 OpenCode 原生 Session；不自动重放副作用')
    trust = sub.add_parser('attest')
    trust.add_argument('artifact')
    sub.add_parser('smoke')
    compare = sub.add_parser('benchmark')
    compare.add_argument('base')
    compare.add_argument('candidate')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = init(args.root, args.superpowers, args.e2e)
        elif args.command == 'doctor':
            result = gates.doctor()
        elif args.command == 'route':
            result = engineering.route(args.description)
        elif args.command == 'benchmark':
            root = Path(args.root).resolve()
            result = benchmark.compare(json.loads(path_in(root, args.base, exists=True).read_text()),
                                       json.loads(path_in(root, args.candidate, exists=True).read_text()))
        else:
            project = Project(args.root)
            if args.command == 'reconcile':
                result = alignment.reconcile(project, args.preview)
            elif args.command == 'compile':
                result = ({'status':'PREVIEW_ONLY','spec_inventory':openspec.inventory(project),
                           'scenarios':openspec.scenarios(project),'approval_created':False}
                          if args.preview else openspec.compile_contract(project))
            elif args.command == 'discover':
                result = sources.discover(project)
                write_json(path_in(project.root, '.ads/discovery.json'), result)
            elif args.command == 'context':
                result = engineering.context(project, args.action == 'freeze')
            elif args.command == 'verify':
                run = evidence.run_checks(project, args.role)
                result = {'status': run['status'], 'run_id': run['run_id'], 'role': run['role'],
                          'subject_sha256': run['subject']['sha256'], 'subject_unchanged': run['subject_unchanged'],
                          'development_binding': run.get('development_binding', {'status': 'NOT_LINKED'}),
                          'checks': [{'id': c['check_id'], 'status': c['status'], 'failure': c['failure']} for c in run['checks']],
                          'trust': run['trust']}
            elif args.command == 'gate':
                result = gates.audit(project)
            elif args.command == 'status':
                if args.gate == 'release':
                    result = delivery.evaluate(project)
                else:
                    result = evidence.decide(project)
                result['selected_gate'] = args.gate
            elif args.command == 'qa':
                if args.action == 'defects':
                    result = qa.defects(project)
                elif args.action == 'evaluate':
                    result = qa.evaluate(project)
                    result['selected_gate'] = args.gate
                    if args.gate == 'independent':
                        result['status'] = 'NOT_VERIFIED'
                else:
                    config = project.config.get('qa', {})
                    result = qa.intake(path_in(project.root, config['source'], exists=True))
                    try:
                        result['mapping'] = qa.candidates(result, project.contract())
                    except Blocked as exc:
                        result['mapping'] = []
                        result['requirement_reconciliation'] = 'BLOCKED'
                        result['mapping_failure'] = str(exc)
                    result['status'] = 'IMPORTED'
                    write_json(path_in(project.root, '.ads/qa-intake.json'), result)
            elif args.command == 'develop':
                result = engineering.develop(project, args.model, args.execute, session=args.session)
            elif args.command == 'attest':
                result = assurance.attest(project, args.artifact)
            elif args.command == 'smoke':
                result = assurance.smoke(project)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        values = (result.get('status'), result.get('development'), result.get('case_execution'), result.get('quality'))
        blocked = any(value in ('FAIL', 'BLOCKED', 'NOT_VERIFIED', 'REPLAN_REQUIRED', 'UNKNOWN', 'REVISION_REQUIRED') for value in values)
        return 3 if blocked else 0
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error_type': type(exc).__name__, 'reason': str(exc)}, ensure_ascii=False))
        return 3


if __name__ == '__main__':
    sys.exit(main())
