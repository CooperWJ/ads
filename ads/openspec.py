"""从既有 OpenSpec 基线与批准的测试映射生成只读义务视图；不创建规格权威。"""
import json
from pathlib import Path
import re

from .project import require, path_in, digest, canonical, write_json


def inventory(project):
    root = path_in(project.root, project.config['spec_root'], exists=True)
    files = sorted(root.rglob('spec.md'))
    require(bool(files), 'OpenSpec 已确认基线为空')
    require(not any(p.is_symlink() for p in files), '规格不得为符号链接')
    return {str(p.relative_to(project.root)): digest(p.read_bytes()) for p in files}


def _semantic_lines(text):
    # 只忽略围栏外空白行和行尾空白；不归一化词语、代码缩进或业务值。
    lines, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
        if line.strip() or fenced:
            lines.append(line.rstrip())
    return "\n".join(lines)


def scenarios(project):
    found = []
    for name, sha in inventory(project).items():
        text = path_in(project.root, name, exists=True).read_text()
        requirement, current = None, None
        statements, counts = [], {}
        fenced = False
        for number, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(('```', '~~~')):
                fenced = not fenced
                if current is not None:
                    current['oracle_quote'].append(line)
                elif requirement:
                    statements.append(line)
                continue
            req = None if fenced else re.match(r'^###\s+(?:Requirement|需求)\s*[:：]\s*(.+?)\s*$', line)
            case = None if fenced else re.match(r'^####\s+(?:Scenario|场景)\s*[:：]\s*(.+?)\s*$', line)
            if req:
                requirement = req.group(1)
                require(requirement not in counts, '同一规格文件的需求名称重复')
                counts[requirement] = 0
                current, statements = None, []
            elif case:
                require(bool(requirement), '场景缺少所属需求')
                counts[requirement] += 1
                title = case.group(1)
                identity = digest(canonical([name, requirement, title]))[:24]
                current = {'id': identity, 'requirement': requirement, 'scenario': title,
                           'description': requirement + ' / ' + title,
                           'sources': [{'path': name, 'sha256': sha, 'locator': f'L{number}'}],
                           'requirement_quote': "\n".join(statements).strip(), 'oracle_quote': []}
                found.append(current)
            elif current is not None:
                current['oracle_quote'].append(line)
            elif requirement:
                statements.append(line)
        require(not fenced and bool(counts) and all(counts.values()), '规格围栏未闭合或存在没有场景的需求')
    require(bool(found) and len({x['id'] for x in found}) == len(found), '规格场景为空或存在重复身份')
    for case in found:
        case['oracle_quote'] = "\n".join(case['oracle_quote']).strip()
        require(bool(case['oracle_quote']), '场景缺少可核对的行为原文')
        case['semantic_sha256'] = digest(canonical({key: _semantic_lines(case[key])
            for key in ('requirement', 'scenario', 'requirement_quote', 'oracle_quote')}))
    return found


def compile_contract(project):
    current = inventory(project)
    observed = scenarios(project)
    mapping_path = path_in(project.root, project.config['verification_map'], exists=True)
    mapping = json.loads(mapping_path.read_text())
    require(mapping.get('schema') == 'ads-openspec-verification-map/v1', '未知测试映射格式')
    semantics = {x['id']: x['semantic_sha256'] for x in observed}
    if mapping.get('spec_inventory') != current:
        require(mapping.get('scenario_semantics') == semantics, '规格行为变化或证据不足；需要既有流程复审，不能自动重绑定')
    authority = mapping.get('authority', {})
    require(bool(authority.get('reviewer')) and bool(authority.get('decision_ref')), '缺少既有测试设计批准引用')
    bindings = mapping.get('bindings')
    require(isinstance(bindings, list), '缺少测试映射')
    key = lambda x: (x['source'], x['requirement'], x['scenario'])
    by_key = {key(row): row for row in bindings}
    require(len(by_key) == len(bindings), '重复场景映射')
    expected = {(x['sources'][0]['path'], x['requirement'], x['scenario']) for x in observed}
    require(set(by_key) <= expected, '测试映射含不存在的规格场景')
    obligations, missing = [], []
    for case in observed:
        row = by_key.get((case['sources'][0]['path'], case['requirement'], case['scenario']), {})
        tests = row.get('tests')
        if not isinstance(tests, list) or not tests:
            missing.append({'source': case['sources'][0]['path'], 'requirement': case['requirement'], 'scenario': case['scenario']})
        else:
            obligations.append({**case, 'tests': tests})
    if missing:
        return {'status': 'BLOCKED', 'reason': 'SPEC_SCENARIO_VERIFICATION_GAP', 'missing': missing,
                'contract_written': False}
    target = path_in(project.root, project.config['contract'])
    require(target.is_relative_to(project.state), '派生契约只能写入 .ads，不维护第二份人工规格')
    contract = {'schema': 'ads-contract/v1', 'authority': authority, 'obligations': obligations,
                'derived_from': 'OpenSpec baseline + externally reviewed verification mapping',
                'spec_inventory': current, 'scenario_semantics': semantics,
                'mapping_source': str(mapping_path.relative_to(project.root)),
                'mapping_sha256': digest(mapping_path.read_bytes())}
    write_json(target, contract)
    target.chmod(0o444)
    return {'status': 'COMPILED_DERIVED', 'obligations': len(obligations),
            'contract': str(target.relative_to(project.root)), 'approval_created': False,
            'semantic_completeness': 'NOT_VERIFIED'}
