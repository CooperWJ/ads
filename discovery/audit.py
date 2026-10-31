"""Evaluate an independent frozen review against raw source inventory.

A review is authored by the trusted evaluator for this synthetic benchmark.
In real projects AI suggestions may be drafts, not self-approved requirements.
"""
import hashlib
import json
from pathlib import Path
from .sources import collect, SourceError

SCHEMA='ads-independent-source-review/v1'
VALID={'REQUIRED','CONTEXT','EXCLUDED'}

def _check(ok,why):
    if not ok:raise SourceError(why)

def audit(raw_dir, review, baseline_obligation_ids):
    extraction=collect(raw_dir)
    _check(isinstance(review,dict) and review.get('schema')==SCHEMA,'invalid independent review schema')
    by_source={x['source']:x for x in extraction['sources']}
    frozen=review.get('sources')
    _check(isinstance(frozen,list) and {x.get('source') for x in frozen if isinstance(x,dict)}==set(by_source)
           and len(frozen)==len(by_source),'source inventory missing/new source; independent review needed')
    for frozen_item in frozen:
        name=frozen_item['source'];actual=by_source[name]
        _check(frozen_item.get('sha256')==actual['sha256'],f'{name}: source hash drift; review invalid')
        _check(frozen_item.get('units')==actual['units'],f'{name}: source extraction changed; review invalid')
    actual={x['id']:x for x in extraction['units']}
    rows=review.get('decisions')
    _check(isinstance(rows,list),'missing independent review decisions')
    reviewed={}
    for row in rows:
        _check(isinstance(row,dict),'malformed review decision')
        key=row.get('unit_id')
        _check(isinstance(key,str) and key not in reviewed,'duplicate/missing source review decision')
        reviewed[key]=row
    _check(set(actual)==set(reviewed),f'unreviewed or phantom source fragments: missing={sorted(set(actual)-set(reviewed))[:5]}, extra={sorted(set(reviewed)-set(actual))[:5]}')
    discovered=set();stats={k:0 for k in VALID}
    for key,unit in actual.items():
        row=reviewed[key];disposition=row.get('disposition')
        _check(row.get('text_sha256')==unit['text_sha256'],f'{unit["source"]}:{unit["locator"]}: source fragment changed')
        _check(disposition in VALID,f'{unit["locator"]}: unreviewed disposition')
        _check(isinstance(row.get('reviewer'),str) and row['reviewer'].strip() and
               isinstance(row.get('decision_ref'),str) and row['decision_ref'].strip(),
               f'{unit["locator"]}: independent reviewer/decision reference absent')
        links=row.get('obligations',[])
        _check(isinstance(links,list) and len(set(links))==len(links) and all(isinstance(x,str) and x for x in links),
               f'{unit["locator"]}: invalid obligation mapping')
        _check(bool(links)==(disposition=='REQUIRED'),f'{unit["locator"]}: required fragments must map, context/exclusion cannot map')
        # A visible design label and explicit PRD action must never be silently dropped.
        _check(not (unit['kind']=='visible_text' and disposition!='REQUIRED'),f'{unit["locator"]}: SVG visible label must be REQUIRED')
        if disposition!='REQUIRED' and unit['kind'] in ('bullet','statement','sheet_row'):
            _check(isinstance(row.get('reason'),str) and bool(row['reason'].strip()),
                   f'{unit["locator"]}: contextual/excluded requirement-like fragment requires rationale')
        discovered.update(links);stats[disposition]+=1
    baseline=set(baseline_obligation_ids)
    new=sorted(discovered-baseline)
    # Existing missing baseline IDs already have their own M0 source/oracle contract.
    return {'status':'GAP' if new else 'PASS','source_count':extraction['source_count'],
            'unit_count':extraction['unit_count'],'reviewed_units':len(reviewed),
            'dispositions':stats,'new_unverified_obligations':new,
            'needs_acceptance_design':len(new),
            'coverage_dimensions':{'material_inventory':'PASS','source_extraction':'PASS',
                                   'source_decisions':'PASS',
                                   'accepted_obligation_verification':'GAP' if new else 'PASS'},
            'review_sha256':hashlib.sha256(json.dumps(review,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'sources':extraction['sources']}

def load_and_audit(raw_dir,review_file,baseline_obligation_ids):
    review=json.loads(Path(review_file).read_text(encoding='utf-8'))
    return audit(raw_dir,review,baseline_obligation_ids)
