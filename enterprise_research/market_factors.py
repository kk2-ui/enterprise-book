# enterprise_research/market_factors.py
from __future__ import annotations

import math
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from market_data import HONG_KONG, checked_rows, read_json, write_json
from market_observation_update import TENCENT, fetch, start_day

NY_TZ = ZoneInfo("America/New_York")
RETRY_INTERVAL = timedelta(minutes=30)

_LOCKS_GUARD = threading.Lock()
_SOURCE_LOCKS: dict[str, threading.Lock] = {}

BENCHMARKS = {
    "sh000300": {
        "label": "沪深300",
        "unit": "点",
        "url": "https://gu.qq.com/sh000300",
        "source": "腾讯证券",
        "referer": "https://gu.qq.com/",
    },
    "hkHSI": {
        "label": "恒生指数",
        "unit": "点",
        "url": "https://gu.qq.com/hkHSI",
        "source": "腾讯证券",
        "referer": "https://gu.qq.com/",
    },
}

DXY_META = {
    "label": "ICE 美元指数 (DXY)",
    "unit": "点",
    "url": "https://finance.yahoo.com/quote/DX-Y.NYB/history/",
    "spec_url": "https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices",
    "source": "Yahoo Finance (ICE Data Indices 口径)",
    "referer": "https://finance.yahoo.com/",
}

YAHOO_DXY_URLS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
    "https://query2.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
)


def _get_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _SOURCE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SOURCE_LOCKS[key] = lock
        return lock


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _pos_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return round(num, 4) if math.isfinite(num) and num > 0 else None


def _expected_market_day(target: date, is_dxy: bool) -> date:
    wd = target.weekday()
    if is_dxy:
        # HK available date = NY session + 1 calendar day (Mon..Fri NY -> Tue..Sat HK)
        if wd == 6:
            return target - timedelta(days=1)
        if wd == 0:
            return target - timedelta(days=2)
        return target
    if wd == 5:
        return target - timedelta(days=1)
    if wd == 6:
        return target - timedelta(days=2)
    return target


def _in_retry_window(state: dict, window_start: str, cutoff: str, now_hk: datetime) -> bool:
    if state.get("attempted_cutoff") != cutoff:
        return False
    att_start = state.get("attempted_start")
    if isinstance(att_start, str) and att_start > window_start:
        return False
    retry_after_raw = state.get("retry_after")
    if not isinstance(retry_after_raw, str):
        return False
    try:
        retry_after = datetime.fromisoformat(retry_after_raw)
    except ValueError:
        return False
    if retry_after.tzinfo is None:
        retry_after = retry_after.replace(tzinfo=HONG_KONG)
    return now_hk < retry_after


def _merge_spans(spans: list[list[str]], new_span: tuple[str, str] | None) -> list[list[str]]:
    valid: list[tuple[str, str]] = []
    for item in spans:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            s, e = str(item[0]), str(item[1])
            if _parse_day(s) and _parse_day(e) and s <= e:
                valid.append((s, e))
    if new_span and _parse_day(new_span[0]) and _parse_day(new_span[1]) and new_span[0] <= new_span[1]:
        valid.append(new_span)
    if not valid:
        return []
    valid.sort(key=lambda x: (x[0], x[1]))
    merged: list[list[str]] = [[valid[0][0], valid[0][1]]]
    for s, e in valid[1:]:
        prev_s, prev_e = merged[-1]
        if (_parse_day(s) - _parse_day(prev_e)).days <= 4:
            if e > prev_e:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    return merged


def _span_covers(spans: list[list[str]], window_start: str, end_target: str) -> bool:
    for s, e in spans:
        if s <= window_start and e >= end_target:
            return True
    return False


def _normalize_rows(raw_items: list[dict], has_session: bool) -> list[dict]:
    merged_by_date: dict[str, dict] = {}
    for r in raw_items:
        if not isinstance(r, dict):
            continue
        d = r.get("date")
        c = _pos_float(r.get("close"))
        if _parse_day(d) is None or c is None:
            continue
        if has_session:
            s = r.get("session")
            if _parse_day(s) is None:
                continue
            merged_by_date[d] = {"date": d, "session": s, "close": c}
        else:
            merged_by_date[d] = {"date": d, "close": c}
    if not merged_by_date:
        return []
    ordered = [merged_by_date[k] for k in sorted(merged_by_date.keys())]
    validated = checked_rows(ordered)
    if not has_session:
        return [{"date": r["date"], "close": _pos_float(r["close"]) or r["close"]} for r in validated]
    return [
        {
            "date": r["date"],
            "session": r.get("session") or merged_by_date[r["date"]]["session"],
            "close": _pos_float(r["close"]) or r["close"],
        }
        for r in validated
        if r.get("date") in merged_by_date
    ]


