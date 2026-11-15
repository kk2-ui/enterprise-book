"""Official public HSI endpoints, separate from the authenticated Index360 API."""
from urllib.parse import urlencode
from .acquisition import fetch_json
from datetime import datetime,timezone

BASE='https://www.hsi.com.hk/api/wsit-hsi-ddoc-ea-public-website-proxy/v1/'
TR_CODES={'HSCI':'10069.00','HSLI':'10070.00','HSSI':'10074.00'}


def total_return(code):
    url=BASE+'product-data/pub/indexes/metadata/v2?'+urlencode(dict(data='valueHistoryPub',indexCodes=TR_CODES[code],language='eng'))
    raw=fetch_json(url)
    if raw.get('code')!='0' or len(raw.get('data',[]))!=1:raise ValueError('恒生公开指数历史未取得')
    data=raw['data'][0]
    if data.get('indexCode')!=TR_CODES[code]:raise ValueError('指数身份不匹配')
    return dict(code=code,name=data['indexName'],currency='HKD',adjustment='TOTAL_RETURN_GROSS',
                source='恒生指数公司公开总回报指数',source_url=url,captured_at=datetime.now(timezone.utc).isoformat(),
                rows=[dict(date=r['date'],close=float(r['close']),volume=None) for r in data['valueHistory']])


def factsheet_values(text,source_url,retrieved_at):
    """Read only the official factsheet valuation columns, retaining its date."""
    import re
    stamp=re.search(r'All data as at (\d{1,2} [A-Za-z]{3} \d{4})',text)
    if not stamp or 'PE Ratio' not in text or 'Yield (%)' not in text:
        raise ValueError('恒生概览的日期或估值列无法识别')
    as_of=datetime.strptime(stamp.group(1),'%d %b %Y').date().isoformat();out=[]
    for line in text.splitlines():
        m=re.match(r'\s*(HSCI|HSLI|HSSI)\s+',line)
        if not m:continue
        values=re.findall(r'[-+]?\d[\d,]*(?:\.\d+)?',line[m.end():])
        if len(values)!=11:continue  # performance/correlation rows are not valuation rows
        values=[float(v.replace(',','')) for v in values]
        out.append(dict(index=m.group(1),as_of=as_of,pe=values[-2],dividend_yield=values[-3]/100,pb=None,
                        available_on=retrieved_at[:10],retrieved_at=retrieved_at,published_on=None,
                        source_url=source_url,excerpt=line,definition='恒生官方概览的PE及股息率原口径；不等同本批行业归母财报汇总',
                        limitation='资料期末不同于行情日；首次公开日期未知，不用于严格历史分位；该概览未披露PB'))
    if {r['index'] for r in out}!={'HSCI','HSLI','HSSI'}:raise ValueError('恒生概览缺少本批三个指数估值行')
    return out


def acquire_factsheet(directory):
    from pathlib import Path
    from urllib.request import urlopen,Request
    import subprocess
    from market_data import write_json
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    url=BASE+'content/gcs/download?'+urlencode(dict(resource='/public-website/webapp/factsheets/en-hk/hsci.pdf'))
    p=root/'hsci-fundamentals.pdf';txt=p.with_suffix('.txt');stamp=datetime.now(timezone.utc).isoformat()
    if not p.exists():
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as r:data=r.read()
        if not data.startswith(b'%PDF'):raise ValueError('恒生估值原件不是PDF')
        p.write_bytes(data)
    if not txt.exists():subprocess.run(['pdftotext','-layout',str(p),str(txt)],check=True,capture_output=True)
    values=factsheet_values(txt.read_text(),url,stamp)
    write_json(root/'official-valuations.json',dict(values=values,pdf_path=str(p.resolve()),text_path=str(txt.resolve()),retrieved_at=stamp,source_url=url))
    return values
