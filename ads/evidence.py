"""运行项目声明的专业测试器；标准结果、日志和版本绑定的薄投影。"""
import json
from pathlib import Path
import subprocess
import time
from xml.etree import ElementTree as ET
import uuid

from .project import Blocked, require, digest, path_in, write_json
from .process import execute
from .e2e_report import e2e


def junit(data):
    require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), '报告不得含 DTD')
    root = ET.fromstring(data)
    require(root.tag in ('testsuite', 'testsuites'), '未知 JUnit 根结构')
    for suite in [root, *root.findall('.//testsuite')]:
        actual = list(suite.iter('testcase'))
        if suite.get('tests') is not None:
            require(int(suite.get('tests')) == len(actual), 'JUnit 声明数量与实际用例不符')
        for attr, tag in (('failures', 'failure'), ('errors', 'error'), ('skipped', 'skipped')):
            if suite.get(attr) is not None:
                require(int(suite.get(attr)) == sum(c.find(tag) is not None for c in actual), 'JUnit 聚合状态与用例不符')
    cases = []
    for case in root.iter('testcase'):
        name = case.get('name')
        require(bool(name), 'JUnit 测试缺少名称')
        ident = '.'.join(x for x in (case.get('classname'), name) if x)
        children = [x.tag for x in case]
        result = 'FAIL' if any(x in children for x in ('failure', 'error')) else ('NOT_RUN' if 'skipped' in children else 'PASS')
        cases.append({'id': ident, 'status': result})
    require(bool(cases), '空 JUnit 报告不能通过')
    return cases


def playwright(data):
    root = json.loads(data)
    require(not root.get('errors'), 'Playwright 存在全局错误')
    cases = []
    def visit(suite, prefix):
        for spec in suite.get('specs', []):
            for test in spec.get('tests', []):
                identity = ' / '.join(prefix + [spec['title'], test.get('projectName', '')]).strip(' /')
                attempts = test.get('results', [])
                status = 'PASS' if (attempts and all(x.get('status') == 'passed' for x in attempts)
                                    and test.get('expectedStatus', 'passed') == 'passed'
                                    and spec.get('ok', True) is True
                                    and test.get('status', 'expected') == 'expected') else 'FAIL'
                if attempts and all(x.get('status') == 'skipped' for x in attempts):
                    status = 'NOT_RUN'
                cases.append({'id': identity, 'status': status})
        for child in suite.get('suites', []):
            visit(child, prefix + [child.get('title', '')])
    for suite in root.get('suites', []):
        visit(suite, [suite.get('title', '')])
    require(bool(cases), '空 Playwright 报告不能通过')
    return cases


def parse(kind, data):
    require(len(data) <= 20 * 1024 * 1024, '测试报告过大')
    return {'junit': junit, 'playwright': playwright, 'e2e': e2e}[kind](data)


