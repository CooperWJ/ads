"""消费外部评测结果做三轴配对比较；不新增评测调度器。"""
import math
from .project import require


def wilson(successes, count):
    if not count:
        return [0, 1]
    z = 1.96
    center = (successes/count + z*z/(2*count))/(1+z*z/count)
    delta = z*math.sqrt(successes/count*(1-successes/count)/count + z*z/(4*count*count))/(1+z*z/count)
    return [max(0, center-delta), min(1, center+delta)]


def compare(base, candidate):
    require(base.get('schema') == candidate.get('schema') == 'ads-benchmark-observations/v1', '未知对照输入')
    require(base.get('model') == candidate.get('model') and base.get('budget') == candidate.get('budget')
            and bool(base.get('model')) and bool(base.get('budget')), '模型/预算不一致，不能归因于框架')
    require(isinstance(base['budget'], dict) and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in base['budget'].values()), '预算必须有明确正值')
    left, right = base['runs'], candidate['runs']
    key = lambda row: (row['case_id'], row['seed'], row['split'])
    lmap, rmap = {key(r): r for r in left}, {key(r): r for r in right}
    require(len(lmap) == len(left) and len(rmap) == len(right) and set(lmap) == set(rmap) and bool(left), '案例、种子、拆分遗漏或重复')
    for row in left + right:
        require(row.get('split') in ('development', 'holdout', 'fresh'), '未声明样本拆分')
        require(isinstance(row.get('evidence_ref'), str) and row['evidence_ref'], '测量必须引用原始证据')
        require(type(row.get('cost')) in (int, float) and math.isfinite(row['cost']) and row['cost'] >= 0, '缺少成本，不得剔除失败样本')
        require(type(row.get('duration_seconds')) in (int, float) and math.isfinite(row['duration_seconds']) and row['duration_seconds'] >= 0, '缺少执行时延')
        for axis in ('requirements', 'engineering', 'delivery'):
            require(row.get(axis) in ('PASS', 'FAIL', 'UNKNOWN'), '三轴必须分别报告，未知不得删除')
    axes = {}
    for axis in ('requirements', 'engineering', 'delivery'):
        axes[axis] = {}
        for name, runs in (('base', left), ('candidate', right)):
            passed = sum(row[axis] == 'PASS' for row in runs)
            axes[axis][name] = {'pass': passed, 'total': len(runs),
                                 'unknown': sum(row[axis] == 'UNKNOWN' for row in runs),
                                 'rate': passed/len(runs), 'wilson95': wilson(passed, len(runs))}
    return {'schema': 'ads-benchmark-comparison/v1', 'axes': axes,
            'cost': {'base': sum(r['cost'] for r in left), 'candidate': sum(r['cost'] for r in right)},
            'duration_seconds': {'base': sum(r['duration_seconds'] for r in left),
                                 'candidate': sum(r['duration_seconds'] for r in right)},
            'splits': sorted({r['split'] for r in left}), 'paired_runs': len(left),
            'conclusion': 'EXPLORATORY_ONLY', 'adoption': 'NOT_AUTOMATIC',
            'note': '保留失败/未知与成本；输入证据真实性、独立性和因果效果需另行审查'}
