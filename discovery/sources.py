"""Deterministic raw-source enumerator for the synthetic ADS M1 benchmark.

Finds traceable fragments, NOT semantic requirements. It never promotes source
content to approved business truth. Unsupported/garbled media fail closed.
This compact adapter is not an OCR, Figma, or general document understanding service.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

SUPPORTED={'.md','.svg','.xlsx'}
LIMIT=2*1024*1024
M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'

class SourceError(ValueError): pass

def require(ok,why):
    if not ok: raise SourceError(why)

def digest(data: bytes): return hashlib.sha256(data).hexdigest()

def item(path,loc,kind,text,**extra):
    require(isinstance(text,str) and bool(text.strip()),f'{path}:{loc}: empty extracted fragment')
    return {'id':digest(f'{path}|{loc}'.encode())[:20],'source':path,'locator':loc,
            'kind':kind,'text':text,'text_sha256':digest(text.encode('utf8')),**extra}

def md_units(name,data):
    text=data.decode('utf-8-sig',errors='strict');units=[]
    for no,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line:continue
        if line.startswith('<!--'):raise SourceError(f'{name}: comment markup unsupported, requires inspection')
        if line.startswith('#'):
            units.append(item(name,f'L{no}','heading',line.lstrip('# ').strip()));continue
        if line.startswith(('- ','* ')):
            units.append(item(name,f'L{no}','bullet',line[2:].strip()));continue
        parts=[x.strip() for x in re.split(r'(?<=[.!?])\s+',line) if x.strip()]
        for idx,part in enumerate(parts,1):
            units.append(item(name,f'L{no}:S{idx}','statement',part))
    require(units,f'{name}: no readable text')
    return units,{'fragments':len(units)}

def svg_units(name,data):
    require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(),f'{name}: DTD forbidden')
    root=ET.fromstring(data);units=[]
    for index,node in enumerate(n for n in root.iter() if n.tag.split('}')[-1]=='text'):
        text=''.join(node.itertext()).strip()
        units.append(item(name,f'text[{index+1}]','visible_text',text))
    require(units,f'{name}: SVG has no visible text nodes')
    return units,{'fragments':len(units)}

def _xlsx_text(cell,strings):
    t=cell.attrib.get('t');formula=cell.find(f'{{{M}}}f')
    if formula is not None:
        return '='+str(formula.text or ''), True
    if t=='inlineStr':
        return ''.join(node.text or '' for node in cell.findall(f'.//{{{M}}}t')),False
    node=cell.find(f'{{{M}}}v')
    if node is None:return '',False
    if t=='s':
        index=int(node.text or '-1');require(0<=index<len(strings),'invalid shared string reference')
        return strings[index],False
    return node.text or '',False

def xlsx_units(name,data):
    from io import BytesIO
    try:
        with ZipFile(BytesIO(data)) as z:
            names=z.namelist()
            require(len(names)<300 and sum(x.file_size for x in z.infolist())<15*1024*1024,'xlsx content too large')
            require('xl/workbook.xml' in names and 'xl/_rels/workbook.xml.rels' in names,'xlsx workbook structure missing')
            require(not any(x.startswith('xl/externalLinks/') or 'vbaProject' in x for x in names), 'xlsx external links/macros forbidden')
            strings=[]
            if 'xl/sharedStrings.xml' in names:
                root=ET.fromstring(z.read('xl/sharedStrings.xml'))
                strings=[''.join(n.text or '' for n in x.findall(f'.//{{{M}}}t')) for x in root.findall(f'{{{M}}}si')]
            rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            targets={x.attrib['Id']:x.attrib['Target'] for x in rel.findall(f'{{{P}}}Relationship')}
            wb=ET.fromstring(z.read('xl/workbook.xml'))
            sheets=wb.findall(f'.//{{{M}}}sheets/{{{M}}}sheet')
            require(sheets,'xlsx no sheets')
            units=[];sums=[];formulas=0
            for sheet in sheets:
                title=sheet.attrib['name'];ident=sheet.attrib[f'{{{R}}}id']
                require(ident in targets, f'xlsx relationship absent: {title}')
                target=targets[ident].lstrip('/')
                if not target.startswith('xl/'):
                    target='xl/'+target
                require('..' not in Path(target).parts and target in names,f'xlsx missing or unsafe worksheet: {title}')
                root=ET.fromstring(z.read(target))
                rows=[]
                for row in root.findall(f'.//{{{M}}}sheetData/{{{M}}}row'):
                    cells=[]
                    for cell in row.findall(f'{{{M}}}c'):
                        coord=cell.attrib.get('r','')
                        require(re.fullmatch('[A-Z]+[0-9]+',coord) is not None, 'invalid cell address')
                        value,formula=_xlsx_text(cell,strings)
                        if value.strip():
                            cells.append((coord,value,formula))
                            formulas+=int(formula)
                    if cells:rows.append((int(row.attrib['r']),cells))
                require(rows,f'xlsx sheet {title} empty; requires explicit assessment')
                firstno,header=rows[0]
                units.append(item(name,f'{title}!R{firstno}','sheet_header',' | '.join(f'{c}={v}' for c,v,_ in header),sheet=title))
                for no,cells in rows[1:]:
                    units.append(item(name,f'{title}!R{no}','sheet_row',' | '.join(f'{c}={v}' for c,v,_ in cells),sheet=title,contains_formula=any(f for _,_,f in cells)))
                sums.append({'sheet':title,'visibility':sheet.attrib.get('state','visible'),'rows':len(rows)-1})
            require(units,f'{name}: no rows')
            return units,{'sheets':sums,'formulas':formulas,'fragments':len(units)}
    except (BadZipFile,KeyError,ET.ParseError) as exc:
        raise SourceError(f'{name}: unreadable XLSX: {exc}') from exc

def collect(root):
    """Exhaust all files under the declared raw-source directory, reject unknown media."""
    root=Path(root)
    require(root.is_dir(),'source directory missing')
    files=sorted(root.rglob('*'))
    require(files,'no source material')
    report=[];units=[]
    for path in files:
        require(not path.is_symlink(),f'source symlink forbidden: {path}')
        if path.is_dir():continue
        rel='raw/'+path.relative_to(root).as_posix()
        require(path.suffix.lower() in SUPPORTED,f'unreadable source type: {rel}')
        data=path.read_bytes();require(0<len(data)<=LIMIT,f'unreadable/oversized source: {rel}')
        decoder={'.md':md_units,'.svg':svg_units,'.xlsx':xlsx_units}[path.suffix.lower()]
        try: extracted,meta=decoder(rel,data)
        except (ValueError,UnicodeError,ET.ParseError) as exc:
            raise SourceError(f'{rel}: extraction failed: {exc}') from exc
        require(extracted,f'{rel}: no extracted source units')
        report.append({'source':rel,'sha256':digest(data),'units':len(extracted),'meta':meta})
        units.extend(extracted)
    require(len({x['id'] for x in units})==len(units),'source unit ID collision')
    return {'schema':'ads-source-discovery/v1','sources':report,'units':units,
            'source_count':len(report),'unit_count':len(units)}
