"""Shared observation data for a company or a selected book edition."""

from datetime import date, datetime, timedelta, timezone
from threading import Lock

from market_data import canonical, now_iso, read_json, write_json
from market_observation_update import stock_series
from market_nbs import METRICS as NBS_METRICS
from model_books import read_edition
from source_data.access import facts, manifest

METRIC_ALIASES = {'parent': 'owners_profit', 'profit_parent': 'owners_profit'}
METRICS = {'revenue': '营业收入', 'gross_profit': '毛利', 'cfo': '经营活动现金净额',
           'owners_profit': '归母利润', 'trade_receivables_net': '期末净贸易应收'}
SERIES_LOCKS = {}
SERIES_LOCKS_GUARD = Lock()
UNIT_TO_YI = {'CNY': 1e8, 'CNY_yuan': 1e8, 'CNY_thousand': 1e5, 'CNY_million': 100, 'CNY_100million': 1}


DRIVERS = {
    '000651.SZ': dict(macro='appliances', benchmark='sh000300', cadence=3, macro_note='观察家电终端需求。统计范围包含其他家电品牌和音像器材。',
                      micro_note='存货反映公司账上的备货，合同负债反映预收对价。两者都随季节波动，经销商库存另有口径。',
                      micro={'inventory': '合并存货', 'contracts': '合并合同负债'}),
    '06049.HK': dict(macro='housing', benchmark='hkHSI', cadence=6, macro_note='住宅竣工影响新盘交付的行业环境。存量住宅续约及公建外拓另有驱动。',
                      micro_note='贸易应收款项及票据的期末净额反映已确认但尚待收回的款项，也受项目规模和半年收款节奏影响。',
                      micro={'trade_receivables_net': '贸易应收款项及票据净额'}),
}
STOCK_ALIASES = {'bs_inventory': 'inventory', 'bs_contracts': 'contracts'}


def operating_series(profile, rows, docs, cutoff):
    """Plot each report's current balance on the publication date of the source we actually have."""
    observations = {}
    for row in rows:
        key = STOCK_ALIASES.get(row['metric'], row['metric'])
        doc = docs.get(row['document_id'])
        column = row.get('column_definition') or {}
        period = column.get('end') or column.get('date')
        if (not doc or key not in profile['micro'] or row['scope'] != 'consolidated'
                or column.get('kind') not in ('point_in_time', 'stock') or not period
                or period > doc['published_on'] or row['unit'] not in UNIT_TO_YI):
            continue
        # Within a filing the older column is comparative, not another release on the same day.
        identity = (key, doc['id'])
        if identity in observations and observations[identity]['period'] >= period:
            continue
        observations[identity] = dict(period=period, published=doc['published_on'],
                                      value=float(row['value']) / UNIT_TO_YI[row['unit']],
                                      url=f"{doc['original_url']}#page={row['pdf_page']}",
                                      source=doc['title'], page=row['pdf_page'])
    start = (date.fromisoformat(cutoff) - timedelta(days=731)).isoformat()
    return [dict(label=label, unit='亿元', points=sorted(
        (pt for (metric, _), pt in observations.items() if metric == key and start <= pt['published'] <= cutoff),
        key=lambda p: (p['published'], p['period']))) for key, label in profile['micro'].items()]


def stock_code(company):
    try:
        return canonical(company['code'])
    except ValueError:
        return None


def series_for(directory, code, cutoff, force=False):
    if not code:
        return None, {}
    # Keep this cache distinct from the pilots' intentionally mixed bases.
    path = directory / 'market_observation' / 'unadjusted' / f'{code}.json'
    with SERIES_LOCKS_GUARD:
        lock = SERIES_LOCKS.setdefault(path, Lock())
    with lock:
        return _series_for(path, code, cutoff, force)


def _series_for(path, code, cutoff, force):
    stored = read_json(path)
    checked = (stored or {}).get('checked_cutoffs', [])
    if not force and cutoff in checked:
        latest = max((r['date'] for r in stored['rows'] if r['date'] <= cutoff), default=None)
        lagging = latest and latest < cutoff
        checked_at = stored.get('checked_at')
        retry_after = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        if not lagging or (checked_at and checked_at >= retry_after):
            return stored, dict(finished_at=checked_at,
                                lagging={code: {'last': latest, 'checked_through': cutoff}} if lagging else {})
    try:
        incoming = stock_series(code, cutoff)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        return stored, {'errors': {code: str(error)}}
    old_rows = {row['date']: row for row in stored['rows']} if stored else {}
    latest = incoming['rows'][-1]['date']
    old_rows.update((row['date'], row) for row in incoming['rows'])
    result = dict(incoming, rows=[old_rows[day] for day in sorted(old_rows)],
                  checked_cutoffs=sorted(set([*checked, cutoff])))
    write_json(path, result)
    return result, dict(finished_at=now_iso(),
                        lagging={code: {'last': latest, 'checked_through': cutoff}} if latest < cutoff else {})


def historical_limit(edition):
    if not edition:
        return None
    overview = edition.get('parts', {}).get('overview', {}).get('display') or {}
    cutoff = edition.get('information_cutoff') or edition.get('book_date')
    snapshot_dossier = (edition.get('snapshot') or {}).get('dossier') or {}
    # Early historical editions predate the structured cover flag.
    if overview.get('historical') or snapshot_dossier.get('historical') or '历史企业书' in edition.get('title', ''):
        try:
            return date.fromisoformat(cutoff).isoformat()
        except (ValueError, TypeError):
            return None
    return None


