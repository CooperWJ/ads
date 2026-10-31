"""Case calibration: reference must PASS, empty and meaningful mutations must FAIL."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
# UI-crash is browser-only: do not claim it has been calibrated without a real browser.
BACKEND_CASES=['reference','empty','equivalent','missing_ui_field','placeholder_api','bad_export','no_persistence','auth_bypass']

def run_case(name,profile='backend',qa='pass',evidence='current'):
    output=ROOT/'artifacts'/'calibration'/f'{name}-{profile}-{qa}-{evidence}'
    call=[sys.executable,str(ROOT/'evaluator/grade.py'),'--candidate',name,'--profile',profile,
          '--qa-case',qa,'--evidence-case',evidence,'--out',str(output)]
    p=subprocess.run(call,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
    try:
        report=json.loads(p.stdout)
        status=report['status']
    except Exception:
        status='INFRA_ERROR';report={'error':p.stderr[-800:] or p.stdout[-800:]}
    return {'candidate':name,'profile':profile,'qa':qa,'evidence':evidence,'status':status,'exit_code':p.returncode,'report':str(output/'grade.json') if status!='INFRA_ERROR' else None}

def browser_calibration_ok(executions):
    by_name={(x['candidate'],x['profile']):x['status'] for x in executions}
    return by_name.get(('reference','full')) == 'PASS' and by_name.get(('ui_crash','full')) == 'FAIL'


def main():
    parser=argparse.ArgumentParser(description='Calibrate both backend and browser-visible M0 criteria')
    parser.add_argument('--require-browser', action='store_true',
                        help='fail unless reference/full PASS and injected UI crash/full FAIL')
    args=parser.parse_args()
    results=[]
    for name in BACKEND_CASES:
        results.append(run_case(name))
    results.append(run_case('reference',qa='pending'))
    results.append(run_case('reference',evidence='stale'))
    # Limited JS integration is independent from Playwright and cannot replace full profile.
    for name in ('reference','equivalent','ui_crash','empty'):
        results.append(run_case(name,profile='integration'))
    results.append(run_case('reference',profile='full'))
    results.append(run_case('ui_crash',profile='full'))
    expected={'reference':'PASS','empty':'FAIL','equivalent':'PASS',
              'missing_ui_field':'FAIL','placeholder_api':'FAIL',
              'bad_export':'FAIL','no_persistence':'FAIL','auth_bypass':'FAIL'}
    assertions=[]
    for result in results:
        key=result['candidate']
        if result['profile']=='backend' and result['qa']=='pass' and result['evidence']=='current':
            assertions.append({'case':key,'expected':expected[key],'actual':result['status'],'match':result['status']==expected[key]})
        if result['profile']=='integration' and result['qa']=='pass' and result['evidence']=='current':
            want = 'PASS' if key in ('reference','equivalent') else 'FAIL'
            assertions.append({'case':'node-integration-'+key,'expected':want,'actual':result['status'],
                               'match':result['status']==want})
        if result['qa']=='pending':
            assertions.append({'case':'qa-pending','expected':'FAIL','actual':result['status'],'match':result['status']=='FAIL'})
        if result['evidence']=='stale':
            assertions.append({'case':'stale-evidence','expected':'FAIL','actual':result['status'],'match':result['status']=='FAIL'})
    browser_reference=next(x for x in results if x['candidate']=='reference' and x['profile']=='full')
    browser_fault=next(x for x in results if x['candidate']=='ui_crash' and x['profile']=='full')
    browser_ok=browser_calibration_ok(results)
    browser_report={'required':args.require_browser,'reference_status':browser_reference['status'],
                    'ui_crash_status':browser_fault['status'], 'calibrated':browser_ok,
                    'status':'PASS' if browser_ok else 'NOT_VERIFIED'}
    verified=all(row['match'] for row in assertions) and (browser_ok or not args.require_browser)
    result={'status':'PASS' if verified else 'FAIL','calibrated_profile':'backend + limited Node JS real HTTP (not browser)','calibrated':len(assertions),
            'checks':assertions,'executions':results,'browser_calibration':browser_report,
            'trusted_ci_status':'NOT_IMPLEMENTED: local filesystem isolation is not security isolation'}
    path=ROOT/'artifacts'/'calibration-summary.json'
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    sys.exit(0 if result['status']=='PASS' else 1)

if __name__=='__main__':main()
