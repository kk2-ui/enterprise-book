"""Read original statement tables; preserve publication dates and comparisons.

Only explicitly denominated consolidated statements are accepted; current and prior columns are kept.
Notes, management summaries and numeric matches to a vendor are not inputs.
Unrecognised layouts remain acquisition failures, rather than estimated facts.
"""
import re
from pathlib import Path
from .ingestion import subject_id
from .reconciliation import report_period
from .disclosures import available_close_day

CELL=r'(?:\(?-?\d[\d,]*(?:\.\d+)?\)?|[–—−-])'
PAIR=re.compile(r'(?<!\S)('+CELL+r')\s+('+CELL+r')\s*$')
TAIL=re.compile(r'(?<!\S)'+CELL+r'(?:\s+'+CELL+r')+\s*$')
HEAD=re.compile(r'^(?:未經審核|未經審計)?(?:(?:中期|簡明|簡要|合併|綜合|綜合中期|簡明綜合|簡要綜合)\s*)+(損益.*表|(?:全面)?(?:收益|收入)報?表|財務狀況報?表|資產負債表|現金流量表)(?:[（(]續[）)])?$')


def pair(line):
    m=PAIR.search(line)
    if not m:return None
    return [0.0 if s in ('–','—','−','-') else float(s.replace(',','').replace('(','-').replace(')','')) for s in m.groups()]


def denomination(page):
    # Use the statement's own table header, never listing geography.
    head=''.join(page.splitlines()[:25]).replace(' ','')
    hits=[]
    for pattern,currency in [(r'人民幣千元|RMB[’\x27]?000','CNY'),(r'港(?:幣|元)千元|千港元|HK\$[’\x27]?000','HKD'),(r'美元千元|US\$[’\x27]?000','USD')]:
        if re.search(pattern,head,re.I):hits.append(currency)
    return (hits[0],1000) if len(hits)==1 else (None,None)


def statement_pages(text):
    result=[]
    for pn,page in enumerate(text.split('\f'),1):
        lines=page.splitlines();headers=[re.sub(r'^\d+|\d+$','',re.sub(r'\s+','',s)).replace('况','況') for s in lines[:16] if s.strip()]
        headers += [a+b for a,b in zip(headers,headers[1:]) if re.fullmatch(r'(?:中期|簡明|簡要|合併|綜合)+(?:損益及)?',a)]
        matches=[HEAD.match(s) for s in headers if '附註' not in s and '概要' not in s]
        match=next((m for m in matches if m),None)
        currency,scale=denomination(page)
        if not currency:continue
        if match:
            title=match.group(1)
            kind='balance' if '狀況' in title or '負債' in title else 'cashflow' if '現金' in title else 'income'
        elif (result and result[-1]['page']==pn-1 and result[-1]['kind']=='balance'
              and not any(re.search(r'(?:財務報表|財務資料)附註',h) for h in headers[:6])
              and re.search(r'總權益|權益總額|total equity',page,re.I)
              and re.search(r'非流動負債|non-current liabilities',page,re.I)):
            kind='balance'  # immediately continued bilingual main balance sheet
        elif (result and result[-1]['page']==pn-1 and result[-1]['kind']=='cashflow'
              and not any(re.search(r'財務.*附註|權益變動',h) for h in headers[:6])
              and re.search(r'經營.*現金|已付所得稅',page)
              and re.search(r'投資活動|INVESTING',page,re.I)):
            kind='cashflow'  # cash-flow continuation without a repeated title
        else:continue
        columns=max((len(re.findall(r'人民幣千元|千港元|港幣千元|RMB[’\x27]?000|HK\$[’\x27]?000',s,re.I)) for s in [re.sub(r'\s+','',v) for v in lines[:30]]),default=0)
        if columns==1:
            # Some original tables stagger the two denomination cells onto
            # separate lines (e.g. C&D). Count each language independently.
            head=''.join(lines[:25]).replace(' ','')
            columns=max(len(re.findall(p,head,re.I)) for p in (r'人民幣千元|千港元|港幣千元',r'RMB[’\x27]?000|HK\$[’\x27]?000'))
        if columns not in (2,3):continue
        result.append(dict(page=pn,lines=lines,currency=currency,scale=scale,kind=kind,columns=columns))
    main=[]
    for block in result:
        if main and block['page']-main[-1]['page']>8:break
        main.append(block)
    return main