def _read_factor_cache(path: Path, has_session: bool) -> tuple[list[dict], dict]:
    if not path.exists():
        return [], {}
    try:
        raw = read_json(path)
    except (OSError, ValueError, TypeError):
        return [], {}
    if not isinstance(raw, dict):
        return [], {}
    items = raw.get("points") if isinstance(raw.get("points"), list) else []
    try:
        rows = _normalize_rows(items, has_session=has_session)
    except (ValueError, KeyError, TypeError):
        rows = []
    state = {
        "attempted_cutoff": raw.get("attempted_cutoff", ""),
        "attempted_start": raw.get("attempted_start", ""),
        "retry_after": raw.get("retry_after", ""),
        "covered_spans": raw.get("covered_spans") if isinstance(raw.get("covered_spans"), list) else [],
    }
    if not state["covered_spans"] and len(rows) >= 2:
        state["covered_spans"] = [[rows[0]["date"], rows[-1]["date"]]]
    return rows, state


def _should_refresh(
    rows: list[dict],
    state: dict,
    window_start: str,
    cutoff: str,
    is_dxy: bool,
    now_hk: datetime,
) -> bool:
    upto = [r for r in rows if r["date"] <= cutoff]
    if not upto:
        return not _in_retry_window(state, window_start, cutoff, now_hk)

    spans = _merge_spans(state.get("covered_spans", []), None)
    dt_cutoff = _parse_day(cutoff)
    effective_target = min(dt_cutoff, now_hk.date()) if dt_cutoff else now_hk.date()
    expected_day = _expected_market_day(effective_target, is_dxy=is_dxy).isoformat()

    # Check if historical left boundary [window_start, upto[-1]] is missing from covered spans
    if not _span_covers(spans, window_start, upto[-1]["date"]):
        dt_first = _parse_day(upto[0]["date"])
        dt_start = _parse_day(window_start)
        if not dt_first or not dt_start or (dt_first - dt_start).days > 7:
            return not _in_retry_window(state, window_start, cutoff, now_hk)

    # Exact cutoff day is present in cache -> fresh
    if upto[-1]["date"] == cutoff:
        return False

    # Historical query completely inside an already-fetched span beyond cutoff
    if rows[-1]["date"] > cutoff and _span_covers(spans, window_start, cutoff):
        return False

    # New cutoff not yet attempted when cutoff itself is absent from cache -> refresh immediately
    if state.get("attempted_cutoff") != cutoff:
        return True

    # Already attempted this cutoff: if lagging behind expected completed market day (including weekend check), retry every 30 min
    if upto[-1]["date"] < expected_day:
        return not _in_retry_window(state, window_start, cutoff, now_hk)

    return False


def _write_factor_cache(
    path: Path,
    existing_rows: list[dict],
    incoming_rows: list[dict],
    meta_info: dict,
    state: dict,
    window_start: str,
    cutoff: str,
    now_hk: datetime,
    has_session: bool,
    fetch_succeeded: bool,
) -> list[dict]:
    merged_rows = _normalize_rows([*existing_rows, *incoming_rows], has_session=has_session)
    new_span = None
    if fetch_succeeded and incoming_rows:
        span_end = max(incoming_rows[-1]["date"], cutoff if incoming_rows[-1]["date"] >= cutoff else incoming_rows[-1]["date"])
        # If cutoff is a weekend/holiday and we received up to expected market day in the past, mark cutoff covered if cutoff < today
        if cutoff < now_hk.date().isoformat() and incoming_rows[-1]["date"] >= _expected_market_day(_parse_day(cutoff), has_session).isoformat():
            span_end = max(span_end, cutoff)
        new_span = (min(window_start, incoming_rows[0]["date"]), span_end)

    spans = _merge_spans(state.get("covered_spans", []), new_span)
    prev_att_start = state.get("attempted_start")
    att_start = min(prev_att_start, window_start) if (isinstance(prev_att_start, str) and _parse_day(prev_att_start) and state.get("attempted_cutoff") == cutoff) else window_start

    payload = {
        "key": meta_info["key"],
        "label": meta_info["label"],
        "unit": meta_info["unit"],
        "source": meta_info["source"],
        "url": meta_info["url"],
        "attempted_cutoff": cutoff,
        "attempted_start": att_start,
        "retry_after": (now_hk + RETRY_INTERVAL).isoformat(timespec="seconds"),
        "updated_at": now_hk.isoformat(timespec="seconds"),
        "covered_spans": spans,
        "points": merged_rows,
    }
    if meta_info.get("spec_url"):
        payload["spec_url"] = meta_info["spec_url"]
    write_json(path, payload)
    return merged_rows


