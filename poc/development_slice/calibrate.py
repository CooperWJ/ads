"""校准外部全旅程测试拓扑；明确不代表真实 OpenCode 开发已发生。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from poc.development_slice.docker_grade import evaluate


def calibrate(image, out):
    rows = []
    for candidate, expected, failed_obligation in (
        ('reference_m1', 'PASS', None),
        ('m1_missing_menu', 'FAIL', 'menu-route-accessible'),
        ('m1_silent_error', 'FAIL', 'page-error-state'),
    ):
        target = out / candidate
        report = evaluate(candidate, image, target)
        browser = next((x for x in report['checks'] if x['check'] == 'real_chromium_user_journey'), {})
        failures = {x['id'] for x in report['delivery_verdict']['obligations'] if x['status'] == 'FAIL'}
        good = (report['status'] == expected and report['delivery_verdict']['status'] == expected
                and browser.get('status') in ('PASS', 'FAIL')
                and (failed_obligation is None or failed_obligation in failures))
        rows.append({'candidate': candidate, 'expected': expected, 'actual': report['status'],
                     'delivery': report['delivery_verdict']['status'], 'browser': browser.get('status'),
                     'status': 'PASS' if good else 'FAIL',
                     'runtime': json.loads((target / 'runtime-isolation.json').read_text())})
    return {'schema': 'ads-container-journey-calibration/v1',
            'status': 'PASS' if all(x['status'] == 'PASS' for x in rows) else 'FAIL',
            'runtime_image': image, 'cases': rows,
            'scope': 'fixture full-journey calibration; QA inputs synthetic',
            'opencode_development': 'NOT_VERIFIED', 'protected_ci': 'NOT_VERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        result = calibrate(args.image, args.out)
    except Exception as exc:
        result = {'status': 'INFRA_ERROR', 'error_type': type(exc).__name__, 'detail': str(exc)[:200],
                  'opencode_development': 'NOT_VERIFIED'}
    (args.out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 2)
