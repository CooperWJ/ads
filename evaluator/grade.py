"""M0a local trusted evaluator: copies seed, applies patch, grades clean worktree.

Warning: local process separation is not an OS/container security boundary.
The evaluator must run in protected CI separate from agent permissions in production.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parent))  # direct CLI and importlib-loaded unit tests
from requirements import audit_inventory, adjudicate, ObligationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from discovery.audit import load_and_audit

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'fixtures/project_board'
ALLOWED_PATHS = {'app.py', 'web/index.html', 'web/app.js'}
EXPECTED = {'title':'Project Echo','category':'Research','phase':'Planning','owner':'Mira',
            'milestone_start':'2026-01-12','milestone_end':'2026-07-18','reference_code':'DEMO-E01'}
FIELDS = tuple(EXPECTED)


class CheckFailure(AssertionError):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_digest(root):
    h = hashlib.sha256()
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pyc', '.sqlite'):
            continue
        rel = str(path.relative_to(root))
        h.update(rel.encode());h.update(b'\0');h.update(path.read_bytes());h.update(b'\0')
    return h.hexdigest()


def validate_patch(patch):
    """Verify every effective target path, not only the ---/+++ header lines.

    Still not a secure boundary against malicious submitted code. The worker
    running the candidate must be isolated at the OS/CI permissions layer.
    """
    require(Path(patch).is_file(), 'candidate patch missing')
    raw = Path(patch).read_bytes()
    require(len(raw) <= 256 * 1024, 'patch too large for M0 fixture')
    require(b'GIT binary patch' not in raw, 'binary patch forbidden')
    lines = raw.decode('utf-8', errors='strict').splitlines()
    require(not any(line.startswith(('rename from ', 'rename to ', 'copy from ', 'copy to ',
                    'new file mode ', 'deleted file mode ', 'old mode ', 'new mode '))
                    for line in lines), 'rename/copy/file mode changes forbidden')
    import re
    for line in lines:
        if line.startswith('diff --git '):
            match = re.fullmatch(r'diff --git a/(\S+) b/(\S+)', line)
            require(match is not None and match.group(1) == match.group(2)
                    and match.group(1) in ALLOWED_PATHS,
                    f'patch diff header touches forbidden or mismatched path: {line[:160]}')
    headers = [line for line in lines if line.startswith(('--- ', '+++ '))]
    require(bool(headers), 'empty or unrecognized patch')
    for line in headers:
        entry = line[4:].split('\t')[0]
        require(entry.startswith(('a/', 'b/')) and entry[2:] in ALLOWED_PATHS,
                f'patch touches forbidden path: {entry}')
    stat = subprocess.run(['git','apply','--numstat',str(patch)], capture_output=True, text=True)
    require(stat.returncode == 0, 'git could not parse patch: '+stat.stderr[:300])
    paths = set()
    for entry in stat.stdout.splitlines():
        pieces = entry.split('\t', 2)
        require(len(pieces) == 3 and pieces[0].isdigit() and pieces[1].isdigit(),
                'non-text or malformed patch')
        path = pieces[2]
        require(path in ALLOWED_PATHS, f'patch changes forbidden path: {path}')
        paths.add(path)
    require(bool(paths), 'patch has no effective changes')
    return sorted(paths)


def verify_worktree_scope(base, workdir):
    """Ensure git apply did not add, remove, replace or symlink any file."""
    def inventory(root):
        result = {}
        for path in root.rglob('*'):
            require(not path.is_symlink(), 'symlink in candidate worktree forbidden')
            if path.is_file() and not path.name.endswith(('.pyc', '.sqlite')) and '__pycache__' not in path.parts:
                result[path.relative_to(root).as_posix()] = path
        return result
    originals, candidate = inventory(base), inventory(workdir)
    require(set(originals) == set(candidate), 'candidate added/deleted files')
    changed = {name for name in originals if originals[name].read_bytes() != candidate[name].read_bytes()}
    require(changed <= ALLOWED_PATHS, f'candidate changed protected files: {changed - ALLOWED_PATHS}')
    return sorted(changed)


def http(base, route, method='GET', data=None, headers=None):
    payload = None if data is None else json.dumps(data).encode()
    req = Request(base + route, data=payload, method=method, headers=headers or {})
    if payload is not None:
        req.add_header('Content-Type','application/json')
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except HTTPError as err:
        return err.code, err.read(), dict(err.headers)


@contextmanager
def service(workdir, logdir):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logpath = Path(logdir) / 'app.log'
    env = dict(os.environ, ADS_DB_PATH=str(Path(workdir) / 'runtime.sqlite'))
    with logpath.open('wb') as out:
        proc = subprocess.Popen([sys.executable, '-B', 'app.py', '--port', str(port)], cwd=workdir, stdout=out, stderr=subprocess.STDOUT, env=env)
        try:
            for _ in range(120):
                if proc.poll() is not None:
                    raise CheckFailure('application exited: ' + logpath.read_text()[-1200:])
                try:
                    status, body, _ = http(base,'/health')
                    if status == 200 and json.loads(body)['ok']:
                        break
                except Exception:
                    pass
                time.sleep(.05)
            else:
                raise CheckFailure('application failed to start within 6 seconds')
            yield base
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait(timeout=2)


class AttributeParser(HTMLParser):
    def __init__(self):
        super().__init__();self.fields=[];self.ids=[];self.tags={}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-field' in attrs:
            self.fields.append(attrs['data-field']);self.tags[attrs['data-field']]=tag
        if 'id' in attrs: self.ids.append(attrs['id'])


def check_ui_structure(workdir, base):
    status, payload, _ = http(base,'/')
    require(status == 200, 'UI HTTP root is unavailable')
    parser = AttributeParser();parser.feed(payload.decode('utf-8'))
    require(set(FIELDS) == set(parser.fields), f'UI field set mismatch: expected={list(FIELDS)}, actual={parser.fields}')
    require(len(parser.fields) == len(FIELDS), 'duplicate/missing UI fields')
    require(all(parser.tags.get(field)=='dd' for field in FIELDS), 'read-only fields must be noneditable description elements')
    for expected_label in ('Fictional Project Board','Select project','Read-only project details','Editable notes','Save notes','Export XLSX'):
        require(expected_label in payload.decode('utf-8'), 'UI label missing: '+expected_label)
    require({'project-select','notes','save','export'}.issubset(parser.ids), 'UI action missing')
    status, script, _ = http(base,'/app.js')
    require(status == 200 and len(script) > 300, 'UI script missing')
    return 'HTTP-served UI contains the required seven data slots and actions; browser behavior checked separately'


class MenuParser(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('id')=='menu-project-board':self.links.append(attrs.get('href'))


def check_menu_route(base):
    status,home,_=http(base,'/')
    require(status==200,'home not reachable')
    p=MenuParser();p.feed(home.decode())
    require(p.links==['/board'],'navigation menu does not link to /board')
    status,body,_=http(base,'/board')
    require(status==200 and b'id="project-select"' in body and b'/app.js' in body,
            'navigation destination does not load the actual board')
    return 'live HTTP navigation target and menu entry verified'


def check_error_markup(base):
    status,data,_=http(base,'/board')
    require(status==200,'board not reachable for error markup check')
    class AlertParser(HTMLParser):
        def __init__(self):super().__init__();self.elements=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if a.get('id')=='error':self.elements.append((tag,a.get('role'),'hidden' in a))
    p=AlertParser();p.feed(data.decode())
    require(p.elements==[('p','alert',True)], 'explicit accessible initially hidden error alert missing')
    return 'dedicated accessibility error alert has correct markup'


def read_m1_pack(case_id, discovery, original_ids):
    path=ROOT/'evaluator/m1_acceptance.json'
    pack=json.loads(path.read_text())
    require(pack.get('schema')=='ads-m1-acceptance-pack/v1' and pack.get('case_id')==case_id,
            'invalid M1 acceptance version or case ID')
    items=pack.get('obligations')
    require(isinstance(items,list) and len(items)==2, 'both M1 requirements must be present')
    ids={x.get('id') for x in items}
    require(ids==set(discovery['new_unverified_obligations']) and ids.isdisjoint(original_ids),
            'M1 acceptance must exactly match independent source discoveries')
    checks={'menu-route-accessible':('menu_route_accessible','The project board must open from the navigation menu.'),
            'page-error-state':('request_error_state','Show an explicit error state when the project request fails.')}
    for item in items:
        name,text=checks[item['id']]
        require(item.get('checks')==[name] and item.get('browser_required') is True and
                item.get('source')=='raw/prd.md' and item.get('source_text')==text,
                'invalid acceptance source or check mapping: '+item['id'])
    return pack, sha256(path)


def check_api(base):
    status, body, _ = http(base,'/api/projects')
    require(status == 200, 'list API failed')
    rows = json.loads(body)
    require(len(rows) >= 2 and all('id' in row for row in rows), 'list API malformed')
    status, body, _ = http(base,'/api/projects/1')
    require(status == 200, 'detail API failed')
    record = json.loads(body)
    for key,value in EXPECTED.items():
        require(record.get(key) == value, f'API detail not backed by expected record: {key}')
    require('notes' in record, 'API missing editable notes')
    return 'real HTTP list/detail response contains all seven record-backed fields'


def check_persistence(base, workdir):
    status, _, _ = http(base, '/api/projects/1/notes', 'POST', {'notes':'denied'}, {'X-Demo-Role':'viewer'})
    require(status == 403, f'viewer write should be rejected, got {status}')
    status, body, _ = http(base, '/api/projects/1/notes', 'POST', {'notes':'Reviewed in M0'}, {'X-Demo-Role':'editor'})
    require(status == 200 and json.loads(body).get('saved') is True,'editor save failed')
    db = sqlite3.connect(Path(workdir)/'runtime.sqlite')
    try:
        persisted = db.execute('SELECT notes FROM projects WHERE id=1').fetchone()[0]
    finally: db.close()
    require(persisted == 'Reviewed in M0', f'HTTP success without DB commit: {persisted!r}')
    status, body, _ = http(base, '/api/projects/1')
    require(json.loads(body).get('notes') == 'Reviewed in M0', 'read-back not consistent with persisted value')
    return 'viewer rejected; editor save persisted in SQLite and GET read-back reflects value'


def read_xlsx(data):
    with ZipFile(__import__('io').BytesIO(data)) as z:
        require(z.testzip() is None, 'corrupt XLSX ZIP member')
        xml = z.read('xl/worksheets/sheet1.xml')
        require('xl/workbook.xml' in z.namelist(), 'XLSX workbook missing')
    root = ET.fromstring(xml)
    ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rows=[]
    for row in root.findall('.//x:sheetData/x:row',ns):
        values=[]
        for cell in row.findall('x:c',ns):
            t=cell.find('x:is/x:t',ns)
            values.append('' if t is None else (t.text or ''))
        rows.append(values)
    return rows


def check_export(base):
    status, payload, headers = http(base, '/api/projects/1/export')
    require(status == 200, f'XLSX export not available: {status}')
    require('spreadsheetml' in headers.get('Content-Type',''), 'export content-type incorrect')
    rows = read_xlsx(payload)
    expected_columns = list(FIELDS) + ['notes']
    require(len(rows) == 2 and rows[0] == expected_columns, f'export column mismatch: {rows[:1]}')
    for index, key in enumerate(FIELDS):
        require(rows[1][index] == EXPECTED[key], f'export value incorrect: {key}')
    require(rows[1][-1] == 'Reviewed in M0', 'export did not include persisted notes')
    return 'real XLSX downloaded via HTTP, ZIP/XML verified, columns and saved data verified'


def check_js_runtime(workdir, base, check_error=False):
    """Real Node execution of browser JS against real API using a minimal fake DOM.

    Not a browser E2E, not a secure sandbox. Kept as a distinct evidence type.
    """
    node = shutil.which('node')
    if not node:
        return 'BLOCKED', 'Node.js unavailable for limited JS runtime integration check'
    checker = ROOT / 'evaluator' / 'js_runtime_check.cjs'
    command = [node, str(checker), str(Path(workdir)/'web'/'app.js'), base]
    if check_error:command.append('--m1-error')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=12, cwd=workdir)
    except subprocess.TimeoutExpired:
        return 'FAIL', 'JS integration check timeout'
    try:
        detail = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 'FAIL', 'JS integration output invalid: '+(result.stderr or result.stdout)[-300:]
    if result.returncode != 0 or detail.get('status') != 'PASS':
        return 'FAIL', 'JS integration: '+str(detail.get('error', 'unknown failure'))[:400]
    return 'PASS', 'Node fake-DOM executes candidate JS against live HTTP and reload; NOT a browser test'


def check_browser(base, logdir, m1_enabled=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as err:
        return 'BLOCKED', 'Playwright package unavailable: '+str(err)
    try:
        with sync_playwright() as playwright:
            # Default to matching Playwright browser; override only in approved environments.
            chrome = os.environ.get('ADS_CHROMIUM_PATH')
            kwargs={'headless':True,'args':['--no-sandbox']}
            if chrome and Path(chrome).is_file():kwargs['executable_path']=chrome
            browser = playwright.chromium.launch(**kwargs)
            try:
                context=browser.new_context(accept_downloads=True)
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                page=context.new_page()
                page.goto(base+'/', wait_until='domcontentloaded', timeout=10000)
                if m1_enabled:
                    page.locator('#menu-project-board').click()
                    require(page.url.endswith('/board'), 'menu does not navigate to project board')
                page.locator('#project-select').select_option('1')
                page.locator('#project-details').wait_for(state='visible', timeout=10000)
                for key, value in EXPECTED.items():
                    actual=page.locator(f'[data-field="{key}"]').inner_text()
                    require(actual == value, f'browser field {key!r} incorrect: {actual!r}')
                    require(not page.locator(f'[data-field="{key}"]').is_editable(), f'browser field {key!r} must be read-only')
                require(page.locator('#export').is_disabled(), 'export enabled before save')
                page.locator('#notes').fill('Browser verified')
                page.locator('#save').click()
                require(page.locator('#export').is_enabled(), 'export still disabled after successful save')
                with page.expect_download(timeout=10000) as download_info:
                    page.locator('#export').click()
                download=download_info.value
                path=Path(logdir)/'browser-export.xlsx'
                download.save_as(path)
                values=read_xlsx(path.read_bytes())
                require(values[1][-1]=='Browser verified','downloaded XLSX is not based on browser save')
                page.reload()
                page.locator('#project-select').select_option('1')
                page.locator('#project-details').wait_for(state='visible')
                require(page.locator('#notes').input_value()=='Browser verified','reload lost saved notes')
                if m1_enabled:
                    page.locator('#project-select').evaluate("el => { const opt = document.createElement('option'); opt.value='999'; opt.textContent='Missing record'; el.append(opt); }")
                    page.locator('#project-select').select_option('999')
                    alert=page.get_by_role('alert')
                    alert.wait_for(state='visible',timeout=10000)
                    require('HTTP 404' in alert.inner_text(),'browser error reason missing')
                    require(page.locator('#project-details').is_hidden(),'failed request retained stale details')
                context.tracing.stop(path=str(Path(logdir)/'browser-trace.zip'))
                context.close()
                return 'PASS','real Chromium journey: select→7 fields→save→download→reload passed'
            finally:browser.close()
    except Exception as err:
        msg=str(err).split('Call log:')[0].strip()[:500]
        if 'ERR_BLOCKED_BY_ADMINISTRATOR' in msg or 'Executable doesn\'t exist' in msg or 'browserType.launch' in msg and 'failed' in msg:
            return 'BLOCKED',msg
        return 'FAIL',msg


def check_qa(case):
    # This fixture is owned by the evaluator; not copied to the candidate worktree.
    expected=('qa-screen','qa-export')
    statuses={k:'PASSED' for k in expected}
    if case=='pending':statuses['qa-export']='PENDING'
    if case=='failed':statuses['qa-export']='FAILED'
    missing=[k for k in expected if statuses.get(k) != 'PASSED']
    require(not missing, f'QA independent required cases not passed: {[(k,statuses.get(k)) for k in missing]}')
    return 'all independently required QA cases passed; no DEV result substituted'


def check_evidence(case, current_hash):
    actual=current_hash if case=='current' else '0'*64
    require(actual==current_hash, 'execution evidence does not match candidate source SHA')
    return 'evidence source identity matches independently computed candidate digest'


def evaluate(patch, profile, qa_case, evidence_case, outdir, m1_enabled=False):
    base=CASE/'base'
    manifest=json.loads((CASE/'case.json').read_text())
    require(tree_digest(base)==manifest['base_tree_sha256'], 'frozen baseline checksum changed')
    raw_digest=hashlib.sha256((CASE/'raw/brief.md').read_bytes()+(CASE/'raw/wireframe.svg').read_bytes()).hexdigest()
    require(raw_digest==manifest['raw_material_sha256'], 'source material changed since case calibration')
    rubric=json.loads((ROOT/'evaluator/raw_obligations.json').read_text(encoding='utf-8'))
    audit=audit_inventory(CASE/'raw', rubric)
    require(rubric.get('case_id')==manifest['case_id'], 'rubric does not match frozen task identity')
    source_discovery=load_and_audit(CASE/'raw',ROOT/'evaluator/source_review.json',
                                    {entry['id'] for entry in rubric['obligations']})
    pack, pack_sha = read_m1_pack(manifest['case_id'],source_discovery,{x['id'] for x in rubric['obligations']}) if m1_enabled else (None,None)
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ads-m0-clean-') as temp:
        workdir=Path(temp)/'candidate'
        shutil.copytree(base,workdir)
        if patch is not None:
            validate_patch(patch)
            action=subprocess.run(['git','apply','--check',str(patch)],cwd=workdir,capture_output=True,text=True)
            require(action.returncode==0,'candidate patch cannot apply: '+action.stderr[:300])
            applied=subprocess.run(['git','apply',str(patch)],cwd=workdir,capture_output=True,text=True)
            require(applied.returncode==0,'candidate patch failed: '+applied.stderr[:300])
        verify_worktree_scope(base, workdir)
        candidate_hash=tree_digest(workdir)
        results=[]
        def record(name, call):
            try:results.append({'check':name,'status':'PASS','detail':call()})
            except Exception as err:results.append({'check':name,'status':'FAIL','detail':str(err)[:500]})
        with service(workdir,outdir) as baseurl:
            record('ui_structure',lambda: check_ui_structure(workdir,baseurl))
            if m1_enabled:
                record('menu_route_accessible',lambda: check_menu_route(baseurl))
                record('error_accessibility',lambda: check_error_markup(baseurl))
            record('api_contract',lambda: check_api(baseurl))
            record('sqlite_persistence_and_auth',lambda: check_persistence(baseurl,workdir))
            record('real_xlsx_export',lambda: check_export(baseurl))
            if profile in ('integration', 'full'):
                js_status, js_detail = check_js_runtime(workdir, baseurl)
                results.append({'check':'node_js_dom_real_http','status':js_status,'detail':js_detail})
                if m1_enabled:
                    state,detail=check_js_runtime(workdir,baseurl,check_error=True)
                    if any(r['check']=='error_accessibility' and r['status']!='PASS' for r in results):state='FAIL'
                    results.append({'check':'request_error_state','status':state,'detail':detail})
            if profile=='full':
                state, detail=check_browser(baseurl,outdir,m1_enabled=m1_enabled)
                results.append({'check':'real_chromium_user_journey','status':state,'detail':detail})
        record('independent_qa',lambda:check_qa(qa_case))
        record('source_bound_evidence',lambda:check_evidence(evidence_case,candidate_hash))
        delivery=adjudicate({'obligations':rubric['obligations']+(pack['obligations'] if pack else [])},results)
        # A newly discovered obligation has no independently executed acceptance
        # evidence. Never promote the old M0 tests to complete delivery.
        pending=[x['id'] for x in delivery['obligations'] if
                 x['id'] in source_discovery['new_unverified_obligations'] and x['status']!='PASS']
        delivery['m1_unverified_new_obligations']=pending if m1_enabled else source_discovery['new_unverified_obligations']
        source_discovery['acceptance_closure']={
            'mode':'m1' if m1_enabled else 'm0',
            'status':('PASS' if not pending else 'NOT_VERIFIED') if m1_enabled else 'GAP',
            'remaining':delivery['m1_unverified_new_obligations'],
            'required_browser':bool(m1_enabled),
            'acceptance_sha256':pack_sha} 
        if source_discovery['status']=='GAP' and not m1_enabled and delivery['status']=='PASS':
            delivery['status']='NOT_VERIFIED' 
        statuses={row['status'] for row in results}
        overall='FAIL' if 'FAIL' in statuses else ('BLOCKED' if 'BLOCKED' in statuses else 'PASS')
        report={'case_id':manifest['case_id'],'profile':profile,'status':overall,
                'source_material_sha256':manifest['raw_material_sha256'],
                'base_tree_sha256':manifest['base_tree_sha256'],
                'candidate_tree_sha256':candidate_hash,
                'candidate_patch_sha256':sha256(patch) if patch else None,
                'qa_case':qa_case,'evidence_case':evidence_case,'checks':results,
                'raw_source_inventory':audit,'source_discovery':source_discovery,'delivery_verdict':delivery,
                'm1_acceptance_enabled':m1_enabled,'m1_acceptance_sha256':pack_sha,
                'protected_rubric_sha256':sha256(ROOT/'evaluator/raw_obligations.json'),
                'execution_mode':'new ephemeral worktree and fresh SQLite DB; no OS/container isolation',
                'grader_sha256':sha256(__file__),
                'generated_at_utc':datetime.now(timezone.utc).isoformat()}
        (outdir/'grade.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate',default='reference',help='reference | empty | equivalent | bad variant | /path/to/custom.patch')
    parser.add_argument('--profile',choices=('backend','integration','full'),default='backend')
    parser.add_argument('--acceptance-bundle',choices=('m0','m1'),default='m0',help='select separately authored acceptance for discovered M1 requirements')
    parser.add_argument('--qa-case',choices=('pass','pending','failed'),default='pass')
    parser.add_argument('--evidence-case',choices=('current','stale'),default='current')
    parser.add_argument('--out',default=str(ROOT/'artifacts/latest'))
    parser.add_argument('--require-delivery',action='store_true',help='nonzero unless all raw source obligations have independently verified browser-backed results')
    parser.add_argument('--allow-untrusted-local-candidate', action='store_true',
                        help='explicitly accept host-execution risk for a custom patch; use isolated CI instead')
    args=parser.parse_args()
    custom_patch=args.candidate.endswith('.patch')
    patch=None if args.candidate=='empty' else (Path(args.candidate).resolve() if custom_patch else CASE/'patches'/f'{args.candidate}.patch')
    try:
        require(not custom_patch or args.allow_untrusted_local_candidate,
                'custom patch execution needs --allow-untrusted-local-candidate; use an isolated runner')
        require(patch is None or patch.is_file(),f'candidate patch not found: {patch}')
        report=evaluate(patch,args.profile,args.qa_case,args.evidence_case,args.out,m1_enabled=args.acceptance_bundle=='m1')
    except (CheckFailure, ObligationError) as err:
        report={'status':'REJECTED','error':str(err),'candidate':args.candidate}
    except Exception as err:
        report={'status':'INFRA_ERROR','error':str(err),'candidate':args.candidate}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.require_delivery and report.get('status')=='PASS' and report['delivery_verdict']['status']!='PASS':return 2
    if report['status']=='PASS':return 0
    if report['status'] in ('FAIL','REJECTED'):return 1
    return 2

if __name__=='__main__':sys.exit(main())