def run_checks(project, role='dev'):
    require(role in ('dev', 'qa'), '未知执行责任')
    contract = project.contract()
    if role == 'qa':
        from .qa import reviewed_baseline
        reviewed_baseline(project)
    before = project.snapshot()
    run_id = uuid.uuid4().hex
    directory = path_in(project.root, f'.ads/runs/{run_id}')
    directory.mkdir(parents=True, exist_ok=False)
    selected = [x for x in project.config['checks'] if x['role'] == role]
    require(bool(selected), '没有配置该责任的测试检查，不能默认通过')
    results = []
    for index, check in enumerate(selected):
        report_name = check['report']['path'].replace('{run_id}', run_id)
        report_path = path_in(project.root, report_name)
        require(report_path.is_relative_to(directory), '原始报告必须写入本次全新运行目录')
        require(not report_path.exists(), '拒绝复用已存在测试报告')
        argv = [x.replace('{run_id}', run_id).replace('{run_dir}', str(directory)) for x in check['argv']]
        started = time.monotonic()
        out, err = directory / f'{index}-stdout.log', directory / f'{index}-stderr.log'
        exit_code, failure = None, None
        with out.open('wb') as stdout, err.open('wb') as stderr:
            try:
                exit_code = execute(argv, cwd=path_in(project.root, check.get('cwd', '.')),
                                    stdout=stdout, stderr=stderr, timeout=check['timeout_seconds'])
            except subprocess.TimeoutExpired:
                failure = 'TIMEOUT'
            except OSError:
                failure = 'EXECUTION_ERROR'
        cases = []
        try:
            require(report_path.is_file() and not report_path.is_symlink(), '缺少本次原始测试报告')
            raw = report_path.read_bytes()
            cases = parse(check['report']['kind'], raw)
            report_digest = digest(raw)
        except (OSError, ValueError, ET.ParseError, KeyError, TypeError):
            failure = failure or 'INVALID_REPORT'
            report_digest = None
        passed = exit_code == 0 and failure is None and cases and all(c['status'] == 'PASS' for c in cases)
        results.append({'check_id': check['id'], 'role': role, 'argv': argv, 'exit_code': exit_code,
                        'status': 'PASS' if passed else 'FAIL', 'failure': failure, 'cases': cases,
                        'duration_seconds': time.monotonic() - started,
                        'report': report_name, 'report_sha256': report_digest,
                        'logs': {str(p.relative_to(project.root)): digest(p.read_bytes()) for p in (out, err)}})
    after = project.snapshot()
    report = {'schema': 'ads-project-run/v1', 'run_id': run_id, 'role': role,
              'subject': before, 'subject_unchanged': before == after,
              'status': 'PASS' if before == after and all(x['status'] == 'PASS' for x in results) else 'FAIL',
              'checks': results, 'trust': 'LOCAL_EXECUTION', 'independent_qa_identity': 'NOT_VERIFIED',
              'contract_authority': contract['authority']}
    write_json(directory / 'run.json', report)
    write_json(path_in(project.root, f'.ads/latest-{role}.json'), {'run_id': run_id})
    return report


def load_current(project, role='dev'):
    pointer = json.loads(path_in(project.root, f'.ads/latest-{role}.json', exists=True).read_text())
    run = json.loads(path_in(project.root, f'.ads/runs/{pointer["run_id"]}/run.json', exists=True).read_text())
    require(run.get('schema') == 'ads-project-run/v1' and run.get('role') == role, '运行记录身份不符')
    require(run.get('subject') == project.snapshot() and run.get('subject_unchanged') is True, '代码、来源、契约或配置已经漂移')
    for check in run['checks']:
        report = path_in(project.root, check['report'], exists=True)
        require(digest(report.read_bytes()) == check['report_sha256'], '原始测试报告已被修改')
        actual = parse(next(x for x in project.config['checks'] if x['id'] == check['check_id'])['report']['kind'], report.read_bytes())
        require(actual == check['cases'], '运行记录与原始报告不一致')
        for name, sha in check['logs'].items():
            require(digest(path_in(project.root, name, exists=True).read_bytes()) == sha, '执行日志已被修改')
    return run


def decide(project):
    contract = project.contract()
    run = load_current(project)
    obligations = []
    for obligation in contract['obligations']:
        required = obligation['tests']
        outcomes = []
        for target in required:
            check_id, test_id = target['check'], target['case']
            matching = [c['status'] for result in run['checks'] if result['check_id'] == check_id
                        and result['status'] == 'PASS' for c in result['cases'] if c['id'] == test_id]
            outcomes.append(bool(matching) and all(status == 'PASS' for status in matching))
        obligations.append({'id': obligation['id'], 'status': 'PASS' if all(outcomes) else 'NOT_VERIFIED'})
    from .sources import discover
    discovered = discover(project)
    good = run['status'] == 'PASS' and all(x['status'] == 'PASS' for x in obligations) and discovered['status'] == 'INVENTORIED'
    alignment_state = 'NOT_REVIEWED'
    if project.config.get('source_review'):
        from .alignment import reconcile
        alignment_state = reconcile(project)['status']
        good = good and alignment_state == 'SCOPED_RECONCILED_LOCAL'
    return {'schema': 'ads-project-decision/v1', 'development': 'DEV_VERIFIED_LOCAL' if good else 'BLOCKED',
            'obligations': obligations, 'subject_sha256': run['subject']['sha256'],
            'source_inventory': discovered['status'], 'requirements_alignment': alignment_state,
            'semantic_completeness': 'NOT_VERIFIED',
            'qa_independence': 'NOT_VERIFIED', 'release': 'NOT_VERIFIED',
            'scope': 'configured contract and local runner; not absolute requirement completeness'}
