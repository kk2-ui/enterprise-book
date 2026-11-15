"""Public inputs, retained with actual retrieval dates and provider responses."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_data import write_json

REPORTS = {
    'periods': 'RPT_CUSTOM_HKSK_APPFN_CASHFLOW_SUMMARY',
    'income': 'RPT_HKF10_FN_INCOME',
    'balance': 'RPT_HKF10_FN_BALANCE',
    'cashflow': 'RPT_HKF10_FN_CASHFLOW_PC',
    'indicators': 'RPT_HKF10_FN_MAININDICATOR',
}


def fetch_json(url):
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=25) as response:
        return json.load(response)


def financial_report(code, kind):
    params = dict(reportName=REPORTS[kind], columns='ALL', filter=f'(SECUCODE="{code}")',
                  pageSize=5000, pageNumber=1, sortColumns='REPORT_DATE', sortTypes=-1,
                  source='F10', client='PC')
    if kind == 'periods':
        params['columns'] = 'SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,START_DATE,REPORT_DATE,FISCAL_YEAR,CURRENCY,ACCOUNT_STANDARD,REPORT_TYPE'
        for key in ('pageNumber','pageSize','sortColumns','sortTypes'): params.pop(key)
    rows, urls = [], []
    while True:
        url = 'https://datacenter.eastmoney.com/securities/api/data/v1/get?' + urlencode(params)
        response = fetch_json(url)
        result = response.get('result')
        if not response.get('success') or not isinstance(result, dict):
            raise ValueError(response.get('message') or '财报接口未返回数据')
        page_rows = result.get('data') or []
        if kind == 'periods':
            rows = page_rows[0].get('REPORT_LIST', []) if page_rows else []
        else:
            rows.extend(page_rows)
        urls.append(url)
        if kind == 'periods': break
        if params['pageNumber'] >= int(result.get('pages') or 1): break
        params['pageNumber'] += 1
    return dict(code=code, kind=kind, source='东方财富港股财报', urls=urls,
                retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), rows=rows)


def acquire_financials(members, directory, force=False, progress=None):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    tasks, results = [], []
    for member in members:
        for kind in REPORTS:
            path = directory / (member['code']+'-'+kind+'.json')
            if path.exists() and not force:
                results.append(dict(code=member['code'],kind=kind,status='cached',path=str(path)))
            else:
                tasks.append((member['code'],kind,path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(financial_report,code,kind):(code,kind,path) for code,kind,path in tasks}
        for future in as_completed(futures):
            code,kind,path = futures[future]
            try:
                data=future.result();write_json(path,data)
                result=dict(code=code,kind=kind,status='acquired',rows=len(data['rows']),path=str(path))
            except Exception as error:
                result=dict(code=code,kind=kind,status='failed',error=str(error))
            results.append(result)
            if progress:progress(result)
    write_json(directory/'acquisition.json',results)
    return results


def raw_prices(code, cutoff):
    params=dict(secid='116.'+code.split('.')[0], klt=101, fqt=0, lmt=1000000,
                beg='20190101', end=cutoff.replace('-',''),
                fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57')
    url='https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params)
    data=fetch_json(url).get('data') or {}
    rows=[]
    for item in data.get('klines') or []:
        parts=item.split(',')
        rows.append(dict(date=parts[0],close=float(parts[2]),volume=float(parts[5]),amount=float(parts[6])))
    if not rows:raise ValueError('未复权行情缺失')
    return dict(code=code,currency='HKD',adjustment='NONE',source='东方财富未复权日线',source_url=url,
                retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),rows=rows)
