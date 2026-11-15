"""ECB reference cross rates; publication is after the Hong Kong close."""
import csv
from datetime import date,timedelta
import io
import zipfile
from urllib.request import urlopen

URL='https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip'


def acquire():
    with urlopen(URL,timeout=30) as response:payload=response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read(archive.namelist()[0]).decode('utf-8-sig')


def parse(text):
    rows=[]
    for r in csv.DictReader(io.StringIO(text)):
        if r['Date']<'2019-01-01':continue
        if r.get('HKD') in (None,'N/A') or r.get('CNY') in (None,'N/A'):continue
        rows.append(dict(as_of=r['Date'],available_on=(date.fromisoformat(r['Date'])+timedelta(days=1)).isoformat(),
                         rates={'CNY/HKD':float(r['HKD'])/float(r['CNY']),
                                'USD/HKD':float(r['HKD'])/float(r['USD'])},source_url=URL,
                         formula='每欧元港元数 / 每欧元人民币数',basis='欧洲央行参考汇率；非港股收盘即期汇率'))
    return sorted(rows,key=lambda r:r['as_of'])


def at(rows,day,information_cutoff=None):
    valid=[r for r in rows if r['as_of']<=day and r['available_on']<=(information_cutoff or day)]
    return valid[-1] if valid else None
