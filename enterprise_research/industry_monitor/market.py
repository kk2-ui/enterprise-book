"""Use the existing factor calculation only after aligning gross total returns."""
import json
from pathlib import Path
from market_context import build_context
from .returns import cash_events,total_return
from .indices import TR_CODES


def from_inputs(root,universe,cutoff):
    root=Path(root);series={};errors=[]
    for m in universe['members']:
        try:
            raw=json.loads((root/'prices'/(m['code']+'.json')).read_text())
            div=json.loads((root/'dividends'/(m['code']+'.json')).read_text())
            events,unknown=cash_events(div)
            index=json.loads((root/'hkex_index'/(m['code']+'.json')).read_text())
            if not index['records']:raise ValueError('资本事件公告目录未取得')
            complex_events=[r for r in index['records'] if any(x in r['title'] for x in ('股份合併','股份拆細','紅股發行','實物分派','供股'))]
            if complex_events:raise ValueError('存在供股或其他非现金权益，待原件核算后加入含息参照')
            value=total_return(raw,events,unresolved=unknown)
            value.update(name=m['name'],captured_at=div['retrieved_at'],code=m['code'])
            series[m['code']]=value
        except (OSError,ValueError,KeyError) as e:errors.append(dict(code=m['code'],error=str(e)))
    for code,identifier in TR_CODES.items():
        p=root/'indices'/(code+'-total-return.json')
        if p.exists():value=json.loads(p.read_text())
        else:
            raw=json.loads((root/'indices'/(identifier+'.json')).read_text());data=raw['data'][0]
            from .indices import BASE
            from urllib.parse import urlencode
            url=raw.get('source_url') or BASE+'product-data/pub/indexes/metadata/v2?'+urlencode(dict(data='valueHistoryPub',indexCodes=identifier,language='eng'))
            value=dict(code=code,name=data['indexName'],currency='HKD',adjustment='TOTAL_RETURN_GROSS',
                       source='恒生指数公司公开总回报指数',source_url=url,captured_at=raw.get('retrieved_at'),
                       rows=[dict(date=r['date'],close=float(r['close']),volume=None) for r in data['valueHistory']])
        value['rows']=[r for r in value['rows'] if r['date']<=cutoff];series[code]=value
    profile=dict(label='基础物业广样本',scope=universe['scope'],aggregation='daily_median',sector_history='property',
                 peers=[{k:m[k] for k in ('code','name','reason','source')} for m in universe['members'] if m['group']=='basic' and m['code']!='06049.HK'],
                 excluded=[{k:m[k] for k in ('code','name','reason','source')} for m in universe['members'] if m['group']!='basic'])
    result=build_context('06049.HK',profile,series,errors,cutoff,universe['version'])
    result['method_version']='market-context-total-return-v1'
    result['return_convention']='税前现金股息在除净日按收盘价再投资；不含税费；复杂权益未核定的证券剔除'
    result['return_coverage']=dict(included=[c for c in series if c.endswith('.HK')],excluded=errors,
                                   official_index_start=min(r['date'] for r in series['HSCI']['rows']))
    # A separately labelled price-only long history can start earlier than the
    # official five-year total-return feed. Never splice their levels together.
    price_index=root/'indices/HSCI-price.json'
    if price_index.exists():
        from sector_history import build_history
        raw_series={'HSCI':json.loads(price_index.read_text())}
        for m in universe['members']:
            if m['code']=='01778.HK':continue  # unresolved 2025 rights issue
            path=root/'prices'/(m['code']+'.json')
            if path.exists():raw_series[m['code']]=json.loads(path.read_text())
        h=build_history('06049.HK',raw_series,universe)
        h['return_basis']='PRICE_ONLY'
        if h['status']=='ready':
            h['notes']=[n for n in h['notes'] if '前复权' not in n]
            h['notes'].insert(0,'本节全部采用未复权价格变化，未计现金分红；有未核定供股的彩生活留在名单但不计算涨跌。与下方统一含息的短中期模型分开。')
        result['sector_history']=h
    return result,series
