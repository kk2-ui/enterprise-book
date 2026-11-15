#!/usr/bin/env python3
"""Export current company factors and topics as a readable Markdown document."""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Store
import topics


def export_topics(store, cid, destination):
    company = store.company(cid)
    sources = {s['id']: s for s in company['sources']}
    frame = company.get('research_framework') or {}
    factors = frame.get('factors', [])
    out = [f'# {company["name"]}专题研究', '',
           f'行业框架：{frame.get("title", "尚未确定")} · 修订 {frame.get("revision", "—")}', '',
           frame.get('rationale', ''), '', frame.get('synthesis', ''), '']
    known = {f['id'] for f in factors}
    groups = factors + [dict(id='', name='跨主线与其他专题')]
    def reference(match):
        sid, page, label = match.groups()
        source = sources[sid]
        target = source.get('path') or source.get('url') or f'http://127.0.0.1:8778/api/sources/{sid}/content'
        return f'[{label}](<{target}>)' + (f'（PDF第{page}页）' if page else '')
    for f in groups:
        selected = [t for t in company['topics'] if
                    ((t.get('factor_ids') or [''])[0] == f['id'] if f['id'] else
                     (t.get('factor_ids') or [''])[0] not in known)]
        if not selected:
            continue
        out += [f'## {f["name"]}', '', f.get('question', ''), '',
                f.get('assessment', ''), '', f.get('watch', ''), '']
        for summary in selected:
            t = topics.read(store, cid, summary['id'])
            body = topics.SOURCE_MARKER.sub(reference, t['body'])
            body = re.sub(r'^(#{1,4}) ', r'##\1 ', body, flags=re.M)
            out += [f'### {t["title"]}', '',
                    f'修订 {t["revision"]} · {t["updated_at"][:10]} · {" / ".join(t.get("factor_labels", []))}', '',
                    t.get('summary', ''), '', body, '']
    Path(destination).write_text('\n'.join(out))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('company')
    p.add_argument('output', type=Path)
    args = p.parse_args()
    export_topics(Store(args.data_dir), args.company, args.output)