def _fetch_tencent_benchmark(benchmark: str, begin: str, cutoff: str) -> list[dict]:
    cfg = BENCHMARKS[benchmark]
    query = urlencode({"param": f"{benchmark},day,{begin},{cutoff},640,"})
    payload = fetch(f"{TENCENT}?{query}", cfg["referer"])
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise RuntimeError(f"{cfg['label']}接口异常 code={payload.get('code') if isinstance(payload, dict) else 'invalid'}")

    sec = (payload.get("data") or {}).get(benchmark) if isinstance(payload.get("data"), dict) else None
    bars = sec.get("day") if isinstance(sec, dict) else None
    if not isinstance(bars, list):
        raise RuntimeError(f"{cfg['label']}未返回未复权 day 序列（可能不支持历史区间 {begin}..{cutoff}）")

    raw_rows = [
        {"date": str(bar[0]).strip(), "close": bar[2]}
        for bar in bars
        if isinstance(bar, (list, tuple)) and len(bar) >= 3 and str(bar[0]).strip() <= cutoff
    ]
    rows = _normalize_rows(raw_rows, has_session=False)
    if not rows:
        raise RuntimeError(f"{cfg['label']}在区间 {begin}..{cutoff} 无有效收盘记录")
    return rows


def _parse_yahoo_dxy(payload: dict, cutoff: str) -> list[dict]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        raise RuntimeError("Yahoo DXY 缺少 chart 响应结构")
    if chart.get("error"):
        raise RuntimeError(f"Yahoo DXY 不支持该历史请求或报错: {chart['error']}")

    results = chart.get("result")
    res = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else None
    if res is None:
        raise RuntimeError("Yahoo DXY 缺少 result 数据")

    meta = res.get("meta") if isinstance(res.get("meta"), dict) else {}
    if (
        meta.get("symbol") != "DX-Y.NYB"
        or "ICE Futures" not in str(meta.get("fullExchangeName") or "")
        or meta.get("instrumentType") != "INDEX"
        or meta.get("exchangeTimezoneName") != "America/New_York"
    ):
        raise RuntimeError(
            f"DXY 身份元数据不匹配: symbol={meta.get('symbol')}, exchange={meta.get('fullExchangeName')}, "
            f"type={meta.get('instrumentType')}, tz={meta.get('exchangeTimezoneName')}"
        )

    timestamps = res.get("timestamp")
    quotes = (res.get("indicators") or {}).get("quote")
    closes = quotes[0].get("close") if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict) else None
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        raise RuntimeError("Yahoo DXY 未返回所请求区间的日线序列")

    today_ny = datetime.now(NY_TZ).date()
    raw_rows: list[dict] = []
    for ts, raw_close in zip(timestamps, closes):
        if not isinstance(ts, (int, float)):
            continue
        dt_ny = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(NY_TZ)
        if dt_ny.hour != 0 or dt_ny.minute != 0 or dt_ny.second != 0:
            continue
        session_day = dt_ny.date()
        if session_day >= today_ny:
            continue
        hk_date = (session_day + timedelta(days=1)).isoformat()
        if hk_date > cutoff:
            continue
        close_val = _pos_float(raw_close)
        if close_val is None:
            continue
        raw_rows.append({
            "date": hk_date,
            "session": session_day.isoformat(),
            "close": close_val,
        })

    rows = _normalize_rows(raw_rows, has_session=True)
    if not rows:
        raise RuntimeError("Yahoo DXY 未解析出有效纽约零点完整日线")
    return rows


