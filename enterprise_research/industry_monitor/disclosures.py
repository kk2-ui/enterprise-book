"""HKEX public announcement discovery with original publication timestamps.

The stock-list `i` is the search identity; `s` is NOT the search identity.
All versions are retained. A later amended report never replaces its original.
"""
import html
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .acquisition import fetch_json
from market_data import write_json

HOST='https://www1.hkexnews.hk'


def available_close_day(record):
    """After-close disclosures cannot enter that day's closing valuation.

    Use 16:00 conservatively around the closing auction. A next-calendar-day
    bound also works over weekends: the next observed trading close is later.
    When time is absent, delay a day instead of guessing intraday availability.
    """
    stamp=record.get('published_at')
    day=datetime.fromisoformat(record['published_on']).date()
    if not stamp or datetime.fromisoformat(stamp).hour>=16:day+=timedelta(days=1)
    return day.isoformat()


def identities():
    rows=[]
    for status in ('active','inactive'):
        url=HOST+'/ncms/script/eds/'+status+'stock_sehk_c.json'
        for row in fetch_json(url):
            rows.append(dict(code=row['c'].zfill(5)+'.HK',stock_id=str(row['i']),name=row['n'],
                             status=status,source_url=url))
    return rows


def announcements(identity, start, end):
    params=dict(sortDir='0',sortByOptions='DateTime',category='0' if identity['status']=='active' else '1',market='SEHK',
                stockId=identity['stock_id'],documentType='-1',fromDate=start.replace('-',''),
                toDate=end.replace('-',''),title='',searchType='1',t1code='-2',
                t2Gcode='-2',t2code='-2',rowRange=1000,lang='zh')
    url=HOST+'/search/titleSearchServlet.do?'+urlencode(params)
    raw=fetch_json(url)
    if raw.get('hasNextRow'):raise ValueError('公告超过1000条，须缩短日期范围')
    rows=[]
    for r in json.loads(raw.get('result','[]')):
        if r.get('FILE_TYPE')!='PDF':continue
        published=datetime.strptime(r['DATE_TIME'],'%d/%m/%Y %H:%M')
        title=html.unescape(r['TITLE']);category=html.unescape(r['LONG_TEXT'])
        kind=classify(category)
        rows.append(dict(id=r['NEWS_ID'],code=identity['code'],title=title,category=category,kind=kind,
                         published_at=published.isoformat()+'+08:00',published_on=published.date().isoformat(),
                         url=HOST+r['FILE_LINK'],source_url=url,
                         amended=any(s in title for s in ('修訂','修正','補充','更正','重列'))))
    return dict(identity=identity,start=start,end=end,retrieved_at=datetime.now(timezone.utc).isoformat(),
                records=rows,total=raw.get('recordCnt'))


def classify(category):
    return ('annual_report' if '年報' in category and '財務報表' in category else
            'interim_report' if '中期/半年度報告' in category else
            'annual_results' if '末期業績' in category else
            'interim_results' if '中期業績' in category else
            'monthly_return' if '月報表' in category else
            'capital_event' if any(s in category for s in ('股息','股份購回','拆細','合併股份','供股','私有化','撤銷上市')) else 'other')


def discover(members, directory, end, progress=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    ids=identities();write_json(directory/'identities.json',ids)
    jobs=[];results=[]
    for m in members:
        path=directory/(m['code']+'.json')
        if path.exists():results.append(dict(code=m['code'],status='cached'));continue
        matches=[r for r in ids if r['code']==m['code']]
        # Multiple securities may reuse a code. Require an issuer name match.
        if len(matches)>1:
            status='inactive' if m['status']=='delisted' else 'active'
            matches=[r for r in matches if r['status']==status]
        if len(matches)>1:
            wanted=m['name'].replace('物业','物業').replace('服务','服務').replace('骏','駿')[:2]
            matches=[r for r in matches if wanted in r['name']]
        if len(matches)!=1:
            results.append(dict(code=m['code'],status='identity_unresolved',candidates=matches));continue
        jobs.append((matches[0],path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(announcements,i,'2019-01-01',end):(i,p) for i,p in jobs}
        for future in as_completed(futures):
            ident,path=futures[future]
            try:
                data=future.result();write_json(path,data)
                result=dict(code=ident['code'],status='acquired',records=len(data['records']))
            except Exception as e:result=dict(code=ident['code'],status='failed',error=str(e))
            results.append(result)
            if progress:progress(result)
    write_json(directory/'acquisition.json',results)
    return results


def download(record, directory, archive=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    name=record['code']+'-'+record['published_on']+'-'+record['id']
    if archive:
        archived=Path(archive)/(name+'.json')
        if archived.is_file():
            prior=json.loads(archived.read_text())
            if all(Path(prior[key]).is_file() for key in ('pdf_path','text_path')):
                result=dict(record,pdf_path=prior['pdf_path'],text_path=prior['text_path'])
                write_json(directory/(name+'.json'),result)
                return result
    pdf=directory/(name+'.pdf');txt=directory/(name+'.txt')
    if not pdf.exists():
        with urlopen(Request(record['url'],headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as r:content=r.read()
        if not content.startswith(b'%PDF'):raise ValueError('公告响应不是PDF')
        pdf.write_bytes(content)
    if not txt.exists():
        subprocess.run(['pdftotext','-layout',str(pdf),str(txt)],check=True,capture_output=True)
    result=dict(record,pdf_path=str(pdf.resolve()),text_path=str(txt.resolve()))
    write_json(directory/(name+'.json'),result)
    return result
