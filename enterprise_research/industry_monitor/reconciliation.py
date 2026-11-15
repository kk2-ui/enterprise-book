"""Locate source rows for review; a numeric coincidence is never adoption.

The proposal records the exact page, line and currency context. Accepted manifests
are explicit research inputs. Historical facts are then read from that original,
not assigned a date to the provider's mutable history.
"""
import json
import re
from pathlib import Path

from .ingestion import subject_id
from .disclosures import available_close_day

LABELS={
 'revenue':r'收入|收益|營業額|Revenue',
 'parent_profit':r'擁有人|權益持有人|股東|母公司|Owners|owners|equity holders',
 'parent_equity':r'擁有人|權益持有人|股東|母公司|Owners|owners|equity holders|權益總額',
 'total_assets':r'資產總|總資產|Total assets',
 'total_liabilities':r'負債總|總負債|Total liabilities',
 'cash':r'現金及|Cash and|cash and',
 'trade_receivables':r'應收|receivables|Receivables',
 'other_receivables':r'應收|receivables|Receivables|預付款',
 'goodwill':r'商譽|Goodwill|goodwill',
 'intangibles':r'無形|Intangible|intangible',
 'minority_equity':r'非控股|少數|Non-controlling|non-controlling',
 'operating_cash_flow':r'經營|營運|operating',
 'fixed_capex':r'購買|購置|購建|添置|Purchase|purchase|payment|Payments',
 'intangible_capex':r'無形|intangible',
 'lease_payments':r'租賃|lease',
 'dividends_paid':r'股息|dividend',
 'interest_income':r'利息|interest',
 'minority_profit':r'非控股|少數|non-controlling',
}
NUMBER=re.compile(r'(?<![\w,.])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![\w,.])')


def amount(raw):
    return float(raw.replace(',','').replace('(','-').replace(')',''))


def report_period(record):
    title=record['title'].translate(str.maketrans('〇零一二三四五六七八九','00123456789'))
    years=re.findall(r'20\d{2}',title)
    if len(set(years))!=1:
        # Some issuer titles contain a literal typo (e.g. 二年二四年年報).
        # Recover only a unique year printed on the actual report cover.
        path=record.get('text_path')
        if not path or not Path(path).exists():return None
        cover=Path(path).read_text().split('\f',1)[0].translate(str.maketrans('〇零一二三四五六七八九','00123456789'))
        if not re.search(r'年報|中期報告|ANNUAL REPORT|INTERIM REPORT',cover,re.I):return None
        years=re.findall(r'20\d{2}',cover)
        if len(set(years))!=1:return None
    return years[0]+('-06-30' if record['kind']=='interim_report' else '-12-31')


def proposals(repo, record):
    end=report_period(record)
    if not end:return []
    pages=Path(record['text_path']).read_text().split('\f')
    facts=[f for f in repo.facts(subject_id(record['code']))
           if f['period_end']==end and f['metric'] in LABELS and f['source_key'].startswith('eastmoney:')]
    found=[]
    for f in facts:
        hits=[]
        for pn,page in enumerate(pages,1):
            lines=page.splitlines()
            for ln,line in enumerate(lines,1):
                context='\n'.join(lines[max(0,ln-3):min(len(lines),ln+1)])
                if not re.search(LABELS[f['metric']],context,re.I):continue
                for scale in (1000,1000000,1):
                    expected=f['value']/scale
                    if abs(expected)<1:continue
                    tokens=[t for t in NUMBER.finditer(line) if abs(amount(t.group())-expected)<.00001]
                    if not tokens:continue
                    if scale==1000 and not re.search(r'千元|千港元|千人民幣|[’\x27]000|thousand',page,re.I):continue
                    if scale==1000000 and not re.search(r'百萬|million',page,re.I):continue
                    if scale==1 and '千元' in page:continue
                    hits.append(dict(page=pn,line=ln,excerpt=line,context=context,scale=scale,token=tokens[0].group(),
                                     currency_context=' | '.join(x.strip() for x in lines if re.search(r'千元|HK\$|RMB|人民幣|港元',x))[:700]))
        if hits:found.append(dict(code=record['code'],document_id='hkex-'+record['id'],document_path=record['text_path'],
                                pdf_path=record['pdf_path'],source_url=record['url'],available_on=record['published_on'],
                                period_end=end,metric=f['metric'],provider_fact_id=f['id'],currency=f['currency'],
                                value=f['value'],scope=f['scope'],period_start=f['period_start'],candidates=hits,
                                status='requires_row_and_currency_review'))
    return found


def adopt_manifest(repo, manifest, document):
    """Only an explicitly reviewed row can enter strict point-in-time arithmetic."""
    if manifest.get('status')!='reviewed':raise ValueError('原件行清单尚未核对')
    pages=Path(manifest['text_path']).read_text().split('\f')
    result=[]
    for row in manifest['rows']:
        excerpt=pages[row['page']-1].splitlines()[row['line']-1]
        if excerpt!=row['excerpt']:raise ValueError('原件定位已变化，请回读')
        tokens=list(NUMBER.finditer(excerpt));value=amount(tokens[row['column']].group())*row['scale']
        if abs(value-row['value'])>max(.01,abs(value)*1e-12):raise ValueError('原件数字与采用值不符')
        result.append(repo.add_fact(dict(subject_id=subject_id(manifest['code']),metric=row['metric'],
           period_start=row.get('period_start',''),period_end=row['period_end'],scope=row['scope'],
           currency=row['currency'],unit='currency',value=value,available_on=available_close_day(manifest),
           vintage='dated_restatement' if row.get('comparative') else 'original',priority=100,
           comparative_restated=bool(re.search(r'重列|重述|重新表述|restated','\n'.join(pages[row['page']-1].splitlines()[:30]),re.I)),
           source_key=f'{document["id"]}:{row["page"]}:{row["line"]}:{row["column"]}:{row["metric"]}',
           source=dict(document_id=document['id'],document_revision=document['revision'],
                       source_id=document['representations']['original'],pdf_page=row['page'],line=row['line'],
                       excerpt=excerpt,formula=f'原件第{row["column"]+1}个数 × {row["scale"]}'),
           verification=manifest['review_basis'])))
    return result