def _fetch_yahoo_dxy(begin: str, cutoff: str) -> list[dict]:
    dt_begin = datetime.strptime(begin, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    dt_cutoff = datetime.strptime(cutoff, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    params = urlencode({
        "period1": int((dt_begin - timedelta(days=7)).timestamp()),
        "period2": int((dt_cutoff + timedelta(days=2)).timestamp()),
        "interval": "1d",
    })
    errs: list[str] = []
    for base in YAHOO_DXY_URLS:
        try:
            return _parse_yahoo_dxy(fetch(f"{base}?{params}", DXY_META["referer"]), cutoff)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errs.append(f"{base.split('/')[2]}: {exc}")
    raise RuntimeError(f"DXY 区间 {begin}..{cutoff} 获取失败（{'；'.join(errs)}）")


def _sync_factor(
    lock_key: str,
    cache_path: Path,
    meta_info: dict,
    window_start: str,
    cutoff: str,
    is_dxy: bool,
    fetcher,
) -> tuple[list[dict], str]:
    with _get_lock(lock_key):
        now_hk = datetime.now(HONG_KONG)
        rows, state = _read_factor_cache(cache_path, has_session=is_dxy)
        err_note = ""

        if _should_refresh(rows, state, window_start, cutoff, is_dxy=is_dxy, now_hk=now_hk):
            try:
                incoming = fetcher(window_start, cutoff)
                rows = _write_factor_cache(
                    cache_path, rows, incoming, meta_info, state,
                    window_start, cutoff, now_hk, has_session=is_dxy, fetch_succeeded=True,
                )
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                err_note = f"{meta_info['label']}拉取失败（已回退本地缓存）：{exc}"
                rows = _write_factor_cache(
                    cache_path, rows, [], meta_info, state,
                    window_start, cutoff, now_hk, has_session=is_dxy, fetch_succeeded=False,
                )

        win_rows = [r for r in rows if window_start <= r["date"] <= cutoff]
        if win_rows and not err_note:
            gap_head = (_parse_day(win_rows[0]["date"]) - _parse_day(window_start)).days
            if gap_head > 14:
                err_note = f"{meta_info['label']}历史起点受上游限制，实际最早覆盖自 {win_rows[0]['date']}（请求起点 {window_start}）"
        elif not win_rows and not err_note:
            err_note = f"{meta_info['label']}上游服务不支持或未返回区间 {window_start}..{cutoff} 的有效日线"

        return win_rows, err_note


def _format_coverage(label: str, pts: list[dict], window_start: str, cutoff: str, is_dxy: bool) -> str:
    if not pts:
        return f"{label}在 [{window_start}, {cutoff}] 暂无可用记录"
    if is_dxy:
        return (
            f"{label}实际覆盖 {pts[0]['date']} 至 {pts[-1]['date']}"
            f"（{len(pts)} 条完整日线，最新对应纽约 {pts[-1]['session']} 收盘）"
        )
    return f"{label}实际覆盖 {pts[0]['date']} 至 {pts[-1]['date']}（{len(pts)} 个交易日）"


def series(directory: str | Path, benchmark: str, cutoff: str) -> dict:
    if benchmark not in BENCHMARKS:
        raise ValueError(f"Unsupported benchmark: {benchmark!r}")
    if _parse_day(cutoff) is None:
        raise ValueError(f"Invalid cutoff date: {cutoff!r}")

    factors_dir = Path(directory) / "market_observation" / "factors"
    factors_dir.mkdir(parents=True, exist_ok=True)
    window_start = start_day(cutoff, 400)

    bm_cfg = BENCHMARKS[benchmark]
    bm_rows, bm_err = _sync_factor(
        lock_key=f"benchmark:{benchmark}",
        cache_path=factors_dir / f"{benchmark}.json",
        meta_info={"key": benchmark, **bm_cfg},
        window_start=window_start,
        cutoff=cutoff,
        is_dxy=False,
        fetcher=lambda b, c: _fetch_tencent_benchmark(benchmark, b, c),
    )

    dxy_rows, dxy_err = _sync_factor(
        lock_key="factor:DX-Y.NYB",
        cache_path=factors_dir / "dxy.json",
        meta_info={"key": "DX-Y.NYB", **DXY_META},
        window_start=window_start,
        cutoff=cutoff,
        is_dxy=True,
        fetcher=_fetch_yahoo_dxy,
    )

    cov_summary = "；".join([
        _format_coverage(bm_cfg["label"], bm_rows, window_start, cutoff, is_dxy=False),
        _format_coverage(DXY_META["label"], dxy_rows, window_start, cutoff, is_dxy=True),
    ])
    errs = [e for e in (bm_err, dxy_err) if e]
    message = f"{'；'.join(errs)}｜{cov_summary}" if errs else cov_summary

    return {
        "benchmark": {
            "key": benchmark,
            "label": bm_cfg["label"],
            "unit": bm_cfg["unit"],
            "source": bm_cfg["source"],
            "url": bm_cfg["url"],
            "points": bm_rows,
            "error": bm_err,
        },
        "dxy": {
            "key": "DX-Y.NYB",
            "label": DXY_META["label"],
            "unit": DXY_META["unit"],
            "source": DXY_META["source"],
            "url": DXY_META["url"],
            "spec_url": DXY_META["spec_url"],
            "points": dxy_rows,
            "error": dxy_err,
        },
        "message": message,
    }
