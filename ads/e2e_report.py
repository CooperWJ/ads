"""读取上游 e2e report-1，保留被 JUnit 折叠的 flaky、筛选和清理失败。"""
import json

from .project import require


def e2e(data):
    document = json.loads(data)
    require(document.get('schemaVersion') == 'report-1', '未知 e2e 报告版本')
    run = document['run']
    require(run.get('specVersion') == '0.1' and run.get('runner', {}).get('name') == 'e2e', '未知 e2e 运行器协议')
    require(not run.get('errors'), 'e2e 存在运行级错误')
    require(not run.get('explore'), '探索发现不能代替必验测试')
    carried = run.get('carried') or {}
    require(not any(carried.get(k) for k in ('results', 'serialGroups', 'errors')), '历史未关闭测试不能被局部重跑隐藏')
    results = run['results']
    require(isinstance(results, list) and bool(results), '空 e2e 报告不能通过')
    groups = {g['id']: g for g in run.get('serialGroups', [])}
    require(len(groups) == len(run.get('serialGroups', [])), '重复串行组')
    statuses = ('passed', 'failed', 'timed-out', 'interrupted', 'flaky', 'skipped')
    selected = [r for r in results if r.get('selected') is True]
    summary = run['summary']
    require(summary.get('discovered') == len(results) and summary.get('selected') == len(selected), 'e2e 报告分母不符')
    for state in ('passed', 'interrupted', 'flaky', 'skipped'):
        require(type(summary.get(state)) is int and summary[state] == sum(r['status'] == state for r in selected), 'e2e 状态计数不符')
    require(type(summary.get('failed')) is int and summary['failed'] == sum(r['status'] in ('failed', 'timed-out') for r in selected), 'e2e 失败计数不符')
    cases, identities = [], set()
    run_clean = run.get('status') == 'passed' and type(run.get('exitCode')) is int and run['exitCode'] == 0
    for result in results:
        require(result.get('status') in statuses and type(result.get('selected')) is bool, '未知 e2e 用例状态')
        parts = [result['testId'], result['targetId'], result['agent'], str(result['repeat'])]
        require(all(isinstance(x, str) and x for x in parts), 'e2e 用例身份缺失')
        ident = json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
        require(ident not in identities, '重复 e2e 用例身份')
        identities.add(ident)
        attempts = result.get('attempts', [])
        group_clean = True
        if result.get('serialGroupId'):
            group = groups[result['serialGroupId']]
            attempts = group['attempts']
            for attempt in attempts:
                members = [m for m in attempt['members'] if m['testId'] == result['testId']]
                require(len(members) == 1 and not attempt.get('cutRetry'), '串行用例未完整执行')
                if members[0]['status'] != 'passed' or members[0].get('error') or members[0].get('secondaryErrors'):
                    group_clean = False
                if any(s.get('status') != 'passed' or s.get('error') for s in members[0].get('steps', [])):
                    group_clean = False
        clean = (run_clean and group_clean and result['selected'] and result['status'] == 'passed' and bool(attempts)
                 and all(a.get('status') == 'passed' and a.get('cleanup') == 'complete'
                         and not a.get('error') and not a.get('secondaryErrors')
                         and all(s.get('status') == 'passed' and not s.get('error') for s in a.get('steps', []))
                         for a in attempts))
        state = 'PASS' if clean else ('NOT_RUN' if not result['selected'] or result['status'] in ('skipped', 'interrupted') else 'FAIL')
        cases.append({'id': ident, 'status': state})
    return cases
