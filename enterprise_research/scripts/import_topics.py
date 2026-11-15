#!/usr/bin/env python3
"""Import authored topic packs. Resolve existing evidence, skip already imported IDs."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Store
import topics


def import_topics(store, path):
    pack = json.loads(Path(path).read_text())
    cid = pack['company_id']
    company = store.company(cid)
    existing = {t['id'] for t in company['topics']}
    docs = (company.get('dossier') or {}).get('documents', {})
    results = []
    for topic in pack['topics']:
        if topic['id'] in existing:
            results.append({'id': topic['id'], 'status': 'already imported'})
            continue
        data = dict(topic)
        def resolve(match):
            key, page, label = match.groups()
            if key in docs:
                doc = docs[key]
                sid = doc.get('pdf_source_id') or doc.get('text_source_id') or doc.get('url_source_id')
                # Authored references may include a PDF page in the visible label.
                found = re.search(r'(?:第|PDF\s*)(\d+)\s*页', label)
                page = page or (found[1] if found and doc.get('pdf_source_id') else None)
                if not sid:
                    raise ValueError(f'资料未入库：{key}')
            else:
                sid = key
            return f'[[source:{sid}{"@"+page if page else ""}|{label}]]'
        data['body'] = topics.SOURCE_MARKER.sub(resolve, data['body'])
        data['change_note'] = data.get('change_note') or '从已有企业书整理为独立专题；原正文与原预测保留'
        results.append(topics.save(store, cid, data, topic['id']))
        existing.add(topic['id'])
    return results


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-dir', required=True, type=Path)
    p.add_argument('pack', type=Path)
    a = p.parse_args()
    print(json.dumps(import_topics(Store(a.data_dir), a.pack), ensure_ascii=False))
