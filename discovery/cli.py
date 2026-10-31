"""Read-only CLI for M1 multi-source review and gap report."""
import argparse, json, sys
from pathlib import Path
from .audit import load_and_audit
from .sources import collect, SourceError

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--raw',default='fixtures/project_board/raw')
    parser.add_argument('--review',default='evaluator/source_review.json')
    parser.add_argument('--baseline',default='evaluator/raw_obligations.json')
    parser.add_argument('--inventory-only',action='store_true',help='preview; no approval or completeness claim')
    args=parser.parse_args()
    try:
        if args.inventory_only:
            result=collect(args.raw)
        else:
            b=json.loads(Path(args.baseline).read_text(encoding='utf8'))
            result=load_and_audit(args.raw,args.review,{x['id'] for x in b['obligations']})
    except (SourceError,ValueError,OSError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)},ensure_ascii=False,indent=2));return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.inventory_only or result['status']=='PASS' else 2

if __name__=='__main__':sys.exit(main())
