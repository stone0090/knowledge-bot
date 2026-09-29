"""One-time migration; preserves content, archives navigation, repairs local links.
Usage: python scripts/migrate_collection.py --vault PATH --backup OUTSIDE_VAULT [--apply]
Dry run by default. Run with bot stopped and synchronized clean Git working tree.
"""
from __future__ import annotations
import argparse,hashlib,json,re,shutil,sys
from pathlib import Path
from urllib.parse import unquote,quote,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.vault.frontmatter import split_frontmatter,dump_frontmatter

LINK=re.compile(r'(?P<head>!?\[[^\]\n]*\]\()(?P<url>[^\s)]+)(?P<tail>\))')
WIKI=re.compile(r'(?P<embed>!?)\[\[(?P<target>[^\]\n]+)\]\]')
CODE=re.compile(r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*(?:\n|$)|(`+)[^\n]*?\2')
def outside_code(s,fn):
    parts=[];offset=0
    for m in CODE.finditer(s):parts.extend([fn(s[offset:m.start()]),m.group()]);offset=m.end()
    return ''.join(parts)+fn(s[offset:])

def plan(root):
    mapping={};used=set(p.relative_to(root) for p in root.rglob('*') if p.is_file() and '.git' not in p.parts and '.obsidian' not in p.parts)
    for p in sorted((root/'Wiki').rglob('*.md')):
        old=p.relative_to(root)
        if 'queries' in old.parts:new=Path('_archive/历史问答')/Path(*old.parts[2:])
        elif len(old.parts)>2:new=Path('Wiki')/p.name
        else:continue
        if new in used:
            new=new.with_name(new.stem+'--'+hashlib.sha256(str(old).encode()).hexdigest()[:8]+new.suffix)
        assert new not in used
        used.add(new);mapping[old]=new
    for name in ['index.md','log.md','SCHEMA.md']:
        p=root/name
        if p.exists():
            new=Path('_archive/旧版导航')/name
            assert new not in used
            mapping[Path(name)]=new
    return mapping

def migrate(root,backup,apply=False,mapping=None,normalize_legacy=True):
    root=root.resolve();backup=backup.resolve()
    assert backup!=root and root not in backup.parents
    mapping=plan(root) if mapping is None else mapping
    for old,new in mapping.items():
        assert (root/old).is_file()
        assert root in (root/new).resolve().parents
        assert not (root/new).exists() or old==new
    assert len(set(mapping.values()))==len(mapping)
    notes=[p for p in root.rglob('*.md') if not any(x in ('.git','.obsidian') for x in p.relative_to(root).parts)]
    bystem={}
    for p in notes:bystem.setdefault(p.stem,[]).append(p.relative_to(root))
    generated={};beforehash={};links=0
    for p in notes:
        old=p.relative_to(root);new=mapping.get(old,old);original=p.read_text(encoding='utf-8')
        beforehash[str(old)]=hashlib.sha256(p.read_bytes()).hexdigest()
        meta,body=split_frontmatter(original)
        def resolve(raw,wiki=False):
            u=urlsplit(raw)
            if u.scheme or u.netloc or not u.path:return None
            value=unquote(u.path)
            candidates=[old.parent/value,Path(value.lstrip('/'))]
            if wiki:
                candidates.reverse()
                if not Path(value).suffix:candidates=[x.with_suffix('.md') for x in candidates]+candidates
            for c in candidates:
                absolute=(root/c).resolve()
                if root in absolute.parents and absolute.is_file():return absolute.relative_to(root)
            if wiki:
                matches=bystem.get(Path(value).stem,[])
                if len(matches)==1:return matches[0]
            return None
        def transform(chunk):
            def md(m):
                nonlocal links
                u=urlsplit(m['url']);target=resolve(m['url'])
                if target is None:return m.group()
                dest=mapping.get(target,target)
                import os
                url=quote(os.path.relpath(root/dest,(root/new).parent),safe='/.-_')
                if u.query:url+='?'+u.query
                if u.fragment:url+='#'+u.fragment
                if url!=m['url']:links+=1
                return m['head']+url+m['tail']
            chunk=LINK.sub(md,chunk)
            def wiki(m):
                nonlocal links
                value,sep,label=m['target'].partition('|');target=resolve(value,True)
                if target not in mapping:return m.group()
                dest=str(mapping[target]);frag=value.partition('#')[2]
                if frag:dest+='#'+frag
                links+=1
                return m['embed']+'[['+dest+('|'+label if sep else '')+']]'
            return WIKI.sub(wiki,chunk)
        body=outside_code(body,transform)
        if meta:
            for k in ('sources','contradictions'):
                if isinstance(meta.get(k),list):meta[k]=[str(mapping.get(Path(str(x)),Path(str(x)))) for x in meta[k]]
            if normalize_legacy and new.parts[0]=='Wiki':
                if meta.get('type')!='note':meta['legacy_type']=meta.get('type','')
                meta['type']='note';meta['managed']='false'
            content=dump_frontmatter(meta)+'\n'+body
        else:content=body
        if content!=original or old!=new:generated[old]=(new,content)
    if apply:
        assert not backup.exists()
        shutil.copytree(root,backup,ignore=shutil.ignore_patterns('.obsidian'))
        for p,(dest,content) in generated.items():
            out=root/dest;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(content,encoding='utf-8')
        for old,new in mapping.items():
            if old!=new:(root/old).unlink()
        for p in sorted(root.rglob('*'),key=lambda x:len(x.parts),reverse=True):
            if p.is_dir() and '.git' not in p.parts and '.obsidian' not in p.parts and not any(p.iterdir()):p.rmdir()
        # Ensure every pre-migration note still exists at its mapped destination.
        for p in notes:assert (root/mapping.get(p.relative_to(root),p.relative_to(root))).is_file()
        (backup/'migration-manifest.json').write_text(json.dumps({'mapping':{str(k):str(v) for k,v in mapping.items()},'original_hashes':beforehash,'links_rewritten':links},ensure_ascii=False,indent=2)+'\n')
    return {'moved_files':len(mapping),'changed_notes':len(generated),'links_rewritten':links,'applied':apply}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--vault',type=Path,required=True);a.add_argument('--backup',type=Path,required=True);a.add_argument('--apply',action='store_true');args=a.parse_args()
    print(json.dumps(migrate(args.vault,args.backup,args.apply),ensure_ascii=False))
