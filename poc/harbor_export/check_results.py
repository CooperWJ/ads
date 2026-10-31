"""消费 Harbor 原生结果，缺失/共享环境/基础设施错误均不算负例成功。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

EXPECTED = {'reference': 1, 'bad-export': 0, 'gate-tamper': 0}


def check(prepared, job):
    manifest = json.loads((prepared / 'manifest.json').read_text())
    if manifest.get('schema') != 'ads-harbor-export/v1' or manifest.get('cases') != EXPECTED:
        raise ValueError('任务身份或固定案例集合不符')
    for name, digest in manifest['files'].items():
        path = prepared / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('任务或评分基线已漂移')
    results = []
    seen = set()
    for path in sorted(job.glob('*/result.json')):
        data = json.loads(path.read_text())
        name = data.get('task_name')
        if name not in EXPECTED or name in seen:
            raise ValueError('未知或重复 trial')
        seen.add(name)
        config = data.get('config', {})
        reward = (data.get('verifier_result') or {}).get('rewards', {}).get('reward')
        boundary = json.loads((path.parent / 'verifier/boundary.json').read_text())
        valid = (data.get('exception_info') is None and bool(data.get('finished_at'))
                 and data.get('verifier_environment_mode') == 'separate'
                 and config.get('environment', {}).get('type') == 'docker'
                 and data.get('agent_info', {}).get('name') == 'oracle'
                 and type(reward) in (int, float) and reward == EXPECTED[name]
                 and boundary.get('run_id') == manifest['run_id']
                 and boundary.get('passed') is bool(EXPECTED[name]))
        results.append({'case': name, 'expected_reward': EXPECTED[name], 'actual_reward': reward,
                        'status': 'PASS' if valid else 'FAIL',
                        'task_checksum': data.get('task_checksum'),
                        'environment_setup': data.get('environment_setup'),
                        'agent_execution': data.get('agent_execution'),
                        'verifier': data.get('verifier')})
    if seen != set(EXPECTED):
        raise ValueError('缺少完整 trial 结果')
    return {'schema': 'ads-harbor-boundary-calibration/v1',
            'status': 'PASS' if all(x['status'] == 'PASS' for x in results) else 'FAIL',
            'harbor_version': manifest['harbor_version'], 'run_id': manifest['run_id'],
            'base_image': manifest['base_image'],
            'scope': manifest['scope'], 'protected_ci': 'NOT_VERIFIED',
            'opencode_development_slice': 'NOT_VERIFIED', 'cases': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('prepared', type=Path)
    parser.add_argument('job', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = check(args.prepared, args.job)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {'status': 'BLOCKED', 'error_type': type(exc).__name__}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 3


if __name__ == '__main__':
    sys.exit(main())
