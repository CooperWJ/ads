"""Evaluator-owned raw-material obligation audit. Do not give this rubric to the coding agent.

SVG label enumeration is exhaustive for this *synthetic fixture*. For other media,
manual review/independent discovery is required; this is NOT general OCR or semantic proof.
"""
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

RUBRIC_SCHEMA='ads-m0-raw-obligations/v1'
VERIFICATION_TYPES={'ui_structure','api_contract','sqlite_persistence_and_auth','real_xlsx_export',
                    'node_js_dom_real_http','real_chromium_user_journey','independent_qa','source_bound_evidence'}

class ObligationError(ValueError):pass

def _ensure(condition, reason):
    if not condition:raise ObligationError(reason)

def audit_inventory(raw_dir, rubric):
    """Check source enumeration and the independently frozen obligation mapping."""
    _ensure(isinstance(rubric,dict) and rubric.get('schema')==RUBRIC_SCHEMA,'invalid obligation schema')
    obligations=rubric.get('obligations')
    _ensure(isinstance(obligations,list) and obligations,'missing protected obligation inventory')
    seen_ids=set();visible=[]
    brief=(Path(raw_dir)/'brief.md').read_text(encoding='utf-8')
    svg=ET.parse(Path(raw_dir)/'wireframe.svg').getroot()
    svg_labels=[(node.text or '').strip() for node in svg.iter() if node.tag.endswith('}text')]
    _ensure(all(svg_labels) and len(svg_labels)==len(set(svg_labels)), 'empty or ambiguous raw SVG text labels')
    for item in obligations:
        _ensure(isinstance(item,dict),'malformed obligation entry')
        id=item.get('id');source=item.get('source');snippet=item.get('source_text');checks=item.get('checks')
        _ensure(isinstance(id,str) and id and id not in seen_ids,'duplicate/missing obligation ID')
        seen_ids.add(id)
        _ensure(isinstance(checks,list) and len(checks)>0 and len(checks)==len(set(checks)) and set(checks)<=VERIFICATION_TYPES, f'{id}: missing/unknown check reference')
        _ensure(type(item.get('browser_required')) is bool,f'{id}: browser requirement must be boolean')
        _ensure(isinstance(snippet,str) and len(snippet)>=3,f'{id}: source anchor missing')
        if source=='raw/wireframe.svg':
            _ensure(snippet in svg_labels,f'{id}: SVG source anchor missing')
            visible.append(snippet)
            _ensure(item['browser_required'],f'{id}: visible UI obligation cannot avoid real browser')
        elif source=='raw/brief.md':
            _ensure(snippet in brief,f'{id}: brief source anchor missing')
        else:raise ObligationError(f'{id}: unapproved or missing source file')
    _ensure(len(visible)==len(set(visible)), 'one raw SVG label mapped more than once')
    missing=sorted(set(svg_labels)-set(visible))
    _ensure(not missing,'unmapped raw SVG labels: '+', '.join(missing))
    # Source-to-requirement completeness for every sentence in the finite synthetic brief.
    # The authored rubric is owned by the evaluator; never infer completed obligations
    # from the candidate program or its own tests.
    paragraphs=brief.split('\n\n')
    _ensure(len(paragraphs)==3, 'synthetic brief format no longer recognizable; review source')
    observed=re.split(r'(?<=[.!?])\s+',paragraphs[1].strip())
    units=rubric.get('brief_sentences')
    _ensure(isinstance(units,list) and len(units)==len(observed),'unmapped brief sentence count')
    ids={item['id'] for item in obligations}
    _ensure([x.get('text') for x in units]==observed, 'raw brief sentence is unmapped, changed, or reordered')
    for index,unit in enumerate(units):
        refs=unit.get('obligations')
        _ensure(isinstance(refs,list) and bool(refs) and len(refs)==len(set(refs)) and set(refs)<=ids,
                f'brief sentence {index+1}: no valid obligation links')
    _ensure(len(visible)==len(set(visible)), 'one raw SVG label mapped more than once')
    return {'status':'PASS','source_svg_labels':len(svg_labels),'mapped_svg_labels':len(visible),'obligations':len(obligations),'brief_sentences':len(observed)}

def adjudicate(rubric, checks):
    """Every obligation needs all linked checks; visible UI also needs real Chromium.

    Not running a required level is NOT_VERIFIED, never PASS. This is independent
    of legacy profile PASS, which only means the selected subset of checks passed.
    """
    lookup={row['check']:row['status'] for row in checks}
    obligations=[]
    for item in rubric['obligations']:
        requirements=list(item['checks'])
        # Independent QA and source binding are mandatory cross-cutting delivery evidence.
        requirements += [k for k in ('independent_qa','source_bound_evidence') if k not in requirements]
        if item['browser_required'] and 'real_chromium_user_journey' not in requirements:
            requirements.append('real_chromium_user_journey')
        states=[lookup.get(k,'NOT_RUN') for k in requirements]
        status='FAIL' if 'FAIL' in states else ('NOT_VERIFIED' if any(v!='PASS' for v in states) else 'PASS')
        obligations.append({'id':item['id'],'status':status,'missing_or_failed_checks':[k for k in requirements if lookup.get(k)!='PASS']})
    statuses={o['status'] for o in obligations}
    return {'status':'FAIL' if 'FAIL' in statuses else ('NOT_VERIFIED' if 'NOT_VERIFIED' in statuses else 'PASS'),
            'total':len(obligations),'passed':sum(o['status']=='PASS' for o in obligations),
            'obligations':obligations}
