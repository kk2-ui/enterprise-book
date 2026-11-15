"""Original-table rows whose layout or font needs an explicit source review.

This adapter complements the generic parser. It neither assigns publication
dates to vendor history nor treats unchecked OCR output as financial facts.
"""
import json
from pathlib import Path

from .disclosures import available_close_day
from .ingestion import subject_id
from .sources import register_report


def ingest(repo, root):
    path=Path(root)/'reviewed_statements.json'
    if not path.exists():return dict(facts=0,documents=0,pending=[])
    records=json.loads(path.read_text());count=0;documents=0;pending=[]
    for item in records:
        record=item['record']
        if item.get('status')!='reviewed' or not item.get('review_reference'):
            pending.append(record['id']);continue
        doc=register_report(repo.directory,record);documents+=1
        with repo.connect() as conn:
            for row in item['rows']:
                source=dict(document_id=doc['id'],document_revision=doc['revision'],
                            source_id=doc['representations']['original'],url=record['url'],
                            pdf_page=row['pdf_page'],excerpt=row['excerpt'],
                            scope_evidence=row['scope_evidence'],review_reference=item['review_reference'])
                if row.get('support_pages'):source['support_pages']=row['support_pages']
                fact=dict(subject_id=subject_id(record['code']),metric=row['metric'],
                          period_start=row['period_start'],period_end=row['period_end'],
                          scope=row['scope'],currency=row['currency'],unit='currency',value=row['value'],
                          available_on=available_close_day(record),vintage=row['vintage'],priority=90,
                          source_key=f'hkex-{record["id"]}:reviewed:{row["metric"]}:{row["period_end"]}',
                          source=source,verification='原件图表或权益归属经逐项核读；公开日来自该原件')
                repo.add_fact(fact,conn);count+=1
    return dict(facts=count,documents=documents,pending=pending)