def selected_edition(store, company, edition_id):
    edition_id = edition_id or company.get('default_book_edition_id')
    if not edition_id and company.get('book_editions'):
        edition_id = company['book_editions'][0]['id']
    return read_edition(store, company['id'], edition_id) if edition_id else None


def valuation(company, edition, cutoff):
    if not edition:
        return {'reason': '尚未保存可链接的企业书估值。'}
    part = edition.get('parts', {}).get('valuation') or {}
    snapshot = edition.get('snapshot') or {}
    info = edition.get('information_cutoff') or edition.get('book_date')
    published = (edition.get('completed_at') or edition.get('created_at') or '')[:10]
    if not info or not published or cutoff < max(info, published):
        return {'reason': '截至所选日期尚未成版或本版估值时点未登记。'}
    if not part.get('body') and not snapshot.get('dossier'):
        return {'reason': '本版尚未保存估值正文。'}
    display = edition.get('parts', {}).get('overview', {}).get('display') or {}
    metrics = display.get('valuation') or snapshot
    return dict(date=info, published_on=published, title=edition['title'],
                cash=metrics.get('cash'), cash_label=metrics.get('cash_label'),
                value=metrics.get('value'), value_label=metrics.get('value_label'),
                url=f"#/company/{company['id']}/editions?edition={edition['id']}&view=valuation")


def disclosures(store, company, edition, cutoff, drivers=None):
    repo = store.source_data
    cid = company['id']
    if edition:
        versions = [edition['source_version']] if edition.get('source_version') else []
    else:
        versions = [p['id'] for p in repo.packages(cid) if p.get('information_cutoff', '') <= cutoff]
    for version in versions:
        try:
            package = manifest(repo, cid, version)
            rows = facts(repo, cid, version)['disclosed']
        except (OSError, ValueError):
            continue
        docs = {d['id']: d for d in package['documents']
                if d.get('published_on') and d['published_on'] <= cutoff
                and d.get('nature') == 'company_disclosure'}
        if drivers is not None:
            drivers['series'] = operating_series(DRIVERS[stock_code(company)], rows, docs, cutoff)
        groups = {}
        for row in rows:
            doc = docs.get(row['document_id'])
            metric = METRIC_ALIASES.get(row['metric'], row['metric'])
            divisor = UNIT_TO_YI.get(row['unit'])
            period = row.get('column_definition', {}).get('end')
            if not (doc and metric in METRICS and divisor and period and period <= cutoff):
                continue
            if row.get('scope') not in ('consolidated', 'owners', 'parent', '合并；归母指标按原行归属'):
                continue
            key = (period, doc['published_on'], doc['id'], row['period'])
            groups.setdefault(key, {})[metric] = row
        if not groups:
            continue
        recent = []
        periods = set()
        for key, metrics in sorted(groups.items(), reverse=True):
            period, published, doc_id, period_label = key
            # Keep one recent flow card per reporting period. Balance rows can be shown separately.
            identity = (period, 'revenue' in metrics)
            if identity in periods or len(recent) == 3:
                continue
            periods.add(identity)
            doc = docs[doc_id]
            recent.append(dict(title=doc['title'], period=period_label, published=published,
                               metrics=[(METRICS[m], f"{float(row['value']) / UNIT_TO_YI[row['unit']]:,.2f} 亿元")
                                        for m, row in metrics.items()],
                               sources=[(f"原件第 {page} 页", f"{doc['original_url']}#page={page}", published)
                                        for page in sorted({row['pdf_page'] for row in metrics.values()})]))
        return recent
    return []


def response(store, company, cutoff, edition=None, limit=None):
    code = stock_code(company)
    # Each cutoff needs its own full lookback, even if newer prices are cached.
    stored, refresh = series_for(store.directory, code, cutoff)
    start = (date.fromisoformat(cutoff) - timedelta(days=400)).isoformat()
    rows = [row for row in stored['rows'] if start <= row['date'] <= cutoff] if stored else []
    unit = '港元/股' if code and code.endswith('.HK') else '元/股'
    chart = [{'date': row['date'], 'values': {code: row['close']}} for row in rows]
    cover = [dict(code=code, label=company['name'], source=stored.get('source') if stored else None,
                  url=stored.get('url') if rows else None, start=rows[0]['date'] if rows else None,
                  end=rows[-1]['date'] if rows else None, count=len(rows))] if code else []
    mode = dict(key='close', label='未复权收盘',
                lanes=[dict(items=[dict(key=code, label=company['name'], unit=unit, color='stock')])])
    profile = DRIVERS.get(code)
    drivers = dict(macro=profile['macro'], macro_label=NBS_METRICS[profile['macro']] + '累计同比',
                   cadence=profile['cadence'], macro_note=profile['macro_note'],
                   micro_note=profile['micro_note'], series=[]) if profile else None
    cards = disclosures(store, company, edition, cutoff, drivers)
    return dict(observation='company', company=company['name'], cutoff=cutoff, chart=chart, drivers=drivers,
                modes=[mode] if code else [], coverage=cover, events=[], refresh=refresh,
                valuation=valuation(company, edition, cutoff), cards=cards,
                price_snapshot=None, historical_limit=limit)