BALANCE={
 'total_assets':r'^(?:總資產|資產總(?:額|值|計))$',
 'total_liabilities':r'^(?:總負債|負債總(?:額|計))$',
 'parent_equity':r'^(?:本公司(?:擁有人|所有者|股東|權益持有人)|母公司(?:擁有人|股東))(?:應佔)?(?:權益|資本及儲備)(?:總額)?$',
 'total_equity':r'^(?:總權益|權益總額|權益合計|資產淨值|權益權益虧絀總額|權益虧絀總額權益總額)$',
 'minority_equity':r'^(?:非控(?:制性|股)|少數股東)權益$',
 'cash':r'^現金及現金等價物$',
 'cash_and_bank':r'^現金及銀行(?:結餘|存款)$',
 'restricted_cash':r'^受(?:限|限制)(?:銀行)?(?:存款|現金|結餘)$',
 'goodwill':r'^商譽$',
 'intangibles':r'^無形資產$',
 'trade_receivables':r'^(?:貿易|交易)應收(?:款項|款|賬款)(?:及應收票據)?$',
 'ppe':r'^(?:物業[、，,]?廠房及設備|物業及設備)$',
}


def extract(record):
    end=report_period(record)
    if not end:return dict(facts=[],issues=['公告标题未能唯一识别财报期间'])
    text=Path(record['text_path']).read_text();pages=statement_pages(text);facts=[];issues=[];operating_closed=False;investing_closed=False
    parent_section=False
    for block in pages:
        kind=block['kind'];lines=block['lines']
        for ln,line in enumerate(lines,1):
            compact=re.sub(r'\s+','',line)
            if kind=='balance' and re.search(r'(?:本公司|母公司)(?:擁有人|股東|權益持有人|權益股東)應佔(?:股本及儲備|資本及儲備|權益)',re.sub(r'[^\u4e00-\u9fff]','',compact)):
                parent_section=True
            if kind=='balance' and re.search(r'非控(?:制性|股)權益|少數股東權益',compact):parent_section=False
            if kind=='cashflow' and re.search(r'投資(?:活動|業務)|investingactivities',re.sub(r'\s+','',line),re.I):operating_closed=True
            if kind=='cashflow' and re.search(r'融資(?:活動|業務)|financingactivities',re.sub(r'\s+','',line),re.I):investing_closed=True
            tail=TAIL.search(line)
            if not tail:continue
            tokens=list(re.finditer(CELL,tail.group()))
            if len(tokens)<block['columns']:continue
            tokens=tokens[-block['columns']:]
            values=[0.0 if t.group() in ('–','—','−','-') else float(t.group().replace(',','').replace('(','-').replace(')','')) for t in tokens[:2]]
            # The columns must be the current/prior financial period. Restatement
            # reconciliation notes have four columns and are not statement pages.
            label=line[:tail.start()+tokens[0].start()].strip()
            raw_label=label
            # Bilingual PDFs put English either before or after Chinese. Keep
            # each alphabet independently; a translated label is not a suffix.
            label=''.join(re.findall(r'[\u4e00-\u9fff]+',raw_label))
            english=re.sub(r'[^a-z]','',raw_label.lower())
            blank_label=not re.search(r'[a-zA-Z\u4e00-\u9fff]',raw_label)
            if label in ('淨額','金淨額','現金淨額','所得現金淨額','流量淨額','現金流量淨額','所得現金流量淨額','的現金淨額','總權益','') or not re.search(r'[\u4e00-\u9fff]',raw_label):
                for previous in reversed(lines[max(0,ln-5):ln-1]):
                    if not previous.strip() or pair(previous):break
                    label=''.join(re.findall(r'[\u4e00-\u9fff]+',previous))+label
                    english=re.sub(r'[^a-z]','',previous.lower())+english
            metric=None;sign=1
            label=re.sub(r'^(?:以下人士應佔|以下各方應佔)','',label)
            english=re.sub(r'^attributableto','',english)
            if kind=='income':
                # The first attribution belongs to profit, subsequent ones can
                # belong to comprehensive income and must not overwrite it.
                if (re.fullmatch(r'(?:本公司|母公司)?(?:擁有人|所有者|股東|股權持有人|權益持有人|權益股東|普通權益持有人|普通股權持有人)(?:應佔)?(?:(?:年內|期內)?(?:溢利|利潤)(?:及全面收益總額)?)?',label) or re.fullmatch(r'(?:owners|equityshareholders|shareholders|equityholders)ofthe(?:company|parent)',english)):metric='parent_profit'
                elif re.fullmatch(r'收入|收益|營業額',label) or english=='revenue':metric='revenue'
            elif kind=='balance':
                metric=next((m for m,p in BALANCE.items() if re.fullmatch(p,label)),None)
                if not metric:
                    metric={'totalequity':'total_equity','noncontrollinginterests':'minority_equity',
                            'cashandcashequivalents':'cash','goodwill':'goodwill',
                            'intangibleassets':'intangibles'}.get(english)
                if parent_section and (blank_label or metric=='total_equity'):
                    metric='parent_equity';parent_section=False
            else:
                if not operating_closed and (re.search(r'經營.*現金.*淨(?:額|流入|流出)|經營.*淨現金',label) or re.search(r'netcash(?:flows)?(?:usedin|generatedfrom|from)operatingactivities',english)):metric='operating_cash_flow'
                elif operating_closed and not investing_closed and re.search(r'物業|廠房|設備|無形資產|使用權資產',label) and re.search(r'購買|購置|購建|添置|付款|預付款',label) and not re.search(r'出售|處置|收購附屬',label):
                    metric=f'capital_cash_payment:{block["page"]}:{ln}';sign=-1
            if not metric:continue
            for column,value in enumerate(values):
                period=end if column==0 else str(int(end[:4])-1)+('-12-31' if kind=='balance' else end[4:])
                existing=[f for f in facts if f['metric']==metric and f['period_end']==period]
                if existing:
                    if metric!='operating_cash_flow':continue
                    # Operating cash before tax may itself be labelled "net".
                    # Adopt the final operating-section subtotal, before investing.
                    for f in existing:facts.remove(f)
                facts.append(dict(subject_id=subject_id(record['code']),metric=metric,
                    period_start='' if kind=='balance' else period[:4]+'-01-01',period_end=period,
                    scope='parent' if metric in ('parent_profit','parent_equity') else 'consolidated',
                    currency=block['currency'],unit='currency',value=value*block['scale']*sign,
                    available_on=available_close_day(record),vintage='original' if column==0 else 'dated_restatement',
                    priority=80,source_key=f'hkex-{record["id"]}:statement:{block["page"]}:{ln}:{column}:{metric}',
                    comparative_restated=bool(re.search(r'重列|重述|重新表述|restated','\n'.join(lines[:30]),re.I)),
                    source=dict(document_id='hkex-'+record['id'],pdf_page=block['page'],line=ln,excerpt=line,
                                column=column+1,scale=block['scale'],url=record['url'],
                                label_context='\n'.join(lines[max(0,ln-2):ln]),
                                original_currency=block['currency']),
                    verification='原件合并主报表、表头币种和两期金额列；比较列只从本公告公开日起可用'))
    # Some issuers print the parent's subtotal without a label. Its rights can
    # be reconstructed from the explicit total and non-controlling interest.
    for period in sorted({f['period_end'] for f in facts if not f['period_start']}):
        lookup={f['metric']:f for f in facts if f['period_end']==period and not f['period_start']}
        if 'parent_equity' in lookup or not {'total_equity','minority_equity'}<=lookup.keys():continue
        total=lookup['total_equity'];minority=lookup['minority_equity']
        if total['currency']!=minority['currency']:continue
        facts.append(dict(total,metric='parent_equity',scope='parent',value=total['value']-minority['value'],
                          source_key=f'hkex-{record["id"]}:derived-parent-equity:{period}',
                          source=dict(document_id='hkex-'+record['id'],url=record['url'],
                                      formula='总权益－非控股权益',components=[total['source'],minority['source']])))
    found={f['metric'] for f in facts if f['period_end']==end}
    for period in (end,str(int(end[:4])-1)+end[4:]):
        components=[f for f in facts if f['metric'].startswith('capital_cash_payment:') and f['period_end']==period]
        if components and investing_closed and len({f['currency'] for f in components})==1:
            base=components[0]
            facts.append(dict(base,metric='capital_expenditure',value=sum(f['value'] for f in components),
                              source_key=f'hkex-{record["id"]}:derived-capex:{period}',
                              source=dict(document_id='hkex-'+record['id'],url=record['url'],formula='投资现金段披露的固定/无形/使用权及投资物业现金支出之和（含已付资本预付款）',
                                          components=[dict(f['source'],value=f['value']) for f in components])))
    for metric in ('parent_profit','parent_equity','operating_cash_flow'):
        if metric not in found:issues.append(metric+'主表行未可靠识别，须补采或核读')
    return dict(facts=facts,issues=issues,period_end=end,statement_pages=[p['page'] for p in pages])
