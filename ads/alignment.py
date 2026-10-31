"""独立来源→交付义务差集；只消费既有决策，不创建审批状态机。"""
import json
from .project import require, path_in
from .sources import discover


def reconcile(project, preview=False):
    discovered = discover(project)
    require(discovered['status'] == 'INVENTORIED', '来源尚有未读区域，不能认可需求对齐')
    units = [unit for source in discovered['sources'] for unit in source['extraction']['units']]
    by_id = {u['id']: u for u in units}
    require(len(by_id) == len(units) and bool(units), '来源目录重叠、重复片段或没有观察')
    contract = project.contract()
    obligations = {o['id'] for o in contract['obligations']}
    if preview:
        return {'status': 'CANDIDATE_REVIEW_ONLY', 'units': units, 'obligation_ids': sorted(obligations),
                'approval_created': False, 'semantic_completeness': 'NOT_VERIFIED'}
    review = json.loads(path_in(project.root, project.config['source_review'], exists=True).read_text())
    require(review.get('schema') == 'ads-source-alignment-review/v1', '未知来源决策投影')
    decisions = review.get('decisions')
    require(isinstance(decisions, list), '缺少来源审查决定')
    reviewed = {d['unit_id']: d for d in decisions}
    require(len(reviewed) == len(decisions), '重复来源决定')
    missing, extra = sorted(set(by_id)-set(reviewed)), sorted(set(reviewed)-set(by_id))
    if missing or extra:
        return {'status': 'BLOCKED', 'missing_units': missing, 'phantom_units': extra,
                'reason': 'SOURCE_REVIEW_INCOMPLETE'}
    covered, unresolved = set(), []
    for ident, unit in by_id.items():
        decision = reviewed[ident]
        require(decision.get('text_sha256') == unit['text_sha256'], '来源片段内容已变化')
        require(bool(decision.get('reviewer')) and bool(decision.get('decision_ref')), '缺少既有语义决定引用')
        state = decision.get('disposition')
        require(state in ('REQUIRED', 'CONTEXT', 'EXCLUDED', 'UNRESOLVED'), '未知来源处置')
        links = decision.get('obligations', [])
        require(isinstance(links, list) and all(isinstance(x, str) for x in links)
                and set(links) <= obligations, '来源指向未知交付义务')
        if state == 'REQUIRED':
            require(bool(links), '必需来源未映射到交付义务')
            covered.update(links)
        elif state == 'UNRESOLVED':
            unresolved.append(ident)
        else:
            require(not links and bool(decision.get('reason')), '上下文/排除必须有理由且不能伪装已覆盖')
    unexplained = sorted(obligations-covered)
    return {'schema': 'ads-source-alignment/v1',
            'status': 'SCOPED_RECONCILED_LOCAL' if not unresolved and not unexplained else 'BLOCKED',
            'unresolved_units': unresolved, 'unexplained_obligations': unexplained,
            'reviewed_units': len(reviewed), 'covered_obligations': len(covered),
            'semantic_completeness': 'NOT_ABSOLUTELY_PROVABLE', 'independent_reviewer_identity': 'NOT_VERIFIED'}
