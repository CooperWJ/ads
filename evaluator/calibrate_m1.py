"""Independent M1 calibration. Does not replace the frozen M0 calibration.

Reference M1 must pass actual Node+HTTP slice tests, legacy/empty/bad variants
must fail. Optional browser strict mode will fail closed if Chromium unavailable.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
CASES={'reference_m1':'PASS','m1_missing_menu':'FAIL','m1_silent_error':'FAIL','reference':'FAIL','empty':'FAIL'}

def run(name,profile):
    out=ROOT/'artifacts'/'m1-calibration'/f'{name}-{profile}'
    cmd=[sys.executable,str(ROOT/'evaluator/grade.py'),'--candidate',name,
         '--profile',profile,'--acceptance-bundle','m1','--out',str(out)]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=65)
        data=json.loads(p.stdout)
        state=data['status']
        delivery=data.get('delivery_verdict',{}).get('status')
    except Exception as exc:
        state='INFRA_ERROR';delivery=None;p=None;data={'error':str(exc)}
    return {'case':name,'profile':profile,'status':state,'delivery':delivery,
            'exit_code':p.returncode if p else None,'report':str(out/'grade.json') if p else None}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--require-browser',action='store_true')
    args=parser.parse_args()
    rows=[run(name,'integration') for name in CASES]
    comparisons=[{'case':x['case'],'expected':CASES[x['case']],'actual':x['status'],
                  'pass':x['status']==CASES[x['case']]} for x in rows]
    browser=[run(n,'full') for n in ('reference_m1','m1_missing_menu','m1_silent_error')]
    browser_ok=(browser[0]['status']=='PASS' and browser[0]['delivery']=='PASS' and
                all(x['status']=='FAIL' for x in browser[1:]))
    results={'schema':'ads-m1-calibration/v1',
             'integration':{'status':'PASS' if all(x['pass'] for x in comparisons) else 'FAIL',
                            'cases':comparisons},
             'browser':{'status':'PASS' if browser_ok else 'NOT_VERIFIED',
                        'cases':browser},
             'full_m1_calibrated':browser_ok,
             'status':'PASS' if all(x['pass'] for x in comparisons) and (browser_ok or not args.require_browser) else 'FAIL'}
    (ROOT/'artifacts/m1-calibration-summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))
    return 0 if results['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
