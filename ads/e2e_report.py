"""读取上游 e2e report-1，保留执行结果并投影低敏 Agent 行为事实。"""
import json
import math
import re

from .project import require


def _agent_evidence(result, attempts):
    """只投影 Agent/断言计数与模型用量；不复制指令、事件详情、屏幕或对话。"""
    step_groups = []
    for attempt in attempts:
        members = attempt.get('members')
        if isinstance(members, list):
            selected = [member for member in members if member.get('testId') == result['testId']]
            require(len(selected) == 1, '串行组 Agent 证据成员缺失或重复')
            step_groups.append(selected[0].get('steps', []))
        else:
            current = attempt.get('steps', [])
            require(isinstance(current, list), 'e2e attempt steps 必须为数组')
            step_groups.append(current)

    agent_steps, deterministic = [], 0
    deterministic_after_act = 0
    steps = [step for group in step_groups for step in group]
    for group in step_groups:
        last_act = max((i for i, step in enumerate(group)
                        if isinstance(step, dict) and step.get('api') == 'agent.act'), default=-1)
        if last_act >= 0:
            deterministic_after_act += sum(
                step.get('kind') == 'assertion' or step.get('api', '').startswith('expect.')
                for step in group[last_act + 1:] if isinstance(step, dict)
            )
    for step in steps:
        require(isinstance(step, dict) and isinstance(step.get('api'), str), 'e2e step 结构无效')
        if step.get('kind') == 'assertion' or step['api'].startswith('expect.'):
            deterministic += 1
        if step.get('kind') == 'agent' or step['api'].startswith('agent.'):
            require(step.get('kind') == 'agent' and step['api'] in
                    ('agent.act', 'agent.assert', 'agent.waitFor', 'agent.extract'),
                    '未知 e2e Agent step 类型')
            metrics = step.get('metrics')
            require(isinstance(metrics, dict)
                    and type(metrics.get('modelCalls')) is int and metrics['modelCalls'] >= 0
                    and type(metrics.get('actionSteps')) is int and metrics['actionSteps'] >= 0,
                    'Agent step 缺少有效的执行计数')
            cache = step.get('cache')
            if cache is not None:
                require(isinstance(cache, dict) and cache.get('mode') in
                        ('self-finalized', 'agent-concluded', 'missed'), 'Agent cache 状态无效')
            model = step.get('model')
            if model is not None:
                require(isinstance(model, dict)
                        and isinstance(model.get('provider'), str) and model['provider']
                        and isinstance(model.get('model'), str) and model['model']
                        and re.fullmatch(r'[A-Za-z0-9._:/@+-]{1,128}', model['provider'])
                        and re.fullmatch(r'[A-Za-z0-9._:/@+-]{1,128}', model['model']),
                        'Agent 模型出处无效或包含非安全字符')
                for key in ('inputTokens', 'outputTokens', 'calls'):
                    if key in model:
                        require(type(model[key]) is int and model[key] >= 0, 'Agent token/call 计数无效')
                if 'estimatedCostUsd' in model:
                    cost = model['estimatedCostUsd']
                    require(type(cost) in (int, float) and cost >= 0
                            and (type(cost) is int or math.isfinite(cost)), 'Agent 模型成本无效')
            agent_steps.append((step, metrics, cache, model))

    if not agent_steps:
        return {
            'status': 'NOT_USED',
            'mode': 'DETERMINISTIC_ONLY',
            'agent_steps': 0,
            'act_steps': 0,
            'assert_steps': 0,
            'deterministic_assertions': deterministic,
            'deterministic_assertions_after_act': 0,
            'action_steps': 0,
            'model_calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'estimated_cost_usd': None,
            'models': [],
            'model_provenance': 'NO_MODEL_CALLS',
            'model_usage_status': 'NO_MODEL_CALLS',
            'model_cost_status': 'NO_MODEL_CALLS',
            'cache_modes': {'self-finalized': 0, 'agent-concluded': 0, 'missed': 0, 'unobserved': 0},
        }

    act_steps = sum(step['api'] == 'agent.act' for step, _, _, _ in agent_steps)
    assert_steps = sum(step['api'] == 'agent.assert' for step, _, _, _ in agent_steps)
    action_steps = sum(metrics['actionSteps'] for _, metrics, _, _ in agent_steps)
    model_calls = sum(metrics['modelCalls'] for _, metrics, _, _ in agent_steps)
    input_tokens = output_tokens = 0
    costs = []
    model_steps = 0
    missing_model_steps = 0
    missing_cost_steps = 0
    models = set()
    cache_modes = {'self-finalized': 0, 'agent-concluded': 0, 'missed': 0, 'unobserved': 0}
    for _, metrics, cache, model in agent_steps:
        if cache is None:
            cache_modes['unobserved'] += 1
        else:
            cache_modes[cache['mode']] += 1
        if metrics['modelCalls'] > 0 and model is None:
            missing_model_steps += 1
        if model is not None:
            model_steps += 1
            models.add((model['provider'], model['model']))
            input_tokens += model.get('inputTokens', 0)
            output_tokens += model.get('outputTokens', 0)
            if 'estimatedCostUsd' in model:
                costs.append(model['estimatedCostUsd'])
            elif model.get('calls', 0) > 0:
                missing_cost_steps += 1
    mixed = act_steps > 0 and deterministic_after_act > 0
    return {
        'status': 'OBSERVED',
        'mode': 'AGENT_PLUS_DETERMINISTIC' if mixed else
                ('AGENT_WITHOUT_DETERMINISTIC_ASSERTION' if act_steps else 'AGENT_JUDGMENT_ONLY'),
        'agent_steps': len(agent_steps),
        'act_steps': act_steps,
        'assert_steps': assert_steps,
        'deterministic_assertions': deterministic,
        'deterministic_assertions_after_act': deterministic_after_act,
        'action_steps': action_steps,
        'model_calls': model_calls,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'estimated_cost_usd': sum(costs) if costs and missing_cost_steps == 0 and missing_model_steps == 0 else None,
        'models': [{'provider': provider, 'model': model} for provider, model in sorted(models)],
        'model_provenance': ('PARTIAL' if missing_model_steps else 'OBSERVED') if models else
                            ('NOT_REPORTED' if model_calls else 'NO_MODEL_CALLS'),
        'model_usage_status': 'NO_MODEL_CALLS' if not model_calls else
                              ('NOT_REPORTED' if not model_steps else
                               ('PARTIAL' if missing_model_steps else 'OBSERVED')),
        'model_cost_status': 'NO_MODEL_CALLS' if not model_calls else
                             ('NOT_REPORTED' if not model_steps or (missing_cost_steps and not costs) else
                              ('PARTIAL' if missing_cost_steps or missing_model_steps else 'OBSERVED')),
        'cache_modes': cache_modes,
    }


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
    # Do not use summary.executed to upgrade a case: upstream report versions may
    # undercount a runtime-skipped member of a serial group. Per-case PASS below
    # requires the selected result and its actual attempt/member evidence.
    require(all(type(summary.get(k)) is int and summary[k] >= 0 for k in
                ('discovered','selected','executed','passed','failed','interrupted','flaky','skipped')), 'e2e 计数必须为非负整数')
    require(summary.get('discovered') == len(results) and summary.get('selected') == len(selected), 'e2e 报告分母不符')
    for state in ('passed', 'interrupted', 'flaky', 'skipped'):
        require(type(summary.get(state)) is int and summary[state] == sum(r['status'] == state for r in selected), 'e2e 状态计数不符')
    require(type(summary.get('failed')) is int and summary['failed'] == sum(r['status'] in ('failed', 'timed-out') for r in selected), 'e2e 失败计数不符')
    cases, identities = [], set()
    run_clean = run.get('status') == 'passed' and type(run.get('exitCode')) is int and run['exitCode'] == 0
    for result in results:
        require(result.get('status') in statuses and type(result.get('selected')) is bool, '未知 e2e 用例状态')
        require(type(result.get('repeat')) is int and result['repeat'] >= 0, 'e2e 重复轮次必须为非负整数')
        parts = [result['testId'], result['targetId'], result['agent'], str(result['repeat'])]
        require(all(isinstance(x, str) and x for x in parts), 'e2e 用例身份缺失')
        ident = json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
        require(ident not in identities, '重复 e2e 用例身份')
        identities.add(ident)
        attempts = result.get('attempts', [])
        group_clean = True
        if result.get('serialGroupId'):
            group = groups[result['serialGroupId']]
            group_clean = group.get('status') == 'passed'
            attempts = group['attempts']
            for attempt in attempts:
                members = [m for m in attempt['members'] if m['testId'] == result['testId']]
                require(len(members) == 1 and not attempt.get('cutRetry'), '串行用例未完整执行')
                if members[0]['status'] != 'passed' or members[0].get('error') or members[0].get('secondaryErrors'):
                    group_clean = False
                if any(s.get('status') != 'passed' or s.get('error') for s in members[0].get('steps', [])):
                    group_clean = False
        agent_evidence = _agent_evidence(result, attempts)
        clean = (run_clean and group_clean and result['selected'] and result['status'] == 'passed' and bool(attempts)
                 and all(a.get('status') == 'passed' and a.get('cleanup') == 'complete'
                         and not a.get('error') and not a.get('secondaryErrors')
                         and all(s.get('status') == 'passed' and not s.get('error') for s in a.get('steps', []))
                         for a in attempts))
        state = 'PASS' if clean else ('NOT_RUN' if not result['selected'] or result['status'] in ('skipped', 'interrupted') else 'FAIL')
        cases.append({'id': ident, 'status': state, 'agent_evidence': agent_evidence})
    return cases
