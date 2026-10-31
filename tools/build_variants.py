"""Reproducibly generate reference and intentionally faulty patches from the frozen seed."""
from pathlib import Path
from difflib import unified_diff
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'fixtures/project_board'
BASE = CASE / 'base'
PATCHES = CASE / 'patches'


def make_patch(changes, dest):
    lines = []
    for rel, new in sorted(changes.items()):
        old = (BASE / rel).read_text()
        if old == new:
            continue
        lines.extend(unified_diff(old.splitlines(True), new.splitlines(True), fromfile=f'a/{rel}', tofile=f'b/{rel}'))
    if not lines:
        raise ValueError(f'empty patch: {dest}')
    (PATCHES / f'{dest}.patch').write_text(''.join(lines))


def substitute(text, orig, updated):
    if text.count(orig) != 1:
        raise ValueError(f'expected exactly one match of {orig!r}, got {text.count(orig)}')
    return text.replace(orig, updated)


def main():
    base = {str(p.relative_to(BASE)):p.read_text() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.sqlite')}
    target = dict(base)
    target['app.py'] = substitute(base['app.py'], 'self.json(200, {"id": data["id"]})  # Deliberately incomplete seed implementation', 'self.json(200, data)')
    make_patch(target, 'reference')
    bads = {}
    bads['missing_ui_field'] = {'web/index.html': substitute(target['web/index.html'], '<dt>Reference code</dt><dd data-field="reference_code"></dd>', '')}
    bads['placeholder_api'] = {'app.py': substitute(target['app.py'], 'self.json(200, data)', 'self.json(200, {"id": data["id"], "title": data["title"]})')}
    bads['bad_export'] = {'app.py': substitute(target['app.py'], 'COLUMN_NAMES = FIELDS + ("notes",)', 'COLUMN_NAMES = FIELDS[:-1] + ("notes",)')}
    bads['no_persistence'] = {'app.py': substitute(target['app.py'], 'db.execute(\'UPDATE projects SET notes=? WHERE id=?\', (notes, int(parts[2])))', 'db.execute(\'SELECT 1\')')}
    bads['auth_bypass'] = {'app.py': substitute(target['app.py'], "if self.headers.get('X-Demo-Role', '') != 'editor':", 'if False:')}
    bads['ui_crash'] = {'web/app.js': "throw new Error('Injected JS failure');\n" + target['web/app.js']}
    for name, changes in bads.items():
        make_patch({**target, **changes}, name)
    # M1 candidates retain the frozen M0 seed and evaluator authority.
    m1 = dict(target)
    m1['app.py'] = substitute(target['app.py'], "if path in ('/', '/app.js'):", "if path in ('/', '/board', '/app.js'):")
    m1['app.py'] = substitute(m1['app.py'], "('index.html' if path == '/' else 'app.js')", "('index.html' if path in ('/','/board') else 'app.js')")
    m1['web/index.html'] = substitute(target['web/index.html'],
        '<body><main><h1>Fictional Project Board</h1>',
        '<body><nav aria-label="Main menu"><a id="menu-project-board" href="/board">Project board</a></nav><main><h1>Fictional Project Board</h1>')
    m1['web/index.html'] = substitute(m1['web/index.html'], '<p id="message" role="status"></p>',
        '<p id="message" role="status"></p><p id="error" role="alert" hidden></p>')
    m1['web/app.js'] = substitute(target['web/app.js'],
        "const message = document.getElementById('message');",
        "const message = document.getElementById('message');\nconst errorPanel = document.getElementById('error');")
    m1['web/app.js'] = substitute(m1['web/app.js'],
        "  message.textContent = '';\n  if (!currentId) return;",
        "  message.textContent = '';\n  errorPanel.textContent = '';\n  errorPanel.hidden = true;\n  if (!currentId) return;")
    m1['web/app.js'] = substitute(m1['web/app.js'],
        "  } catch (error) { message.textContent = `Load failed: ${error.message}`; }",
        "  } catch (error) { errorPanel.hidden = false; errorPanel.textContent = `Load failed: ${error.message}`; message.textContent = `Load failed: ${error.message}`; }")
    make_patch(m1,'reference_m1')
    broken_menu = dict(m1)
    broken_menu['web/index.html'] = substitute(m1['web/index.html'],
        '<a id="menu-project-board" href="/board">Project board</a>', '<span id="menu-project-board">Project board</span>')
    make_patch(broken_menu,'m1_missing_menu')
    broken_error = dict(m1)
    broken_error['web/app.js'] = substitute(m1['web/app.js'],
        'errorPanel.hidden = false; errorPanel.textContent = `Load failed: ${error.message}`;',
        "errorPanel.hidden = true; errorPanel.textContent = '';")
    make_patch(broken_error,'m1_silent_error')
    equivalent = dict(target)
    equivalent['app.py'] = substitute(target['app.py'], 'self.json(200, data)', 'self.json(200, dict(data))')
    equivalent['web/app.js'] = target['web/app.js'].replace('// Intentionally tiny browser integration.', '// Equivalent browser implementation, alternate comment.\n// Intentionally tiny browser integration.')
    make_patch(equivalent, 'equivalent')
    digest = hashlib.sha256()
    for rel in sorted(base):
        digest.update(rel.encode()); digest.update(b'\0');digest.update(base[rel].encode());digest.update(b'\0')
    manifest = {'case_id':'ADS-M0-001', 'base_tree_sha256':digest.hexdigest(), 'raw_material_sha256':hashlib.sha256((CASE/'raw/brief.md').read_bytes()+(CASE/'raw/wireframe.svg').read_bytes()).hexdigest(), 'reference_patch':'reference.patch','empty_expected':'FAIL','reference_expected_backend':'PASS','reference_expected_full':'PASS (only if real browser available)', 'equivalent_expected':'PASS', 'bad_variants':sorted(bads), 'evaluator_version':'ads-m0-grader/v1', 'trust_note':'Local grader path isolation is NOT an OS security boundary; protected CI must run with separate identities.'}
    (CASE / 'case.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'manifest':str(CASE/'case.json'), 'patches':len(list(PATCHES.glob('*.patch')))},ensure_ascii=False))

if __name__ == '__main__':main()
