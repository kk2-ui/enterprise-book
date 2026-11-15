#!/usr/bin/env python3
"""Export a company book's narrative and source links for reading without the app."""
import argparse, json, os, shutil
from pathlib import Path


def export_book(data, destination):
    destination=Path(destination)
    def figures(section,position):
        result=[]
        for f in section.get('figures',[]):
            if f.get('after_paragraph',len(section.get('paragraphs',[]))-1)!=position:continue
            doc=data['documents'][f['document']]
            original=Path(doc['image'])
            folder=destination.parent/'figures';folder.mkdir(exist_ok=True)
            target=folder/(f['document']+original.suffix)
            if original.resolve()!=target.resolve():shutil.copyfile(original,target)
            result += [f'![{doc["title"]}]({os.path.relpath(target,destination.parent)})','',f.get('caption',''),'']
        return result
    name = data.get('company_name', data['company_id'])
    out = [f'# {name}企业书', '', f'修订日期：{data["as_of"]}', '', data.get('intro',''), '']
    if basis := data.get('research_basis'):
        url=f'http://127.0.0.1:8778/#/company/{data["company_id"]}/research?project={basis["project_id"]}&revision={basis["research_revision"]}'
        out += [f'本版：{data["version"]} · 采用研究r{basis["research_revision"]}', '', f'[完整研究过程]({url})' + (f' · [本版计算]({url}&calculation={basis["calculation_id"]})' if basis.get('calculation_id') else ''), '']
    for i, c in enumerate(data['chapters']):
        out += [f'## 第{i+1}章 {c["title"]}', '', c['subtitle'], '', c['conclusion'], '']
        for s in c['sections']:
            out += ['### '+s['title'], '']
            for position,p in enumerate(s.get('paragraphs', [s.get('body','')])):
                out += [p, '']+figures(s,position)
            if f := s.get('flow'):
                out += ['**'+f['title']+'**', '']
                for lane in f['lanes']:
                    out += [lane['name']+'：'+' → '.join(step['title'] for step in lane['steps']), '']
                    out += [step['title']+'：'+step['body'] for step in lane['steps']]
                    out += ['', lane.get('note',''), '']
                out += [f.get('note',''), '']
            if t := s.get('table'):
                out += ['**'+t['title']+'**', '', '| '+' | '.join(t['columns'])+' |', '| '+' | '.join('---' for _ in t['columns'])+' |']
                out += ['| '+' | '.join(map(str,r))+' |' for r in t['rows']]
                out += ['', t.get('note',''), '']
            if s.get('exhibit') or s.get('chart'):
                out += [f'[查看本节图表和原数](http://127.0.0.1:8778/#/company/{data["company_id"]}/book?chapter={i})', '']
            for r in s.get('refs',[]):
                d = data['documents'][r['document']]; target = d.get('pdf') or d.get('text') or d.get('image') or d['url']
                out += [f'来源：[{d["title"]}]({target})'+(f'，PDF第{r["page"]}页' if r.get('page') else '')+'；'+d['period'], '']
        out += ['### 待观察事项', '', c['counter'], '', '### 尚需了解的情况', '']
        for q in c['questions']: out += [q['ask'], '', '所需资料：'+q['evidence'], '', '影响判断：'+q['impact'], '']
    Path(destination).write_text('\n'.join(out))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('dossier',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    export_book(json.loads(a.dossier.read_text()),a.output)
