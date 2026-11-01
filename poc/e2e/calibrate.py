"""运行已知虚构参考/坏变体，复用 e2e 和 ads verify，不调度模型或签署 QA。"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ads import evidence
from ads.project import Project, digest, write_json
from evaluator.grade import service

HERE = Path(__file__).resolve().parent
PACKAGES = HERE / 'node_modules'
CLI = PACKAGES / 'e2e/dist/cli/bin.js'


@contextmanager
def environment(values):
    previous = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def command(cwd, *argv):
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


def prepare(workspace, variant, probe=None, agent=False):
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / 'node_modules').symlink_to(PACKAGES, target_is_directory=True)
    (workspace / '.gitignore').write_text('node_modules\n.ads/\n__pycache__/\n*.sqlite*\n')
    (workspace / 'sources').mkdir()
    raw = ROOT / 'fixtures/project_board/raw/brief.md'
    shutil.copyfile(raw, workspace / 'sources/brief.md')
    shutil.copyfile(HERE / 'package-lock.json', workspace / 'package-lock.json')
    (workspace / 'tests').mkdir()
    config_file = 'e2e.config.ts'
    if probe:
        # 真实上游断言先失败再重试，证明报告的 flaky 不被 JUnit/PASS 掩盖。
        code = "import {test,expect} from 'e2e';\nimport fs from 'node:fs';\n"
        if probe == 'skipped':
            code += "test('report-probe',async()=>{test.skip(true,'deliberate native skipped probe');});\n"
        else:
            body = ("const seen=fs.existsSync(process.env.ADS_PROBE_FLAG);fs.writeFileSync(process.env.ADS_PROBE_FLAG,'1');expect(seen).toBe(true);"
                    if probe == 'flaky' else 'expect(2+2).toBe(4);')
            code += "test('report-probe',async()=>{" + body + "});\n"
        (workspace / 'tests/probe.e2e.ts').write_text(code)
        (workspace / 'e2e.config.ts').write_text("export default {targets:[{name:'tools',platform:'tools'}],tests:['tests/probe.e2e.ts'],retries:"
                                                 + ('1' if probe == 'flaky' else '0') + ",reporters:['list','junit'],cache:'off'};\n")
        title, target = 'tests/probe.e2e.ts::report-probe', 'tools'
    else:
        shutil.copytree(ROOT / 'fixtures/project_board/base', workspace / 'app')
        command(workspace / 'app', 'git', 'apply', str(ROOT / 'fixtures/project_board/patches' / (variant + '.patch')))
        shutil.copyfile(HERE / 'e2e.config.ts', workspace / 'e2e.config.ts')
        shutil.copyfile(HERE / 'assert_product.py', workspace / 'assert_product.py')
        if agent:
            shutil.copyfile(HERE / 'e2e.agent.config.ts', workspace / 'e2e.agent.config.ts')
            shutil.copyfile(HERE / 'tests/agent-journey.e2e.ts', workspace / 'tests/agent-journey.e2e.ts')
            config_file = 'e2e.agent.config.ts'
            title = 'tests/agent-journey.e2e.ts::agent-save-refresh-export'
        else:
            shutil.copyfile(HERE / 'tests/journey.e2e.ts', workspace / 'tests/journey.e2e.ts')
            title = 'tests/journey.e2e.ts::save-refresh-export'
        target = 'chromium'
    if agent and "cache: 'off'" not in (workspace / 'e2e.config.ts').read_text():
        raise ValueError('Agent evaluation requires the inherited e2e cache: off policy')
    case = json.dumps([title,target,'default','0'], ensure_ascii=False, separators=(',', ':'))
    write_json(workspace / 'contract.json', {'schema':'ads-contract/v1',
        'authority':{'reviewer':'synthetic-fixture-calibration','decision_ref':'frozen-ADS-M0-001'},
        'obligations':[{'id':'journey','sources':[{'path':'sources/brief.md','sha256':digest(raw.read_bytes()),'locator':'full-document'}],
                        'tests':[{'check':'e2e','case':case}]}]})
    write_json(workspace / 'ads.project.json', {'schema':'ads-project/v1','repositories':[{'name':'fictional','path':'.'}],
        'source_dirs':['sources'],'contract':'contract.json','checks':[{'id':'e2e','role':'dev','effect':'IDEMPOTENT','timeout_seconds':120,
            'argv':[shutil.which('node'),'--disable-warning=ExperimentalWarning',str(CLI),'run','--config',config_file,'--output','{run_dir}/e2e'],
            'report':{'kind':'e2e','path':'.ads/runs/{run_id}/e2e/report.json'}}]})
    command(workspace, 'git', 'init', '-q')
    command(workspace, 'git', 'add', '.')
    command(workspace, 'git', '-c','user.name=ADS synthetic fixture','-c','user.email=ads@example.invalid','commit','-qm','frozen test input')
    return Project(workspace)


def collect(project, run, expected, out, agent=False):
    check = run['checks'][0]
    report_path = project.root / check['report']
    native = json.loads(report_path.read_text())['run']
    statuses = [r['status'] for r in native['results']]
    decision = evidence.decide(project)
    errors = [a.get('error', {}) for r in native['results'] for a in r['attempts'] if a.get('error')]
    marker = {'no_persistence':'expect.toHaveValue failed', 'bad_export':'AssertionError: 导出缺列或列序错误'}.get(out.name)
    expected_failure = any(e.get('category') == 'test' and marker in e.get('message', '') for e in errors) if marker else False
    correct = ((expected == 'PASS' and run['status'] == 'PASS' and decision['development'] == 'DEV_VERIFIED_LOCAL')
               or (expected == 'FAIL' and run['status'] == 'FAIL' and check['exit_code'] == 1
                   and 'failed' in statuses and not native['errors'] and check['failure'] is None and expected_failure))
    agent_evidence = check['cases'][0].get('agent_evidence') if agent and check.get('cases') else None
    if agent:
        cache_modes = (agent_evidence or {}).get('cache_modes', {})
        agent_observed = (agent_evidence or {}).get('status') == 'OBSERVED'
        model_calls = (agent_evidence or {}).get('model_calls', 0)
        if (not agent_observed or model_calls == 0 or cache_modes.get('self-finalized', 0) > 0
                or (agent_evidence or {}).get('model_provenance') != 'OBSERVED'
                or (agent_evidence or {}).get('status') == 'BLOCKED'):
            state = 'BLOCKED'
        elif (agent_evidence.get('mode') != 'AGENT_PLUS_DETERMINISTIC'
              or agent_evidence.get('act_steps', 0) == 0
              or agent_evidence.get('deterministic_assertions_after_act', 0) == 0
              or not correct):
            state = 'FAIL'
        else:
            state = 'PASS'
    else:
        state = 'PASS' if correct else 'FAIL'
    # 原始报告、下载、截图、轨迹、日志均保留；不把基础设施错误算作检错成功。
    destination = out / 'evidence'
    shutil.copytree(project.root / '.ads/runs' / run['run_id'], destination)
    return {'expected':expected,'actual':run['status'],'development':decision['development'],
            'native_exit_code':check['exit_code'],'native_statuses':statuses,
            'expected_failure_marker':marker,'expected_failure_observed':expected_failure,
            'subject_sha256':run['subject']['sha256'],'report_sha256':check['report_sha256'],
            'agent_evidence':agent_evidence,
            'status':state}


def calibrate(out, browser=True, agent=False):
    require_tools = CLI.is_file() and shutil.which('node')
    if not require_tools:
        raise ValueError('先在 poc/e2e 运行 npm ci；不回退其他测试器')
    out.mkdir(parents=True, exist_ok=False)
    rows, probes = [], []
    for variant, expected in ([('reference','PASS'),('no_persistence','FAIL'),('bad_export','FAIL')] if browser else []):
        location = out / variant
        location.mkdir()
        project = prepare(location / 'workspace', variant)
        with service(project.root / 'app', location) as url, environment({
            'ADS_E2E_URL':url, 'ADS_PYTHON':sys.executable, 'ADS_DB_PATH':str(project.root / 'app/runtime.sqlite'),
            'E2E_TELEMETRY_DISABLED':'1', 'CI':'1'}):
            row = collect(project, evidence.run_checks(project), expected, location)
        rows.append({'variant':variant,**row})
    for probe in ('passed','flaky','skipped'):
        location = out / probe
        location.mkdir()
        project = prepare(location / 'workspace', None, probe)
        with environment({'ADS_PROBE_FLAG':str(location / 'attempt.flag'),'E2E_TELEMETRY_DISABLED':'1','CI':'1'}):
            run = evidence.run_checks(project)
        check = run['checks'][0]
        native = json.loads((project.root / check['report']).read_text())['run']
        raw_status = native['results'][0]['status']
        good = check['exit_code'] == 0 and raw_status == probe and run['status'] == ('PASS' if probe == 'passed' else 'FAIL')
        if probe == 'flaky':
            # 展示标准 JUnit 的确丢失 flaky；生产适配使用原生报告。
            junit = (project.root / check['report']).with_name('junit.xml').read_bytes()
            good = good and evidence.parse('junit',junit)[0]['status'] == 'PASS'
        shutil.copytree(project.root / '.ads/runs' / run['run_id'], location / 'evidence')
        probes.append({'probe':probe,'native_exit_code':check['exit_code'],'native_status':raw_status,
                       'ads_status':run['status'],'status':'PASS' if good else 'FAIL'})
    agent_row = None
    if agent:
        location = out / 'agent'
        location.mkdir()
        model_id = os.environ.get('ADS_E2E_OPENCODE_MODEL', '').strip()
        if not model_id:
            agent_row = {'status':'BLOCKED','reason':'ADS_E2E_OPENCODE_MODEL_NOT_CONFIGURED'}
        else:
            project = prepare(location / 'workspace', 'reference', agent=True)
            with service(project.root / 'app', location) as url, environment({
                'ADS_E2E_URL':url, 'ADS_PYTHON':sys.executable, 'ADS_DB_PATH':str(project.root / 'app/runtime.sqlite'),
                'E2E_TELEMETRY_DISABLED':'1', 'CI':'1'}):
                agent_row = collect(project, evidence.run_checks(project), 'PASS', location, agent=True)
    overall = 'FAIL' if any(r['status'] == 'FAIL' for r in rows+probes) else (
        'BLOCKED' if agent_row and agent_row['status'] == 'BLOCKED' else
        ('FAIL' if agent_row and agent_row['status'] == 'FAIL' else 'PASS'))
    return {'status':overall,
            'browser_journeys':rows,'native_report_probes':probes,'agent_journey':agent_row,
            'framework':'e2e@0.22.0 / @e2e-dev/web@0.15.4',
            'scope':'known fictional variants and real upstream execution; agent profile uses OpenCode Console OAuth; not independent QA identity or model-generated code',
            'model_execution':('NOT_RUN' if not agent else (agent_row['status'] if agent_row else 'BLOCKED')),
            'protected_execution':'NOT_VERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reports-only',action='store_true')
    parser.add_argument('--agent',action='store_true',help='Run the OpenCode Console-backed agent journey; requires an explicit model and e2e login')
    args = parser.parse_args()
    try:
        summary = calibrate(args.out.resolve(), not args.reports_only, args.agent)
    except Exception as exc:
        summary = {'status':'INFRA_ERROR','error_type':type(exc).__name__,'detail':str(exc)[:300]}
    write_json(args.out.resolve() / 'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    sys.exit(0 if summary['status'] == 'PASS' else (3 if summary['status'] == 'BLOCKED' else 2))
