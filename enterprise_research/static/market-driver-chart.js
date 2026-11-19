// enterprise_research/static/market-driver-chart.js

const STYLE_ID = 'er-mo-workbench-v2-style';
const STATE_MAP = new WeakMap();

const STYLES = `
.er-mo-wb {
  --wb-bg: #fcfcfa;
  --wb-panel: #ffffff;
  --wb-subtle: #f5f6f8;
  --wb-border: #dfe3ea;
  --wb-border-strong: #c5cdd8;
  --wb-ink: #161d27;
  --wb-ink-sec: #4a5568;
  --wb-ink-muted: #768295;
  --wb-gree: #0e5a8a;
  --wb-gree-alt: #b85d19;
  --wb-poly: #146c54;
  --wb-bench: #64748b;
  --wb-macro: #5b4b8a;
  --wb-dxy: #8f3d26;
  --wb-warn-bg: #fff8eb;
  --wb-warn-bd: #e8c987;
  --wb-warn-tx: #7c5211;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  color: var(--wb-ink);
  background: var(--wb-bg);
  border: 1px solid var(--wb-border);
  border-radius: 6px;
  padding: 14px 16px 12px;
  box-sizing: border-box;
  line-height: 1.45;
  font-variant-numeric: tabular-nums;
}
.er-mo-wb *, .er-mo-wb *::before, .er-mo-wb *::after {
  box-sizing: border-box;
}
.er-mo-wb a.er-mo-link {
  color: #1d4ed8;
  text-decoration: none;
  border-bottom: 1px dotted #93c5fd;
  font-size: 11.5px;
  white-space: nowrap;
}
.er-mo-wb a.er-mo-link:hover {
  color: #1e3a8a;
  border-bottom-style: solid;
}
.er-mo-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--wb-border);
}
.er-mo-title-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.er-mo-badge {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.03em;
  padding: 2px 7px;
  border-radius: 3px;
  color: #fff;
  background: var(--wb-gree);
}
.er-mo-wb[data-theme="poly"] .er-mo-badge {
  background: var(--wb-poly);
}
.er-mo-heading {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--wb-ink);
}
.er-mo-subtag {
  font-size: 11.5px;
  color: var(--wb-ink-sec);
  background: var(--wb-subtle);
  border: 1px solid var(--wb-border);
  padding: 1px 7px;
  border-radius: 3px;
}
.er-mo-cursor-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.er-mo-day-pill {
  font-weight: 700;
  color: var(--wb-ink);
  background: #eef2f7;
  border: 1px solid var(--wb-border-strong);
  border-radius: 3px;
  padding: 2px 8px;
}
.er-mo-day-pill[data-pinned="1"] {
  background: #fef3c7;
  border-color: #d97706;
  color: #78350f;
}
.er-mo-btn {
  cursor: pointer;
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid var(--wb-border-strong);
  background: var(--wb-panel);
  color: var(--wb-ink-sec);
}
.er-mo-btn:hover {
  background: var(--wb-subtle);
  color: var(--wb-ink);
}
.er-mo-clue-box {
  margin-top: 10px;
  background: var(--wb-panel);
  border: 1px solid var(--wb-border);
  border-left: 3px solid var(--wb-gree);
  border-radius: 4px;
  padding: 10px 12px;
}
.er-mo-wb[data-theme="poly"] .er-mo-clue-box {
  border-left-color: var(--wb-poly);
}
.er-mo-clue-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
}
.er-mo-clue-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--wb-ink);
}
.er-mo-clue-rule {
  font-size: 11px;
  color: var(--wb-ink-muted);
}
.er-mo-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px;
}
.er-mo-kpi {
  background: var(--wb-subtle);
  border: 1px solid #e6e9ef;
  border-radius: 4px;
  padding: 7px 9px;
}
.er-mo-kpi-label {
  font-size: 11px;
  color: var(--wb-ink-sec);
  display: flex;
  justify-content: space-between;
  gap: 4px;
}
.er-mo-kpi-val {
  font-size: 14px;
  font-weight: 700;
  color: var(--wb-ink);
  margin: 2px 0;
}
.er-mo-kpi-meta {
  font-size: 11px;
  color: var(--wb-ink-muted);
  line-height: 1.35;
}
.er-mo-tracks {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.er-mo-track {
  background: var(--wb-panel);
  border: 1px solid var(--wb-border);
  border-radius: 4px;
  padding: 7px 10px 6px;
}
.er-mo-track-hdr {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 6px 12px;
  margin-bottom: 4px;
}
.er-mo-track-lhs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.er-mo-track-tag {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 2px;
  background: #edf1f7;
  color: #334155;
  border: 1px solid #d5dde8;
}
.er-mo-track-name {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--wb-ink);
}
.er-mo-track-unit {
  font-size: 11px;
  color: var(--wb-ink-muted);
}
.er-mo-track-val {
  font-size: 12px;
  color: var(--wb-ink);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}
.er-mo-swatch {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
  margin-right: 3px;
  vertical-align: middle;
}
.er-mo-swatch-dash {
  display: inline-block;
  width: 12px;
  height: 0;
  border-top: 2px dashed var(--wb-bench);
  margin-right: 4px;
  vertical-align: middle;
}
.er-mo-plot {
  position: relative;
  width: 100%;
  user-select: none;
  outline: none;
}
.er-mo-plot:focus-visible {
  box-shadow: 0 0 0 2px rgba(29, 78, 216, 0.35);
  border-radius: 3px;
}
.er-mo-svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  cursor: crosshair;
}
.er-mo-empty {
  height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--wb-subtle);
  border: 1px dashed var(--wb-border-strong);
  border-radius: 3px;
  font-size: 12px;
  color: var(--wb-ink-muted);
  padding: 0 12px;
  text-align: center;
}
.er-mo-track-foot {
  margin-top: 3px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 12px;
  font-size: 11px;
  color: var(--wb-ink-muted);
}
.er-mo-status-strip {
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.45;
  background: var(--wb-subtle);
  border: 1px solid var(--wb-border);
  color: var(--wb-ink-sec);
}
.er-mo-status-strip[data-warn="1"] {
  background: var(--wb-warn-bg);
  border-color: var(--wb-warn-bd);
  color: var(--wb-warn-tx);
}
.er-mo-guardrails {
  margin-top: 6px;
  font-size: 11px;
  color: var(--wb-ink-muted);
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 14px;
}
`;

function injectStyles() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = STYLES;
  document.head.appendChild(style);
}

function escText(val) {
  if (val === null || val === undefined) return '';
  const s = String(val);
  if (typeof window !== 'undefined' && typeof window.esc === 'function') {
    return window.esc(s);
  }
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeHref(raw) {
  if (!raw || typeof raw !== 'string') return '';
  const trimmed = raw.trim();
  if (!trimmed) return '';
  try {
    const base = (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin !== 'null')
      ? window.location.origin
      : 'https://localhost';
    const parsed = new URL(trimmed, base);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.href;
    }
  } catch (_) {
    return '';
  }
  return '';
}

function renderLink(url, text, title = '') {
  const href = safeHref(url);
  if (!href) return escText(text || '');
  const tAttr = title ? ` title="${escText(title)}"` : '';
  return `<a class="er-mo-link" href="${escText(href)}" target="_blank" rel="noopener noreferrer"${tAttr}>${escText(text)}</a>`;
}

function isValidDay(d) {
  return typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d);
}

function parseUtcMs(dayStr) {
  const [y, m, d] = dayStr.split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}

function formatUtcDay(ms) {
  const dt = new Date(ms);
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const d = String(dt.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addCalendarDays(dayStr, delta) {
  return formatUtcDay(parseUtcMs(dayStr) + delta * 86400000);
}

function diffCalendarDays(a, b) {
  return Math.round((parseUtcMs(b) - parseUtcMs(a)) / 86400000);
}

function isWeekendDay(dayStr) {
  const wd = new Date(parseUtcMs(dayStr)).getUTCDay();
  return wd === 0 || wd === 6;
}

function finiteNum(v) {
  if (typeof v === 'boolean' || v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(n, digits = 2) {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtSigned(n, digits = 2, suffix = '') {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${fmtNum(n, digits)}${suffix}`;
}

function binaryFloorIndex(arr, key, target) {
  let lo = 0;
  let hi = arr.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid][key] <= target) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

function detectCompanyProfile(data) {
  const comp = String(data?.company || '');
  const macroType = String(data?.drivers?.macro || '');
  const covCode = String(data?.coverage?.[0]?.code || '');
  const firstValKey = Object.keys(data?.chart?.[0]?.values || {})[0] || '';
  const code = covCode || firstValKey;

  const isPoly = macroType === 'housing' || /保利|06049|\.HK/i.test(comp + ' ' + code);
  const unitFromModes = data?.modes?.[0]?.lanes?.[0]?.items?.[0]?.unit;
  const stockUnit = unitFromModes || (isPoly || /\.HK$/i.test(code) ? '港元/股' : '元/股');

  return {
    isPoly,
    theme: isPoly ? 'poly' : 'gree',
    code: code || (isPoly ? '06049.HK' : '000651.SZ'),
    companyName: comp || (isPoly ? '保利物业' : '格力电器'),
    stockUnit,
    defaultBenchLabel: isPoly ? '恒生指数' : '沪深300',
    primaryColor: isPoly ? '#146c54' : '#0e5a8a',
    secondaryColor: '#b85d19',
  };
}

function extractStockSeries(data, code, cutoff) {
  const raw = Array.isArray(data?.chart) ? data.chart : [];
  const map = new Map();
  for (const row of raw) {
    const d = row?.date;
    if (!isValidDay(d) || (cutoff && d > cutoff)) continue;
    const vals = row?.values || {};
    let v = finiteNum(vals[code]);
    if (v === null) {
      const keys = Object.keys(vals);
      if (keys.length > 0) v = finiteNum(vals[keys[0]]);
    }
    if (v !== null && v > 0) {
      map.set(d, v);
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([date, close]) => ({ date, close }));
}

function buildWindowCalendar(stockPts, cutoff, daysReq) {
  const n = Math.max(10, Number(daysReq) || 120);
  const endDay = isValidDay(cutoff)
    ? cutoff
    : (stockPts.length ? stockPts[stockPts.length - 1].date : '2026-11-18');

  let startDay;
  if (stockPts.length >= n) {
    startDay = stockPts[stockPts.length - n].date;
  } else {
    const calSpan = Math.max(n, Math.round((n * 365) / 250));
    startDay = addCalendarDays(endDay, -calSpan);
  }
  if (startDay > endDay) startDay = endDay;

  const calendar = [];
  const totalDays = Math.min(2000, Math.max(0, diffCalendarDays(startDay, endDay)));
  for (let i = 0; i <= totalDays; i++) {
    calendar.push(addCalendarDays(startDay, i));
  }
  return { startDay, endDay, calendar, requestedDays: n };
}

function normalizeMarketSeries(rawPoints, cutoff, requireSession = false) {
  if (!Array.isArray(rawPoints)) return [];
  const byDate = new Map();
  for (const p of rawPoints) {
    const d = p?.date;
    const c = finiteNum(p?.close ?? p?.value);
    if (!isValidDay(d) || (cutoff && d > cutoff) || c === null || c <= 0) continue;
    if (requireSession && p?.session && !isValidDay(p.session)) continue;
    byDate.set(d, {
      date: d,
      close: c,
      session: isValidDay(p?.session) ? p.session : '',
    });
  }
  return Array.from(byDate.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
}

function computeNormalizedComparison(stockWin, benchWin) {
  const benchMap = new Map(benchWin.map((p) => [p.date, p.close]));
  const commonDates = [];
  for (const sp of stockWin) {
    if (benchMap.has(sp.date)) {
      commonDates.push(sp.date);
    }
  }
  if (commonDates.length === 0) {
    return {
      hasCommon: false,
      baseDate: '',
      latestCommonDate: '',
      stockBase: null,
      benchBase: null,
      stockNorm: [],
      benchNorm: [],
      spreadMap: new Map(),
      latestSpread: null,
    };
  }
  const baseDate = commonDates[0];
  const stockMap = new Map(stockWin.map((p) => [p.date, p.close]));
  const stockBase = stockMap.get(baseDate);
  const benchBase = benchMap.get(baseDate);

  const stockNorm = stockWin
    .filter((p) => p.date >= baseDate)
    .map((p) => ({
      date: p.date,
      close: p.close,
      norm: (p.close / stockBase) * 100,
    }));
  const benchNorm = benchWin
    .filter((p) => p.date >= baseDate)
    .map((p) => ({
      date: p.date,
      close: p.close,
      norm: (p.close / benchBase) * 100,
    }));

  const spreadMap = new Map();
  for (const d of commonDates) {
    const sn = (stockMap.get(d) / stockBase) * 100;
    const bn = (benchMap.get(d) / benchBase) * 100;
    spreadMap.set(d, {
      date: d,
      stockNorm: sn,
      benchNorm: bn,
      spread: sn - bn,
      stockClose: stockMap.get(d),
      benchClose: benchMap.get(d),
    });
  }
  const latestCommonDate = commonDates[commonDates.length - 1];
  const latestSpread = spreadMap.get(latestCommonDate) || null;

  return {
    hasCommon: true,
    baseDate,
    latestCommonDate,
    stockBase,
    benchBase,
    stockNorm,
    benchNorm,
    spreadMap,
    latestSpread,
  };
}

function parsePeriodInfo(periodStr) {
  const s = String(periodStr || '').trim();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) {
    const y = Number(m[1]);
    const mo = Number(m[2]);
    return { year: y, month: mo, key: `${y}-${String(mo).padStart(2, '0')}`, raw: s, kind: 'report' };
  }
  m = s.match(/^(\d{4})-(\d{2})$/);
  if (m) {
    const y = Number(m[1]);
    const mo = Number(m[2]);
    return { year: y, month: mo, key: `${y}-${String(mo).padStart(2, '0')}`, raw: s, kind: 'month' };
  }
  m = s.match(/^(\d{4})\s*Q([1-4])$/i);
  if (m) {
    const y = Number(m[1]);
    const mo = Number(m[2]) * 3;
    return { year: y, month: mo, key: `${y}-${String(mo).padStart(2, '0')}`, raw: s, kind: 'quarter' };
  }
  m = s.match(/^(\d{4})\s*H([1-2])$/i);
  if (m) {
    const y = Number(m[1]);
    const mo = Number(m[2]) * 6;
    return { year: y, month: mo, key: `${y}-${String(mo).padStart(2, '0')}`, raw: s, kind: 'half' };
  }
  m = s.match(/^(\d{4})$/);
  if (m) {
    const y = Number(m[1]);
    return { year: y, month: 12, key: `${y}-12`, raw: s, kind: 'annual' };
  }
  return { year: null, month: null, key: s, raw: s, kind: 'other' };
}

function isMacroStepGap(prevPt, currPt) {
  const p1 = parsePeriodInfo(prevPt.period);
  const p2 = parsePeriodInfo(currPt.period);
  if (p1.year !== null && p2.year !== null && p1.month !== null && p2.month !== null) {
    const diffMonths = (p2.year - p1.year) * 12 + (p2.month - p1.month);
    // NBS merges Jan-Feb: Dec (12) -> Feb (2) is 2 months, treated as continuous (not a missing gap)
    if (p1.month === 12 && p2.month === 2 && p2.year === p1.year + 1) {
      return false;
    }
    if (p1.kind === 'annual' && p2.kind === 'annual') {
      return p2.year - p1.year > 1;
    }
    if (diffMonths > 1) {
      // Allow semi-annual/quarterly macro metrics if period kind indicates it
      if ((p1.kind === 'half' || p2.kind === 'half') && diffMonths <= 6) return false;
      if ((p1.kind === 'quarter' || p2.kind === 'quarter') && diffMonths <= 3) return false;
      return true;
    }
    return false;
  }
  return diffCalendarDays(prevPt.published, currPt.published) > 75;
}

function isMicroStepGap(prevPt, currPt, cadenceMonths) {
  const p1 = parsePeriodInfo(prevPt.period);
  const p2 = parsePeriodInfo(currPt.period);
  const cad = Number(cadenceMonths) || 3;
  if (p1.year !== null && p2.year !== null && p1.month !== null && p2.month !== null) {
    const diffMonths = (p2.year - p1.year) * 12 + (p2.month - p1.month);
    return diffMonths > cad + 1;
  }
  const maxDays = cad >= 12 ? 410 : (cad >= 6 ? 225 : 135);
  return diffCalendarDays(prevPt.published, currPt.published) > maxDays;
}

function preparePublishedSeries(rawPoints, cutoff, gapChecker) {
  if (!Array.isArray(rawPoints)) return [];
  const valid = [];
  for (const p of rawPoints) {
    const pub = isValidDay(p?.published) ? p.published : (isValidDay(p?.date) ? p.date : '');
    const val = finiteNum(p?.value);
    if (!pub || (cutoff && pub > cutoff) || val === null) continue;
    valid.push({
      period: String(p?.period || pub),
      published: pub,
      value: val,
      url: p?.url || '',
      source: p?.source || '',
      page: p?.page ?? '',
      metric: p?.metric || '',
    });
  }
  valid.sort((a, b) => {
    if (a.published !== b.published) return a.published < b.published ? -1 : 1;
    return a.period < b.period ? -1 : (a.period > b.period ? 1 : 0);
  });

  // Deduplicate same published date by keeping the latest period disclosed that day, while preserving history for YoY/QoQ
  const enriched = valid.map((item, idx) => {
    const prev = idx > 0 ? valid[idx - 1] : null;
    const isGap = prev ? Boolean(gapChecker(prev, item)) : false;

    const pInfo = parsePeriodInfo(item.period);
    let yoy = null;
    if (pInfo.year !== null && pInfo.month !== null) {
      const targetYear = pInfo.year - 1;
      for (let j = idx - 1; j >= 0; j--) {
        const cand = parsePeriodInfo(valid[j].period);
        if (cand.year === targetYear && cand.month === pInfo.month) {
          const baseVal = valid[j].value;
          const diff = item.value - baseVal;
          const pct = Math.abs(baseVal) > 1e-9 ? (diff / Math.abs(baseVal)) * 100 : null;
          yoy = { basePeriod: valid[j].period, baseValue: baseVal, diff, pct };
          break;
        }
      }
    }
    let qoq = null;
    if (prev) {
      const diff = item.value - prev.value;
      const pct = Math.abs(prev.value) > 1e-9 ? (diff / Math.abs(prev.value)) * 100 : null;
      qoq = { prevPeriod: prev.period, prevValue: prev.value, diff, pct, isGap };
    }
    return { ...item, isGapFromPrev: isGap, qoq, yoy };
  });

  return enriched;
}

function activeDisclosedAt(points, targetDay) {
  if (!points || !points.length) return null;
  const idx = binaryFloorIndex(points, 'published', targetDay);
  return idx >= 0 ? { point: points[idx], index: idx } : null;
}

function buildStepGeometry(points, startDay, endDay, xOf, yOf) {
  if (!points || !points.length) return { segments: [], dots: [], carryLeft: null };
  const uptoEnd = points.filter((p) => p.published <= endDay);
  if (!uptoEnd.length) return { segments: [], dots: [], carryLeft: null };

  const preIdx = binaryFloorIndex(uptoEnd, 'published', startDay);
  let carryPoint = null;
  let firstInWinIdx = 0;

  if (preIdx >= 0) {
    carryPoint = uptoEnd[preIdx];
    firstInWinIdx = preIdx + 1;
    // If multiple points published on exact startDay, carry is the last one on startDay
    if (carryPoint.published === startDay) {
      carryPoint = null;
      firstInWinIdx = preIdx;
      while (firstInWinIdx > 0 && uptoEnd[firstInWinIdx - 1].published === startDay) {
        firstInWinIdx--;
      }
      if (firstInWinIdx > 0) {
        carryPoint = uptoEnd[firstInWinIdx - 1];
      }
    }
  }

  const inWin = uptoEnd.slice(firstInWinIdx);
  const segments = [];
  const dots = [];

  let currVal = carryPoint ? carryPoint.value : null;
  let currX = xOf(startDay);

  for (const pt of inWin) {
    const px = xOf(pt.published);
    const py = yOf(pt.value);
    if (currVal !== null) {
      const prevY = yOf(currVal);
      segments.push({
        x1: currX,
        y1: prevY,
        x2: px,
        y2: prevY,
        dashed: pt.isGapFromPrev,
      });
      segments.push({
        x1: px,
        y1: prevY,
        x2: px,
        y2: py,
        dashed: pt.isGapFromPrev,
      });
    }
    dots.push({ x: px, y: py, point: pt });
    currVal = pt.value;
    currX = px;
  }

  if (currVal !== null) {
    const endX = xOf(endDay);
    const py = yOf(currVal);
    if (endX > currX) {
      segments.push({
        x1: currX,
        y1: py,
        x2: endX,
        y2: py,
        dashed: false,
      });
    }
  }

  return {
    segments,
    dots,
    carryLeft: carryPoint ? { y: yOf(carryPoint.value), point: carryPoint } : null,
  };
}

function buildDailyLineSegments(points, calendarIndexMap, xOf, yOf, valueKey = 'close', allowBridgeWeekend = true) {
  if (!points || !points.length) return { paths: [], singleDots: [], pointLookup: new Map() };
  const pointLookup = new Map();
  for (const p of points) {
    if (calendarIndexMap.has(p.date)) {
      pointLookup.set(p.date, p);
    }
  }

  const winPts = points.filter((p) => calendarIndexMap.has(p.date));
  if (!winPts.length) return { paths: [], singleDots: [], pointLookup };

  const runs = [];
  let currentRun = [winPts[0]];

  for (let i = 1; i < winPts.length; i++) {
    const prev = winPts[i - 1];
    const curr = winPts[i];
    const dPrev = prev.date;
    const dCurr = curr.date;
    const gapDays = diffCalendarDays(dPrev, dCurr);

    let hasMissingWeekday = false;
    if (gapDays > 1) {
      if (!allowBridgeWeekend) {
        hasMissingWeekday = true;
      } else {
        for (let step = 1; step < gapDays; step++) {
          const midDay = addCalendarDays(dPrev, step);
          if (!isWeekendDay(midDay)) {
            hasMissingWeekday = true;
            break;
          }
        }
      }
    }

    if (hasMissingWeekday) {
      runs.push(currentRun);
      currentRun = [curr];
    } else {
      currentRun.push(curr);
    }
  }
  runs.push(currentRun);

  const paths = [];
  const singleDots = [];
  for (const run of runs) {
    if (run.length === 1) {
      const p = run[0];
      singleDots.push({ x: xOf(p.date), y: yOf(p[valueKey]), point: p });
    } else {
      const dStr = run
        .map((p, i) => `${i === 0 ? 'M' : 'L'}${xOf(p.date).toFixed(2)},${yOf(p[valueKey]).toFixed(2)}`)
        .join(' ');
      paths.push(dStr);
    }
  }
  return { paths, singleDots, pointLookup };
}

function computeNiceScale(values, padRatio = 0.12) {
  const clean = values.filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (!clean.length) return { min: 0, max: 100, ticks: [0, 50, 100] };
  let min = Math.min(...clean);
  let max = Math.max(...clean);
  if (Math.abs(max - min) < 1e-6) {
    const delta = Math.abs(max) > 1e-4 ? Math.abs(max) * 0.05 : 1;
    min -= delta;
    max += delta;
  } else {
    const span = max - min;
    min -= span * padRatio;
    max += span * padRatio;
  }
  const mid = (min + max) / 2;
  return { min, max, ticks: [max, mid, min] };
}

function pickAxisDates(calendar) {
  if (!calendar.length) return [];
  if (calendar.length <= 5) return [calendar[0], calendar[calendar.length - 1]];
  const idxs = [
    0,
    Math.round((calendar.length - 1) * 0.25),
    Math.round((calendar.length - 1) * 0.5),
    Math.round((calendar.length - 1) * 0.75),
    calendar.length - 1,
  ];
  const uniq = Array.from(new Set(idxs));
  return uniq.map((i) => calendar[i]);
}

function readableMacroMetric(rawMetric, fallbackLabel, isPoly) {
  const m = String(rawMetric || '').trim();
  if (m && /[\u4e00-\u9fff]/.test(m) && !/行业零售\/产量/.test(m)) {
    return m;
  }
  if (fallbackLabel && /[\u4e00-\u9fff]/.test(fallbackLabel) && !/^(appliances|housing)$/i.test(fallbackLabel.trim())) {
    return fallbackLabel;
  }
  return isPoly ? '国家统计局全国房地产竣工面积同比' : '国家统计局家电和音像零售';
}

function formatChangeSummary(activeItem, unit = '', cadence = 0) {
  if (!activeItem) return '窗口截止前尚无已披露记录';
  const isRateSeries = String(unit).trim() === '%';
  const parts = [];
  if (isRateSeries) {
    if (activeItem.qoq) {
      const tag = activeItem.qoq.isGap ? '跨期较前值' : '较上期';
      parts.push(`${tag} ${fmtSigned(activeItem.qoq.diff, 2, ' 个百分点')}`);
    }
    if (activeItem.yoy) {
      parts.push(`较上年同期 ${fmtSigned(activeItem.yoy.diff, 2, ' 个百分点')}`);
    }
    return parts.length ? parts.join(' ｜ ') : '首期统计记录（无更早对比期）';
  }
  const uTxt = unit ? ` ${unit}` : '';
  if (activeItem.yoy) {
    const yoyTag = Number(cadence) === 3 ? '同季同比' : '较上年同期';
    const pctStr = activeItem.yoy.pct !== null ? ` (${fmtSigned(activeItem.yoy.pct, 1, '%')})` : '';
    parts.push(`${yoyTag} ${fmtSigned(activeItem.yoy.diff, 2)}${uTxt}${pctStr}`);
  }
  if (activeItem.qoq) {
    const qoqTag = activeItem.qoq.isGap ? `跨期较前值(${activeItem.qoq.prevPeriod})` : `较上期(${activeItem.qoq.prevPeriod})`;
    const pctStr = activeItem.qoq.pct !== null ? ` (${fmtSigned(activeItem.qoq.pct, 1, '%')})` : '';
    parts.push(`${qoqTag} ${fmtSigned(activeItem.qoq.diff, 2)}${uTxt}${pctStr}`);
  }
  return parts.length ? parts.join(' ｜ ') : '首期披露记录（无更早对比期）';
}

// Gemini's dated case review, checked against the original disclosures and closing prices.
const OCT_NOV_MARKET_REVIEW = {
  "000651.SZ": [
    {
      "date": "2026-10-28",
      "kind": "公告",
      "title": "单季业绩承压后披露拟派息与拟增持，时间上与低位反弹吻合",
      "text": "10月27日三季报显示第三季度单季营收同比降7.97%、归母净利降43.31%（前三季营收降8.10%、归母降19.51%），当日收于窗口低点36.60元；同日披露每10股拟派10元预案，次日京海互联公告拟增持6至12亿元。28日股价反弹1.91%，股东回报预期与低位企稳时间吻合，有个股层面的支撑线索，但各项贡献无法单独识别。",
      "sources": [
        {
          "label": "格力电器2026年第三季度报告（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-27/1225627217.PDF"
        },
        {
          "label": "格力电器2026年中期利润分配预案公告（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-27/1225627214.PDF"
        },
        {
          "label": "关于股东京海互联增持公司股份计划的公告（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-28/1225630983.PDF"
        },
        {
          "label": "格力电器A股历史行情日线（英为财情）",
          "url": "https://cn.investing.com/equities/gree-electric-a-historical-data"
        }
      ]
    },
    {
      "date": "2026-11-03",
      "kind": "公告",
      "title": "10月末已执行回购增量落地，与起步阶段反弹时点重合",
      "text": "10月29日公告累计已回购23.25亿元，11月3日进一步披露截至10月底累计已回购24.04亿元，显示10月末存在约0.79亿元实际已执行回购买盘（区别于拟派息与拟增持计划）；期间股价于10月30日涨2.42%、11月3日涨1.74%。实际回购与起步反弹在时间上吻合，提供个股层面的支撑线索，但无法拆分回购与外部回报预期的各自贡献。",
      "sources": [
        {
          "label": "关于回购公司股份比例达到1%的进展公告（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-29/1225636209.PDF"
        },
        {
          "label": "关于股份回购进展情况的公告（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-11-03/1225653096.PDF"
        },
        {
          "label": "格力电器A股历史行情日线（英为财情）",
          "url": "https://cn.investing.com/equities/gree-electric-a-historical-data"
        }
      ]
    },
    {
      "date": "2026-11-13",
      "kind": "市场",
      "title": "电子通信大单流出日白电龙头走强，录得窗口最大单日涨幅",
      "text": "11月13日格力涨2.75%创本窗口最大单日涨幅，美的（+2.91%）、海尔（+2.17%）同涨，而沪深300跌0.68%、科创50跌2.30%、创业板指跌3.32%、通信ETF（515880）跌5.64%。按大单及超大单已成交口径估算，当日电子净流出236.57亿元、通信净流出94.13亿元，家电净流入1.85亿元，其中格力净流入3.22亿元。",
      "sources": [
        {
          "label": "2026年11月13日A股行业主力资金流向统计",
          "url": "https://www.yyqyx.com/moneyflow/2026-11-13"
        },
        {
          "label": "格力电器近期主力资金流向明细",
          "url": "https://www.yyqyx.com/s/000651.SZ"
        },
        {
          "label": "格力电器A股历史行情日线（英为财情）",
          "url": "https://cn.investing.com/equities/gree-electric-a-historical-data"
        },
        {
          "label": "美的集团行情页（腾讯证券）",
          "url": "https://gu.qq.com/sz000333/gp"
        },
        {
          "label": "海尔智家行情页（腾讯证券）",
          "url": "https://gu.qq.com/sh600690/gp"
        }
      ]
    },
    {
      "date": "2026-11-17",
      "kind": "行业",
      "title": "电子通信续流出叠加10月家电零售单月转正，支撑后段情绪",
      "text": "11月16日同口径估算电子净流出252.11亿元、通信净流出73.94亿元、家电净流入1.29亿元；同日统计局公布10月家电和音像器材零售单月同比+2.5%（1—10月累计-4.2%），改善后段行业预期但解释不了11月13日的提前加速。11月17日半导体设备与家电同强而通信仍弱，显示科技内部亦有分化。",
      "sources": [
        {
          "label": "2026年11月16日A股行业主力资金流向统计",
          "url": "https://www.yyqyx.com/moneyflow/2026-11-16"
        },
        {
          "label": "国家统计局：2026年1—10月份社会消费品零售总额主要数据",
          "url": "https://www.stats.gov.cn/sj/zxfb/202611/t20261116_1965839.html"
        },
        {
          "label": "粤开证券2026年11月17日市场复盘报告",
          "url": "https://www.ykzq.com/products/download-new/rpt/2026/11/17/620eb127d22a40e9ab8bc754bcdadad4.pdf"
        }
      ]
    },
    {
      "date": "2026-11-18",
      "kind": "研究判断",
      "title": "11月中旬科技与白电的轮动最明显，仍无法追踪同一批资金",
      "text": "三季报盈利并未反转，期间逆势走强与股东回报预期以及11月13日、16日的风格轮动更吻合。全段格力涨9.75%，美的（+11.67%）、海尔（+14.78%）同强，沪深300跌3.12%。盘面支持市场持仓相对强弱切换的推断，但格力16至18日大单估算分别为-1,319万、-7,034万和-1.26亿元而股价续涨，账户级资金直接迁移未经证实，各因素对涨幅的贡献亦无法量化。",
      "sources": [
        {
          "label": "格力三季报",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-27/1225627217.PDF"
        },
        {
          "label": "2026年11月13日A股行业主力资金流向统计",
          "url": "https://www.yyqyx.com/moneyflow/2026-11-13"
        },
        {
          "label": "2026年11月16日A股行业主力资金流向统计",
          "url": "https://www.yyqyx.com/moneyflow/2026-11-16"
        },
        {
          "label": "格力电器近期主力资金流向明细",
          "url": "https://www.yyqyx.com/s/000651.SZ"
        },
        {
          "label": "美的集团行情页（腾讯证券）",
          "url": "https://gu.qq.com/sz000333/gp"
        },
        {
          "label": "海尔智家行情页（腾讯证券）",
          "url": "https://gu.qq.com/sh600690/gp"
        }
      ]
    }
  ],
  "06049.HK": [
    {
      "date": "2026-10-22",
      "kind": "市场",
      "title": "早段随港股风险资产普跌，录得窗口内最深单日回撤",
      "text": "10月22日保利物业单日跌2.38%为本窗口最大跌幅，同日恒生指数跌3.03%、恒生科技指数跌5.03%、同业中海物业跌2.60%。窗口初段的价格下台阶与香港风险资产广泛回撤及物管同业同跌高度吻合，并非单纯窄幅震荡或个股孤立利空。",
      "sources": [
        {
          "label": "保利物业历史收盘",
          "url": "https://cn.investing.com/equities/poly-property-development-co-ltd-historical-data"
        },
        {
          "label": "10月22日港股市场复盘报道（英为财情）",
          "url": "https://hk.investing.com/news/stock-market-news/article-1711523"
        }
      ]
    },
    {
      "date": "2026-11-12",
      "kind": "行业",
      "title": "关联方10月签约降幅收窄但仍承压，公开当日随大盘偏弱",
      "text": "控股股东保利发展11月11日盘后公开、12日版面刊载简报，10月签约金额同比降15.70%（较9月单月-21.13%降幅收窄）；11月12日保利物业跌1.06%、恒指跌1.26%。关联房企签约仅反映外部交付压力背景，不等同保利物业自身订单或回款指标。",
      "sources": [
        {
          "label": "保利发展信息披露列表（巨潮资讯）",
          "url": "https://www.cninfo.com.cn/new/disclosure/stock?orgId=9900000161&stockCode=600048"
        },
        {
          "label": "保利发展2026年10月份销售情况简报（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-11-12/1225667691.PDF"
        },
        {
          "label": "保利发展2026年9月份销售情况简报（巨潮资讯）",
          "url": "https://static.cninfo.com.cn/finalpage/2026-10-17/1225608088.PDF"
        },
        {
          "label": "保利物业历史收盘",
          "url": "https://cn.investing.com/equities/poly-property-development-co-ltd-historical-data"
        }
      ]
    },
    {
      "date": "2026-11-13",
      "kind": "公告",
      "title": "随同业收跌后盘后披露关连交易与车位续签，部分事项尚须审批",
      "text": "11月13日保利物业收跌0.91%，同日华润万象生活跌3.34%、中海物业跌1.23%、恒指跌1.55%；当日盘后港交所披露2027—2029年度持续关连交易及车位代理续签框架协议，部分事项尚须独立股东批准，第一期车位代理保证金拟沿用每年最高余额30亿元的上限。",
      "sources": [
        {
          "label": "保利物业：持续关连交易2027至2029年度框架协议（披露易）",
          "url": "https://www.hkexnews.hk/listedco/listconews/sehk/2026/1113/2026111301417_c.pdf"
        },
        {
          "label": "保利物业：续签车位代理框架协议公告（披露易）",
          "url": "https://www.hkexnews.hk/listedco/listconews/sehk/2026/1113/2026111301475_c.pdf"
        },
        {
          "label": "保利物业历史收盘",
          "url": "https://cn.investing.com/equities/poly-property-development-co-ltd-historical-data"
        },
        {
          "label": "中海物业港股历史行情日线（英为财情）",
          "url": "https://cn.investing.com/equities/china-overseas-property-holdings-historical-data"
        },
        {
          "label": "华润万象生活历史收盘",
          "url": "https://cn.investing.com/equities/china-resources-mixc-lifestyle-serv-historical-data"
        }
      ]
    },
    {
      "date": "2026-11-16",
      "kind": "行业",
      "title": "全国前10月住宅竣工与销售延续负增长，公布当日股价随市微升",
      "text": "11月16日统计局公布1—10月全国住宅竣工面积累计同比降27.9%、新建商品房销售额降14.3%，印证地产竣工及外部结算环境依然偏弱；但当日保利物业收涨0.38%（恒指涨0.49%），该宏观数据仅为行业压力背景而非股价下跌触发点。",
      "sources": [
        {
          "label": "国家统计局：2026年1—10月份全国房地产市场基本情况",
          "url": "https://www.stats.gov.cn/sj/zxfb/202611/t20261116_1965840.html"
        },
        {
          "label": "保利物业历史收盘",
          "url": "https://cn.investing.com/equities/poly-property-development-co-ltd-historical-data"
        }
      ]
    },
    {
      "date": "2026-11-18",
      "kind": "研究判断",
      "title": "早段随港股与同业回落，盘后续约公告晚于主要跌势",
      "text": "10月21日至11月18日保利物业跌1.86%，与恒指（-1.51%）、华润万象生活（-2.00%）、中海物业（-0.61%）同处港股与地产弱背景压力区间（同期DXY按港可用日涨1.73%，具体贡献不明）。关连交易框架在大部分下跌后才披露，且11月17日保利涨1.91%（恒指跌1.03%），未印证公告构成负面触发；11月9日保利跌1.76%时中海物业亦跌1.49%（恒指-0.13%），仍未查清是否存在其他个股独立驱动。",
      "sources": [
        {
          "label": "11月17日港股市场行情复盘（华盛通）",
          "url": "https://www.hstong.com/news/detail/26111716115058781"
        },
        {
          "label": "中海物业港股历史行情日线（英为财情）",
          "url": "https://cn.investing.com/equities/china-overseas-property-holdings-historical-data"
        },
        {
          "label": "保利物业历史收盘",
          "url": "https://cn.investing.com/equities/poly-property-development-co-ltd-historical-data"
        },
        {
          "label": "国家统计局：2026年1—10月份全国房地产市场基本情况",
          "url": "https://www.stats.gov.cn/sj/zxfb/202611/t20261116_1965840.html"
        },
        {
          "label": "华润万象生活历史收盘",
          "url": "https://cn.investing.com/equities/china-resources-mixc-lifestyle-serv-historical-data"
        },
        {
          "label": "ICE DXY 历史收盘",
          "url": "https://finance.yahoo.com/quote/DX-Y.NYB/history/"
        }
      ]
    }
  ]
};

function marketReviewNotes(code, startDay, asOf) {
  const end = '2026-11-18';
  if (startDay > end) return [];
  return (OCT_NOV_MARKET_REVIEW[code] || []).filter(note => note.date <= asOf);
}

function updateMarketReview(host, model, asOf) {
  const box = host.querySelector('[data-driver-attribution]');
  if (!box) return;
  const notes = marketReviewNotes(model.profile.code, model.startDay, asOf);
  box.hidden = !notes.length;
  if (!notes.length || box.dataset.evidenceCount === String(notes.length)) return;
  const expanded = box.querySelector('details')?.open;
  const latest = notes.at(-1);
  const renderNote = note => `<article>
    <div class="er-mo-case-meta"><time datetime="${escText(note.date)}">${escText(note.date)}</time> · ${escText(note.kind)}</div>
    <strong>${escText(note.title)}</strong>
    <p>${escText(note.text)}</p>
    <div class="er-mo-case-links">${note.sources.map(src => renderLink(src.url, src.label)).join(' · ')}</div>
  </article>`;
  box.innerHTML = `<h4>行情归因 · 2026-10-21 至 ${latest.date}</h4>${renderNote(latest)}
    ${notes.length > 1 ? `<details ${expanded ? 'open' : ''}><summary>查看关键日期与原件</summary>
      ${notes.slice(0, -1).map(renderNote).join('')}</details>` : ''}`;
  box.dataset.evidenceCount = String(notes.length);
}

function expInjectStyles() {
  if (typeof document === 'undefined' || document.getElementById('er-mo-exp-style')) return;
  const st = document.createElement('style');
  st.id = 'er-mo-exp-style';
  st.textContent = `
    .er-mo-wb .er-mo-exp{grid-column:1/-1;display:flex;flex-direction:column;gap:8px;font-size:12.5px;color:var(--wb-ink)}
    .er-mo-wb .er-mo-case{margin:8px 0 12px;padding:10px 12px;border:1px solid #dce5e2;background:var(--wb-panel);font-size:13px;line-height:1.6}
    .er-mo-case h4{margin:0 0 6px;font-size:14px}
    .er-mo-case p{margin:2px 0}
    .er-mo-case-meta,.er-mo-case-links{font-size:12px;color:var(--wb-ink-sec)}
    .er-mo-case details{margin-top:6px}
    .er-mo-case summary{cursor:pointer;font-weight:600}
    .er-mo-case details article{margin-top:9px;padding-top:7px;border-top:1px solid #dce5e2}
    .er-mo-exp-lead{display:flex;flex-direction:column;gap:5px;line-height:1.58}
    .er-mo-exp-lead p{margin:0}
    .er-mo-exp-k{display:inline-block;font-size:11px;font-weight:700;padding:1px 6px;margin-right:6px;border-radius:3px;background:#e8eef6;color:#1e3a5f}
    .er-mo-wb[data-theme="poly"] .er-mo-exp-k{background:#e6f2ee;color:#134e3e}
    .er-mo-exp-tbl{width:100%;border-collapse:collapse;font-size:11.5px;background:var(--wb-subtle);border:1px solid #e4e8ef}
    .er-mo-exp-tbl th,.er-mo-exp-tbl td{padding:4px 8px;border-bottom:1px solid #e4e8ef;text-align:left}
    .er-mo-exp-tbl th{font-weight:600;color:var(--wb-ink-sec);background:#eef1f6}
    .er-mo-exp-tbl tr:last-child td{border-bottom:none}
    .er-mo-exp-foot{font-size:11.5px;color:var(--wb-ink-sec);background:var(--wb-subtle);border:1px solid #e4e8ef;border-radius:3px;padding:5px 8px;line-height:1.5}
  `;
  document.head.appendChild(st);
}

function expMatchDxy(dxySeries, targetDay) {
  const idx = binaryFloorIndex(dxySeries, 'date', targetDay);
  if (idx < 0) return { ok: false };
  const pt = dxySeries[idx];
  const lag = diffCalendarDays(pt.date, targetDay);
  return lag >= 0 && lag <= 5 ? { ok: true, date: pt.date, close: pt.close, lag } : { ok: false };
}

function expEvalSpan(name, p0, p1, dxySeries) {
  const stockPct = ((p1.stock / p0.stock) - 1) * 100;
  const hasBench = p0.bench > 0 && p1.bench > 0;
  const benchPct = hasBench ? ((p1.bench / p0.bench) - 1) * 100 : null;
  const diffPp = hasBench ? stockPct - benchPct : null;
  const d0 = expMatchDxy(dxySeries, p0.date);
  const d1 = expMatchDxy(dxySeries, p1.date);
  const dxy = (d0.ok && d1.ok && d0.date < d1.date)
    ? { ok: true, pct: ((d1.close / d0.close) - 1) * 100, d0: d0.date, d1: d1.date, shifted: Boolean(d0.lag || d1.lag) }
    : { ok: false, note: (!d0.ok || !d1.ok) ? '端点缺近期可用值，不作比较' : `港可用日均为 ${d0.date}，无新收盘可比` };
  return { name, start: p0.date, end: p1.date, stockPct, benchPct, diffPp, dxy };
}

function expDir(v) {
  if (v === null || v === undefined || !Number.isFinite(v) || fmtNum(Math.abs(v), 2) === '0.00') return 0;
  return v > 0 ? 1 : -1;
}

function expFmtPct(v, suffix = '%') {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return fmtNum(Math.abs(v), 2) === '0.00' ? `0.00${suffix}` : fmtSigned(v, 2, suffix);
}

function expSpanRelation(aName, aPct, bName, bPct) {
  const da = expDir(aPct);
  const db = expDir(bPct);
  if (da > 0 && db > 0) return '区间内同涨';
  if (da < 0 && db < 0) return '区间内同跌';
  if (da * db < 0) return '区间内反向';
  if (da === 0 && db === 0) return '区间内均持平';
  return da === 0
    ? `区间内${aName}持平、${bName}${db > 0 ? '上涨' : '下跌'}`
    : `区间内${aName}${da > 0 ? '上涨' : '下跌'}、${bName}持平`;
}

function expLegCompare(compName, sPct, benchName, bPct) {
  const ds = expDir(sPct);
  const db = expDir(bPct);
  if (ds > 0 && db > 0) {
    if (fmtNum(Math.abs(sPct - bPct), 2) === '0.00') return '两者涨幅持平';
    return sPct > bPct ? `${compName}涨幅较大` : `${benchName}涨幅较大`;
  }
  if (ds < 0 && db < 0) {
    if (fmtNum(Math.abs(sPct - bPct), 2) === '0.00') return '两者跌幅持平';
    return sPct < bPct ? `${compName}跌幅较大` : `${benchName}跌幅较大`;
  }
  if (ds > 0 && db < 0) return `${compName}上涨、${benchName}下跌`;
  if (ds < 0 && db > 0) return `${compName}下跌、${benchName}上涨`;
  if (ds === 0 && db === 0) return '两者均持平';
  return ds === 0
    ? `${compName}持平、${benchName}${db > 0 ? '上涨' : '下跌'}`
    : `${compName}${ds > 0 ? '上涨' : '下跌'}、${benchName}持平`;
}

function expDxyLegSummary(dxyLegs) {
  const n = dxyLegs.length;
  const head = n === 2
    ? `展示的${escText(dxyLegs[0].name)}与${escText(dxyLegs[1].name)}这两段`
    : `展示的${dxyLegs.map((l) => escText(l.name)).join('、')}三段`;
  const rels = dxyLegs.map((l) => {
    const ds = expDir(l.stockPct);
    const dd = expDir(l.dxy.pct);
    if (ds === 0 || dd === 0) return 'flat';
    return ds === dd ? 'same' : 'opp';
  });
  const sameCnt = rels.filter((r) => r === 'same').length;
  const oppCnt = rels.filter((r) => r === 'opp').length;
  const flatCnt = rels.filter((r) => r === 'flat').length;
  if (flatCnt === 0) {
    if (sameCnt === n) return `${head}均同向`;
    if (oppCnt === n) return `${head}均反向`;
    const detail = dxyLegs.map((l, i) => `${escText(l.name)}${rels[i] === 'same' ? '同向' : '反向'}`).join('、');
    if (n === 2) return `${head}一同向一反向（${detail}）`;
    const cn = ['零', '一', '两', '三'];
    return `${head}${cn[sameCnt]}同向${cn[oppCnt]}反向（${detail}）`;
  }
  const detail = dxyLegs.map((l, i) => {
    if (rels[i] === 'same') return `${escText(l.name)}同向`;
    if (rels[i] === 'opp') return `${escText(l.name)}反向`;
    const ds = expDir(l.stockPct);
    const dd = expDir(l.dxy.pct);
    if (ds === 0 && dd === 0) return `${escText(l.name)}均持平`;
    return ds === 0 ? `${escText(l.name)}股价持平` : `${escText(l.name)} DXY 持平`;
  }).join('、');
  return `${head}表现为${detail}（0.00% 按持平计）`;
}

function expTimingLabel(pubDay, winStart, winEnd, legs) {
  if (pubDay < winStart) return '早于区间首日，属期初已知';
  if (pubDay > winEnd) return `晚于区间最后收盘（${winEnd}）`;
  if (pubDay === winStart) return '与区间首日同日公开';
  if (pubDay === winEnd) return '与区间末日同日公开';
  const hit = legs.find((l) => pubDay >= l.start && pubDay <= l.end);
  return hit ? `处于${hit.name}期间` : '处于区间起止日之间';
}

function buildClueCardsHtml(model, cursorDay) {
  expInjectStyles();
  const { profile, benchMeta, macroMeta, macroSeries, microSeriesList, dxySeries } = model;
  const compName = escText(profile.companyName);
  const benchName = escText(benchMeta.label);
  const stockPts = model.stockWin.filter((p) => p.date <= cursorDay).map((p) => ({ date: p.date, stock: p.close, bench: model.benchMap.get(p.date) || null }));
  const common = stockPts.filter((p) => p.bench !== null);

  const microByDate = new Map();
  microSeriesList.forEach((s) => {
    s.points.filter((pt) => pt.published <= cursorDay).forEach((pt) => {
      const key = `${pt.published}|${pt.period}`;
      if (!microByDate.has(key)) microByDate.set(key, { published: pt.published, period: pt.period, url: pt.url, items: [] });
      microByDate.get(key).items.push(`${s.label} ${fmtNum(pt.value, 2)}${s.unit || '亿元'}`);
    });
  });
  const microEvents = Array.from(microByDate.values()).sort((a, b) => (a.published < b.published ? -1 : 1));
  const macroEvents = macroSeries.filter((pt) => pt.published <= cursorDay);

  if (stockPts.length < 2) {
    const lastM = microEvents[microEvents.length - 1];
    const baseFiling = lastM ? `截至该日最近已公开财报为报告期 ${escText(lastM.period)}（${escText(lastM.published)} 公开：${escText(lastM.items.join('、'))}）。` : '截至该日尚无已公开财报记录。';
    return `<div class="er-mo-exp" data-driver-explanation><div class="er-mo-exp-lead"><p><span class="er-mo-exp-k">窗口边界</span>当前选中日 ${escText(cursorDay)} 接近窗口起点，区间内有效交易日不足 2 日，向右移动光标即可复算价格区间与市场基准对照。${baseFiling}</p></div></div>`;
  }

  const legs = [];
  let splitRule = '';
  if (common.length >= 9) {
    const n = common.length - 1;
    const cuts = [0, Math.floor(n / 3), Math.floor((n * 2) / 3), n];
    ['前段', '中段', '近段'].forEach((nm, i) => legs.push(expEvalSpan(nm, common[cuts[i]], common[cuts[i + 1]], dxySeries)));
    splitRule = '按共同交易日三等分';
  } else if (common.length >= 4) {
    const n = common.length - 1;
    const mid = Math.floor(n / 2);
    legs.push(expEvalSpan('前半段', common[0], common[mid], dxySeries), expEvalSpan('后半段', common[mid], common[n], dxySeries));
    splitRule = '按共同交易日二等分';
  }

  const refSpan = common.length >= 2 ? expEvalSpan('全窗口', common[0], common[common.length - 1], dxySeries) : expEvalSpan('当前窗口', stockPts[0], stockPts[stockPts.length - 1], dxySeries);
  let p1 = '';
  if (!macroMeta.loaded) {
    p1 = `${escText(refSpan.start)} 至 ${escText(refSpan.end)} 期间，${compName}变动 <strong>${expFmtPct(refSpan.stockPct)}</strong>；${benchName}与 DXY 正在同步。`;
  } else if (common.length < 2) {
    p1 = `${escText(refSpan.start)} 至 ${escText(refSpan.end)} 期间，${compName}变动 <strong>${expFmtPct(refSpan.stockPct)}</strong>；与${benchName}共同交易日不足 2 日，暂不计算区间差。`;
  } else {
    const relTone = expSpanRelation(compName, refSpan.stockPct, benchName, refSpan.benchPct);
    const maxLeg = legs.length ? legs.reduce((best, cur) => (Math.abs(cur.diffPp) > Math.abs(best.diffPp) ? cur : best), legs[0]) : null;
    const legDetail = maxLeg
      ? `；区间差最大的一段是<strong>${escText(maxLeg.name)}（${escText(maxLeg.start)} 至 ${escText(maxLeg.end)}）</strong>，${expLegCompare(compName, maxLeg.stockPct, benchName, maxLeg.benchPct)}，相差 <strong>${expFmtPct(maxLeg.diffPp, ' 个百分点')}</strong>`
      : '';
    p1 = `共同交易日 ${escText(refSpan.start)} 至 ${escText(refSpan.end)}（${common.length} 日）${relTone}，${compName}与${benchName}涨跌幅差 <strong>${expFmtPct(refSpan.diffPp, ' 个百分点')}</strong>${legDetail}。`;
  }

  let p2 = '';
  const dxyLegs = legs.filter((l) => l.dxy.ok);
  if (!macroMeta.loaded) {
    p2 = 'ICE 美元指数（DXY）日线载入中。';
  } else if (!refSpan.dxy.ok && dxyLegs.length < 2) {
    p2 = `同期 DXY ${escText(refSpan.dxy.note)}，暂不作同反向比较。`;
  } else if (!refSpan.dxy.ok) {
    p2 = `全段端点缺近期 DXY，按有效分段（港可用日 ${escText(dxyLegs[0].dxy.d0)} 至 ${escText(dxyLegs[dxyLegs.length - 1].dxy.d1)}）观察：${expDxyLegSummary(dxyLegs)}。`;
  } else {
    const fullRel = expSpanRelation(compName, refSpan.stockPct, 'DXY', refSpan.dxy.pct);
    const segPart = dxyLegs.length >= 2 ? `${expDxyLegSummary(dxyLegs)}` : '当前可比分段不足两段，不下多段方向稳定性结论';
    p2 = `全段 DXY（港可用日 ${escText(refSpan.dxy.d0)} 至 ${escText(refSpan.dxy.d1)}${refSpan.dxy.shifted ? '，缺值取前一可用日' : ''}）变动 <strong>${expFmtPct(refSpan.dxy.pct)}</strong>，${fullRel}；${segPart}。`;
  }

  const winStart = refSpan.start;
  const winEnd = refSpan.end;
  const pickMicro = microEvents.length ? microEvents[microEvents.length - 1] : null;
  const inSpanMicro = microEvents.filter((e) => e.published >= winStart && e.published <= winEnd);
  const pickMacro = macroEvents.length ? macroEvents[macroEvents.length - 1] : null;
  const macroTitle = readableMacroMetric(pickMacro?.metric, macroMeta.label, profile.isPoly);

  const clauses = [];
  if (pickMicro) {
    const mTiming = expTimingLabel(pickMicro.published, winStart, winEnd, legs);
    const mLink = pickMicro.url ? ` ${renderLink(pickMicro.url, '财报原件')}` : '';
    const earlierNote = (inSpanMicro.length > 1 && inSpanMicro[0].period !== pickMicro.period)
      ? `（区间内另有 ${escText(inSpanMicro[0].period)} 期于 ${escText(inSpanMicro[0].published)} 公开）`
      : '';
    clauses.push(`已收录最新公司财报为 ${escText(pickMicro.period)} 期（${escText(pickMicro.items.join('、'))}），${escText(pickMicro.published)} 公开（${escText(mTiming)}）${earlierNote}${mLink}`);
  } else {
    clauses.push('截至选中日尚无已公开公司财报');
  }
  if (pickMacro) {
    const macTiming = expTimingLabel(pickMacro.published, winStart, winEnd, legs);
    const macLink = pickMacro.url ? ` ${renderLink(pickMacro.url, '统计原件')}` : '';
    clauses.push(`行业最新为${escText(macroTitle)} ${escText(pickMacro.period)} 期（${fmtSigned(pickMacro.value, 1, macroMeta.unit || '%')}），${escText(pickMacro.published)} 公开（${escText(macTiming)}）${macLink}`);
  } else if (macroMeta.loaded) {
    clauses.push('截至选中日暂无已公开行业统计');
  }
  const p3 = `${clauses.join('；')}。公开日仅标示披露时间位置，不作涨跌归因。`;

  const rowsToRender = common.length >= 2 ? [refSpan, ...legs] : [refSpan];
  const rowsHtml = rowsToRender.map((r) => {
    const dxyCell = r.dxy.ok
      ? `${expFmtPct(r.dxy.pct)} <span style="color:var(--wb-ink-muted)">(${escText(r.dxy.d0)}→${escText(r.dxy.d1)}${r.dxy.shifted ? '·前值' : ''})</span>`
      : `<span style="color:var(--wb-ink-muted)">${escText(r.dxy.note)}</span>`;
    return `<tr><td><strong>${escText(r.name)}</strong> ${escText(r.start)} 至 ${escText(r.end)}</td><td>${expFmtPct(r.stockPct)}</td><td>${r.benchPct !== null ? expFmtPct(r.benchPct) : '—'}</td><td>${r.diffPp !== null ? expFmtPct(r.diffPp, ' 个百分点') : '—'}</td><td>${dxyCell}</td></tr>`;
  }).join('');

  return `
    <div class="er-mo-exp" data-driver-explanation>
      <div class="er-mo-exp-lead">
        <p><span class="er-mo-exp-k">这段行情怎么走</span>${p1}</p>
        <p><span class="er-mo-exp-k">市场与美元对照</span>${p2}</p>
        <p><span class="er-mo-exp-k">基本面何时更新</span>${p3}</p>
      </div>
      <table class="er-mo-exp-tbl">
        <thead><tr><th>同日期配对区间${splitRule ? `（${escText(splitRule)}）` : ''}</th><th>${compName}</th><th>${benchName}</th><th>涨跌幅之差</th><th>DXY（港股可用日）</th></tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
}

function renderTrack0Svg(model, width = 860, height = 132) {
  const padL = 52;
  const padR = 54;
  const padT = 12;
  const padB = 22;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const xOf = (day) => {
    const idx = model.calendarIndexMap.get(day) ?? 0;
    const denom = Math.max(1, model.calendar.length - 1);
    return padL + (idx / denom) * plotW;
  };

  if (!model.stockWin.length) {
    return `<div class="er-mo-empty">当前窗口（截至 ${escText(model.endDay)}）内无个股有效收盘记录</div>`;
  }

  const useNorm = model.normComp.hasCommon;
  const rawPriceScale = computeNiceScale(model.stockWin.map((p) => p.close), 0.1);

  let leftScale;
  let stockDrawPts;
  let benchDrawPts = [];

  if (useNorm) {
    const allNormVals = [
      ...model.normComp.stockNorm.map((p) => p.norm),
      ...model.normComp.benchNorm.map((p) => p.norm),
      100,
    ];
    leftScale = computeNiceScale(allNormVals, 0.1);
    stockDrawPts = model.normComp.stockNorm;
    benchDrawPts = model.normComp.benchNorm;
  } else {
    leftScale = rawPriceScale;
    stockDrawPts = model.stockWin;
  }

  const yOfLeft = (v) => padT + ((leftScale.max - v) / Math.max(1e-9, leftScale.max - leftScale.min)) * plotH;
  const stockValKey = useNorm ? 'norm' : 'close';
  const stockGeom = buildDailyLineSegments(stockDrawPts, model.calendarIndexMap, xOf, yOfLeft, stockValKey, true);
  const benchGeom = useNorm
    ? buildDailyLineSegments(benchDrawPts, model.calendarIndexMap, xOf, yOfLeft, 'norm', true)
    : { paths: [], singleDots: [] };

  const axisColor = useNorm ? '#475569' : model.profile.primaryColor;
  const gridLines = leftScale.ticks
    .map((t) => {
      const y = yOfLeft(t).toFixed(2);
      const leftLabel = useNorm ? fmtNum(t, 1) : fmtNum(t, 2);
      return `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#e5e9f0" stroke-width="1" />
        <text x="${padL - 6}" y="${Number(y) + 3.5}" text-anchor="end" font-size="10" fill="${axisColor}">${escText(leftLabel)}</text>
      `;
    })
    .join('');

  const baseline100 = useNorm && leftScale.min < 100 && leftScale.max > 100
    ? `<line x1="${padL}" y1="${yOfLeft(100).toFixed(2)}" x2="${width - padR}" y2="${yOfLeft(100).toFixed(2)}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="3,3" /><text x="${width - padR + 5}" y="${(yOfLeft(100) + 3.5).toFixed(2)}" text-anchor="start" font-size="9.5" fill="#64748b">首日=100</text>`
    : '';

  const axisDates = pickAxisDates(model.calendar)
    .map((d) => {
      const x = xOf(d).toFixed(2);
      return `<text x="${x}" y="${height - 5}" text-anchor="middle" font-size="10" fill="#768295">${escText(d.slice(5))}</text>`;
    })
    .join('');

  const benchPaths = benchGeom.paths
    .map((d) => `<path d="${d}" fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="4,3" />`)
    .join('');
  const benchDots = benchGeom.singleDots
    .map((pt) => `<circle cx="${pt.x.toFixed(2)}" cy="${pt.y.toFixed(2)}" r="2.6" fill="#64748b" />`)
    .join('');

  const stockPaths = stockGeom.paths
    .map((d) => `<path d="${d}" fill="none" stroke="${model.profile.primaryColor}" stroke-width="2" />`)
    .join('');
  const stockDots = stockGeom.singleDots
    .map((pt) => `<circle cx="${pt.x.toFixed(2)}" cy="${pt.y.toFixed(2)}" r="3" fill="${model.profile.primaryColor}" />`)
    .join('');

  return `
    <svg class="er-mo-svg" viewBox="0 0 ${width} ${height}" data-svg-track="0" data-pad-l="${padL}" data-pad-r="${padR}" data-width="${width}">
      ${gridLines}
      ${baseline100}
      ${benchPaths}
      ${benchDots}
      ${stockPaths}
      ${stockDots}
      <line data-cursor-line="1" x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="#1e293b" stroke-width="1" stroke-dasharray="2,2" visibility="hidden" />
      <circle data-cursor-dot="stock" cx="0" cy="0" r="3.8" fill="${model.profile.primaryColor}" stroke="#fff" stroke-width="1.2" visibility="hidden" />
      <circle data-cursor-dot="bench" cx="0" cy="0" r="3.3" fill="#64748b" stroke="#fff" stroke-width="1.2" visibility="hidden" />
      ${axisDates}
    </svg>
  `;
}

function renderStepTrackSvg(model, trackIdx, seriesList, width = 860, height = 104) {
  const padL = 52;
  const padR = 54;
  const padT = 12;
  const padB = 20;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const xOf = (day) => {
    const idx = model.calendarIndexMap.get(day) ?? 0;
    const denom = Math.max(1, model.calendar.length - 1);
    return padL + (idx / denom) * plotW;
  };

  if (trackIdx === 1 && !model.macroMeta.loaded) {
    return `<div class="er-mo-empty">正在同步国家统计局/行业宏观与跨市场序列…</div>`;
  }

  const visibleVals = [];
  for (const s of seriesList) {
    const upto = s.points.filter((p) => p.published <= model.endDay);
    const preIdx = binaryFloorIndex(upto, 'published', model.startDay);
    if (preIdx >= 0) visibleVals.push(upto[preIdx].value);
    for (const p of upto) {
      if (p.published >= model.startDay) visibleVals.push(p.value);
    }
  }

  if (!visibleVals.length) {
    const emptyMsg = trackIdx === 1
      ? (model.macroMeta.message || '当前截止日前暂无可用行业宏观序列数据')
      : '当前截止日前暂无已公开的公司定期报告数据';
    return `<div class="er-mo-empty">${escText(emptyMsg)}</div>`;
  }

  if (trackIdx === 1) {
    visibleVals.push(0);
  }
  const scale = computeNiceScale(visibleVals, 0.15);
  const yOf = (v) => padT + ((scale.max - v) / Math.max(1e-9, scale.max - scale.min)) * plotH;

  const gridLines = scale.ticks
    .map((t) => {
      const y = yOf(t).toFixed(2);
      const lbl = fmtNum(t, trackIdx === 1 ? 1 : 2);
      return `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#e5e9f0" stroke-width="1" />
        <text x="${padL - 6}" y="${Number(y) + 3.5}" text-anchor="end" font-size="10" fill="#64748b">${escText(lbl)}</text>
      `;
    })
    .join('');

  const zeroLine = scale.min < 0 && scale.max > 0
    ? `<line x1="${padL}" y1="${yOf(0).toFixed(2)}" x2="${width - padR}" y2="${yOf(0).toFixed(2)}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3,3" />`
    : '';

  let geomSvg = '';
  seriesList.forEach((s, sIdx) => {
    const geom = buildStepGeometry(s.points, model.startDay, model.endDay, xOf, yOf);
    s._yOf = yOf;
    if (geom.carryLeft) {
      geomSvg += `<polygon points="${padL - 5},${geom.carryLeft.y.toFixed(2)} ${padL},${(geom.carryLeft.y - 3.5).toFixed(2)} ${padL},${(geom.carryLeft.y + 3.5).toFixed(2)}" fill="${s.color}" opacity="0.85" />`;
    }
    for (const seg of geom.segments) {
      const dash = seg.dashed ? ' stroke-dasharray="4,3"' : '';
      geomSvg += `<line x1="${seg.x1.toFixed(2)}" y1="${seg.y1.toFixed(2)}" x2="${seg.x2.toFixed(2)}" y2="${seg.y2.toFixed(2)}" stroke="${s.color}" stroke-width="1.85"${dash} />`;
    }
    for (const d of geom.dots) {
      geomSvg += `<circle cx="${d.x.toFixed(2)}" cy="${d.y.toFixed(2)}" r="3.4" fill="#ffffff" stroke="${s.color}" stroke-width="2" />`;
    }
    geomSvg += `<circle data-cursor-dot="s${sIdx}" cx="0" cy="0" r="3.6" fill="${s.color}" stroke="#fff" stroke-width="1.2" visibility="hidden" />`;
  });

  const axisDates = pickAxisDates(model.calendar)
    .map((d) => `<text x="${xOf(d).toFixed(2)}" y="${height - 4}" text-anchor="middle" font-size="10" fill="#768295">${escText(d.slice(5))}</text>`)
    .join('');

  return `
    <svg class="er-mo-svg" viewBox="0 0 ${width} ${height}" data-svg-track="${trackIdx}" data-pad-l="${padL}" data-pad-r="${padR}" data-width="${width}">
      ${gridLines}
      ${zeroLine}
      ${geomSvg}
      <line data-cursor-line="1" x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="#1e293b" stroke-width="1" stroke-dasharray="2,2" visibility="hidden" />
      ${axisDates}
    </svg>
  `;
}

function renderTrack3DxySvg(model, width = 860, height = 98) {
  const padL = 52;
  const padR = 54;
  const padT = 12;
  const padB = 20;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const xOf = (day) => {
    const idx = model.calendarIndexMap.get(day) ?? 0;
    const denom = Math.max(1, model.calendar.length - 1);
    return padL + (idx / denom) * plotW;
  };

  if (!model.macroMeta.loaded) {
    return `<div class="er-mo-empty">正在载入 ICE 美元指数 (DXY) 完整日线…</div>`;
  }

  if (!model.dxyWin.length) {
    const msg = model.dxyMeta.error || '当前窗口（<= 截止日）暂无可用 ICE 美元指数完整日线记录';
    return `<div class="er-mo-empty">${escText(msg)}</div>`;
  }

  const scale = computeNiceScale(model.dxyWin.map((p) => p.close), 0.12);
  const yOf = (v) => padT + ((scale.max - v) / Math.max(1e-9, scale.max - scale.min)) * plotH;
  model._dxyYOf = yOf;

  // DXY Hong Kong availability dates are Tue..Sat (for Mon..Fri NY sessions); bridge Sun-Mon non-session calendar days cleanly
  const dxyRuns = [];
  let run = [model.dxyWin[0]];
  for (let i = 1; i < model.dxyWin.length; i++) {
    const prev = model.dxyWin[i - 1];
    const curr = model.dxyWin[i];
    const gap = diffCalendarDays(prev.date, curr.date);
    // Normal weekend gap between Saturday HK available (Fri NY) and Tuesday HK available (Mon NY) is 3 days
    const prevWd = new Date(parseUtcMs(prev.date)).getUTCDay();
    const normalWeekendBridge = prevWd === 6 && gap <= 3;
    if (gap === 1 || normalWeekendBridge) {
      run.push(curr);
    } else {
      dxyRuns.push(run);
      run = [curr];
    }
  }
  dxyRuns.push(run);

  let lineSvg = '';
  for (const r of dxyRuns) {
    if (r.length === 1) {
      lineSvg += `<circle cx="${xOf(r[0].date).toFixed(2)}" cy="${yOf(r[0].close).toFixed(2)}" r="2.8" fill="#8f3d26" />`;
    } else {
      const dPath = r
        .map((p, idx) => `${idx === 0 ? 'M' : 'L'}${xOf(p.date).toFixed(2)},${yOf(p.close).toFixed(2)}`)
        .join(' ');
      lineSvg += `<path d="${dPath}" fill="none" stroke="#8f3d26" stroke-width="1.8" />`;
    }
  }

  const gridLines = scale.ticks
    .map((t) => {
      const y = yOf(t).toFixed(2);
      return `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#e5e9f0" stroke-width="1" />
        <text x="${padL - 6}" y="${Number(y) + 3.5}" text-anchor="end" font-size="10" fill="#8f3d26">${escText(fmtNum(t, 2))}</text>
      `;
    })
    .join('');

  const axisDates = pickAxisDates(model.calendar)
    .map((d) => `<text x="${xOf(d).toFixed(2)}" y="${height - 4}" text-anchor="middle" font-size="10" fill="#768295">${escText(d.slice(5))}</text>`)
    .join('');

  return `
    <svg class="er-mo-svg" viewBox="0 0 ${width} ${height}" data-svg-track="3" data-pad-l="${padL}" data-pad-r="${padR}" data-width="${width}">
      ${gridLines}
      ${lineSvg}
      <line data-cursor-line="1" x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="#1e293b" stroke-width="1" stroke-dasharray="2,2" visibility="hidden" />
      <circle data-cursor-dot="dxy" cx="0" cy="0" r="3.6" fill="#8f3d26" stroke="#fff" stroke-width="1.2" visibility="hidden" />
      ${axisDates}
    </svg>
  `;
}

function buildTrackReadouts(model, cursorDay, isHoverOrPinned) {
  // Track 0: Stock + Benchmark
  const exactStock = model.stockMap.get(cursorDay) ?? null;
  const floorStockIdx = binaryFloorIndex(model.stockAll, 'date', cursorDay);
  const latestStock = floorStockIdx >= 0 ? model.stockAll[floorStockIdx] : null;

  const exactBench = model.benchMap.get(cursorDay) ?? null;
  const floorBenchIdx = binaryFloorIndex(model.benchAll, 'date', cursorDay);
  const latestBench = floorBenchIdx >= 0 ? model.benchAll[floorBenchIdx] : null;

  let stockHtml = '';
  if (exactStock !== null) {
    stockHtml = `<span><i class="er-mo-swatch" style="background:${model.profile.primaryColor}"></i>${escText(model.profile.companyName)} <strong>${fmtNum(exactStock, 2)}</strong> ${escText(model.profile.stockUnit)}</span>`;
  } else if (!isHoverOrPinned && latestStock) {
    stockHtml = `<span><i class="er-mo-swatch" style="background:${model.profile.primaryColor}"></i>截止日休市/无收盘，最近真实收盘 <strong>${fmtNum(latestStock.close, 2)}</strong> ${escText(model.profile.stockUnit)}（${escText(latestStock.date)}）</span>`;
  } else {
    const fallbackNote = latestStock ? `（前最近 ${latestStock.date}: ${fmtNum(latestStock.close, 2)}）` : '';
    stockHtml = `<span><i class="er-mo-swatch" style="background:${model.profile.primaryColor}"></i><strong>${escText(cursorDay)} 无股票收盘</strong>${escText(fallbackNote)}</span>`;
  }

  let benchHtml = '';
  if (!model.macroMeta.loaded) {
    benchHtml = `<span><i class="er-mo-swatch-dash"></i>${escText(model.benchMeta.label)} 同步中…</span>`;
  } else if (exactBench !== null) {
    const sp = model.normComp.spreadMap.get(cursorDay);
    const spTxt = sp
      ? `｜归一 ${fmtNum(sp.stockNorm, 2)} vs ${fmtNum(sp.benchNorm, 2)}，相对基准区间价差 <strong>${fmtSigned(sp.spread, 2, ' 百分点')}</strong>`
      : '';
    benchHtml = `<span><i class="er-mo-swatch-dash"></i>${escText(model.benchMeta.label)} <strong>${fmtNum(exactBench, 2)}</strong> 点${spTxt}</span>`;
  } else if (model.benchAll.length > 0) {
    if (!isHoverOrPinned && latestBench) {
      const sp = model.normComp.latestSpread && model.normComp.latestCommonDate <= cursorDay
        ? `｜共同最新日(${escText(model.normComp.latestCommonDate)})区间价差 <strong>${fmtSigned(model.normComp.latestSpread.spread, 2, ' 百分点')}</strong>`
        : '';
      benchHtml = `<span><i class="er-mo-swatch-dash"></i>${escText(model.benchMeta.label)} 当日无收盘，最近 <strong>${fmtNum(latestBench.close, 2)}</strong> 点（${escText(latestBench.date)}）${sp}</span>`;
    } else {
      benchHtml = `<span><i class="er-mo-swatch-dash"></i>${escText(model.benchMeta.label)} 当日无收盘${latestBench ? `（前值 ${latestBench.date}: ${fmtNum(latestBench.close, 2)}）` : ''}</span>`;
    }
  } else {
    benchHtml = `<span><i class="er-mo-swatch-dash"></i>${escText(model.benchMeta.label)} 暂不可用</span>`;
  }

  const covLink = model.stockCoverageUrl
    ? renderLink(model.stockCoverageUrl, model.stockCoverageSource || '股票行情源')
    : '';
  const bmLink = model.benchMeta.url
    ? renderLink(model.benchMeta.url, model.benchMeta.source || '腾讯证券')
    : '';
  const t0Links = [covLink, bmLink].filter(Boolean).join(' · ');

  // Track 1: Industry Macro
  let t1Html = '';
  if (!model.macroMeta.loaded) {
    t1Html = '<span>载入国家统计局宏观序列中…</span>';
  } else if (!model.macroSeries.length) {
    t1Html = `<span>${escText(model.macroMeta.message || '暂无 <= 截止日宏观数据')}</span>`;
  } else {
    const act = activeDisclosedAt(model.macroSeries, cursorDay)?.point;
    if (!act) {
      t1Html = `<span>截至 ${escText(cursorDay)} 尚无已发布记录</span>`;
    } else {
      const link = act.url ? ` · ${renderLink(act.url, '统计局/原件')}` : '';
      const statName = readableMacroMetric(act.metric, model.macroMeta.label, model.profile.isPoly);
      const gapBadge = act.isGapFromPrev ? ' · [跨期虚线延续]' : '';
      t1Html = `<span><i class="er-mo-swatch" style="background:#5b4b8a"></i>${escText(statName)} <strong>${fmtSigned(act.value, 2, model.macroMeta.unit || '%')}</strong>（统计期 ${escText(act.period)}，${escText(act.published)} 发布${escText(gapBadge)}）｜${escText(formatChangeSummary(act, model.macroMeta.unit || '%'))}${link}</span>`;
    }
  }

  // Track 2: Company Micro Financials
  let t2Html = '';
  if (!model.microSeriesList.length) {
    t2Html = '<span>暂无公司财务驱动序列</span>';
  } else {
    const parts = model.microSeriesList.map((s) => {
      const act = activeDisclosedAt(s.points, cursorDay)?.point;
      if (!act) {
        return `<span><i class="er-mo-swatch" style="background:${s.color}"></i>${escText(s.label)}：截至 ${escText(cursorDay)} 未披露</span>`;
      }
      const pageTxt = act.page ? ` P.${act.page}` : '';
      const srcLabel = `${act.source || '定期报告原件'}${pageTxt}`;
      const link = act.url ? ` · ${renderLink(act.url, srcLabel)}` : (act.source ? ` · ${escText(srcLabel)}` : '');
      return `<span><i class="er-mo-swatch" style="background:${s.color}"></i>${escText(s.label)} <strong>${fmtNum(act.value, 2)}</strong> ${escText(s.unit)}（报告期 ${escText(act.period)}，${escText(act.published)} 披露｜${escText(formatChangeSummary(act, s.unit, model.cadence))}）${link}</span>`;
    });
    t2Html = parts.join(' ');
  }

  // Track 3: ICE US Dollar Index DXY
  let t3Html = '';
  if (!model.macroMeta.loaded) {
    t3Html = '<span>载入 ICE 美元指数 (DXY) 中…</span>';
  } else if (!model.dxySeries.length) {
    t3Html = `<span>${escText(model.dxyMeta.error || '暂无可用 DXY 历史日线')}</span>`;
  } else {
    const exactDxy = model.dxyMap.get(cursorDay) ?? null;
    const floorIdx = binaryFloorIndex(model.dxySeries, 'date', cursorDay);
    const latestDxy = floorIdx >= 0 ? model.dxySeries[floorIdx] : null;
    const yLink = model.dxyMeta.url ? renderLink(model.dxyMeta.url, 'Yahoo历史日线') : '';
    const iceLink = model.dxyMeta.spec_url ? renderLink(model.dxyMeta.spec_url, 'ICE指数口径') : '';
    const links = [yLink, iceLink].filter(Boolean).join(' · ');

    if (exactDxy) {
      t3Html = `<span><i class="er-mo-swatch" style="background:#8f3d26"></i>DXY <strong>${fmtNum(exactDxy.close, 2)}</strong> 点（香港可用日 ${escText(exactDxy.date)}，对应纽约交易日 ${escText(exactDxy.session || '前一交易日')} 完整收盘） ${links}</span>`;
    } else if (latestDxy) {
      const prefix = isHoverOrPinned ? `${escText(cursorDay)} 无新完结纽约日线，沿用最近可用` : '最近已完结可用';
      t3Html = `<span><i class="er-mo-swatch" style="background:#8f3d26"></i>${prefix} <strong>${fmtNum(latestDxy.close, 2)}</strong> 点（香港可用日 ${escText(latestDxy.date)} / 纽约交易日 ${escText(latestDxy.session || '—')} 收盘） ${links}</span>`;
    } else {
      t3Html = `<span><i class="er-mo-swatch" style="background:#8f3d26"></i>截至 ${escText(cursorDay)} 尚无可用纽约完整日线 ${links}</span>`;
    }
  }

  return {
    t0: `${stockHtml} ${benchHtml} ${t0Links ? `<span>${t0Links}</span>` : ''}`,
    t1: t1Html,
    t2: t2Html,
    t3: t3Html,
  };
}

function updateCursorVisuals(host, model, state) {
  const cursorDay = state.cursorDay;
  const isInteractive = state.pinned || state.hovering;
  const idx = model.calendarIndexMap.get(cursorDay) ?? (model.calendar.length - 1);
  const denom = Math.max(1, model.calendar.length - 1);

  // Day badges
  const dayNodes = host.querySelectorAll('[data-driver-day]');
  dayNodes.forEach((node) => {
    node.textContent = cursorDay;
    if (node.classList.contains('er-mo-day-pill')) {
      node.setAttribute('data-pinned', state.pinned ? '1' : '0');
      node.textContent = state.pinned
        ? `选中日 ${cursorDay}（已固定，点击或按 Esc 解除）`
        : `选中日 ${cursorDay}${cursorDay === model.endDay && !state.hovering ? '（截止日）' : ''}`;
    }
  });

  updateMarketReview(host, model, state.pinned ? cursorDay : model.endDay);

  // Clue KPI cards update dynamically with cursorDay (respecting <= cursorDay disclosure!)
  const kpiBox = host.querySelector('[data-role="kpi-grid"]');
  if (kpiBox) {
    kpiBox.innerHTML = buildClueCardsHtml(model, cursorDay);
  }

  // Track value readouts
  const readouts = buildTrackReadouts(model, cursorDay, isInteractive);
  const val0 = host.querySelector('[data-driver-track="0"] [data-driver-value]');
  const val1 = host.querySelector('[data-driver-track="1"] [data-driver-value]');
  const val2 = host.querySelector('[data-driver-track="2"] [data-driver-value]');
  const val3 = host.querySelector('[data-driver-track="3"] [data-driver-value]');
  if (val0) val0.innerHTML = readouts.t0;
  if (val1) val1.innerHTML = readouts.t1;
  if (val2) val2.innerHTML = readouts.t2;
  if (val3) val3.innerHTML = readouts.t3;

  // SVG cursor hairlines & active dots
  const svgs = host.querySelectorAll('svg[data-svg-track]');
  svgs.forEach((svg) => {
    const padL = Number(svg.getAttribute('data-pad-l')) || 52;
    const padR = Number(svg.getAttribute('data-pad-r')) || 54;
    const width = Number(svg.getAttribute('data-width')) || 860;
    const x = padL + (idx / denom) * (width - padL - padR);

    const line = svg.querySelector('[data-cursor-line]');
    if (line) {
      line.setAttribute('x1', x.toFixed(2));
      line.setAttribute('x2', x.toFixed(2));
      line.setAttribute('visibility', 'visible');
      line.setAttribute('stroke', state.pinned ? '#b45309' : '#1e293b');
    }

    const tId = svg.getAttribute('data-svg-track');
    if (tId === '0') {
      const dotStock = svg.querySelector('[data-cursor-dot="stock"]');
      const dotBench = svg.querySelector('[data-cursor-dot="bench"]');
      if (dotStock) {
        const useNorm = model.normComp.hasCommon;
        const rawClose = model.stockMap.get(cursorDay);
        if (rawClose !== undefined && (!useNorm || cursorDay >= model.normComp.baseDate)) {
          const val = useNorm ? (rawClose / model.normComp.stockBase) * 100 : rawClose;
          const allVals = useNorm
            ? [...model.normComp.stockNorm.map((p) => p.norm), ...model.normComp.benchNorm.map((p) => p.norm), 100]
            : model.stockWin.map((p) => p.close);
          const sc = computeNiceScale(allVals, 0.1);
          const y = 12 + ((sc.max - val) / Math.max(1e-9, sc.max - sc.min)) * (132 - 12 - 22);
          dotStock.setAttribute('cx', x.toFixed(2));
          dotStock.setAttribute('cy', y.toFixed(2));
          dotStock.setAttribute('visibility', 'visible');
        } else {
          dotStock.setAttribute('visibility', 'hidden');
        }
      }
      if (dotBench) {
        const rawBench = model.benchMap.get(cursorDay);
        if (model.normComp.hasCommon && rawBench !== undefined && cursorDay >= model.normComp.baseDate) {
          const val = (rawBench / model.normComp.benchBase) * 100;
          const allVals = [...model.normComp.stockNorm.map((p) => p.norm), ...model.normComp.benchNorm.map((p) => p.norm), 100];
          const sc = computeNiceScale(allVals, 0.1);
          const y = 12 + ((sc.max - val) / Math.max(1e-9, sc.max - sc.min)) * (132 - 12 - 22);
          dotBench.setAttribute('cx', x.toFixed(2));
          dotBench.setAttribute('cy', y.toFixed(2));
          dotBench.setAttribute('visibility', 'visible');
        } else {
          dotBench.setAttribute('visibility', 'hidden');
        }
      }
    } else if (tId === '1' || tId === '2') {
      const list = tId === '1' ? model.track1SeriesObj : model.microSeriesList;
      list.forEach((s, sIdx) => {
        const dot = svg.querySelector(`[data-cursor-dot="s${sIdx}"]`);
        if (!dot || !s._yOf) return;
        const act = activeDisclosedAt(s.points, cursorDay)?.point;
        if (act) {
          dot.setAttribute('cx', x.toFixed(2));
          dot.setAttribute('cy', s._yOf(act.value).toFixed(2));
          dot.setAttribute('visibility', 'visible');
        } else {
          dot.setAttribute('visibility', 'hidden');
        }
      });
    } else if (tId === '3') {
      const dotDxy = svg.querySelector('[data-cursor-dot="dxy"]');
      if (dotDxy && model._dxyYOf) {
        const exact = model.dxyMap.get(cursorDay);
        if (exact) {
          dotDxy.setAttribute('cx', x.toFixed(2));
          dotDxy.setAttribute('cy', model._dxyYOf(exact.close).toFixed(2));
          dotDxy.setAttribute('visibility', 'visible');
        } else {
          dotDxy.setAttribute('visibility', 'hidden');
        }
      }
    }
  });
}

function buildDataModel(data, macro, days) {
  const profile = detectCompanyProfile(data);
  const cutoff = isValidDay(data?.cutoff) ? data.cutoff : '';
  const stockAll = extractStockSeries(data, profile.code, cutoff);
  const { startDay, endDay, calendar, requestedDays } = buildWindowCalendar(stockAll, cutoff, days);

  const calendarIndexMap = new Map();
  calendar.forEach((d, idx) => calendarIndexMap.set(d, idx));

  const stockWin = stockAll.filter((p) => p.date >= startDay && p.date <= endDay);
  const stockMap = new Map(stockAll.map((p) => [p.date, p.close]));

  const cov0 = Array.isArray(data?.coverage) && data.coverage.length ? data.coverage[0] : null;
  const stockCoverageUrl = cov0?.url || '';
  const stockCoverageSource = cov0?.source || '交易所/公开收盘';

  // Macro industry fundamentals
  const macroLoaded = macro !== null && macro !== undefined;
  const macroUnit = macro?.unit || '%';
  const rawMacroCandidate = [macro?.label, data?.drivers?.macro_label]
    .find((s) => typeof s === 'string' && /[\u4e00-\u9fff]/.test(s) && !/^(appliances|housing)$/i.test(s.trim()));
  const macroLabel = !profile.isPoly
    ? (rawMacroCandidate && !/产量/.test(rawMacroCandidate) ? rawMacroCandidate : '国家统计局家电和音像零售')
    : (rawMacroCandidate || '国家统计局全国房地产竣工面积同比');
  const macroSeries = macroLoaded
    ? preparePublishedSeries(macro?.points || [], endDay, isMacroStepGap)
    : [];

  const track1SeriesObj = [
    {
      label: macroLabel,
      unit: macroUnit,
      color: '#5b4b8a',
      points: macroSeries,
    },
  ];

  // Company Micro series
  const cadence = Number(data?.drivers?.cadence) || (profile.isPoly ? 6 : 3);
  const rawMicroList = Array.isArray(data?.drivers?.series) ? data.drivers.series : [];
  const microColors = profile.isPoly ? ['#146c54', '#b85d19'] : ['#0e5a8a', '#b85d19'];
  const microSeriesList = rawMicroList.map((s, idx) => ({
    label: String(s?.label || `财务序列 ${idx + 1}`),
    unit: String(s?.unit || '亿元'),
    color: microColors[idx % microColors.length],
    points: preparePublishedSeries(s?.points || [], endDay, (a, b) => isMicroStepGap(a, b, cadence)),
  }));

  // Market Linkage: Benchmark + DXY
  const mkt = macro?.market || null;
  const bmNode = mkt?.benchmark || null;
  const benchMeta = {
    label: bmNode?.label || profile.defaultBenchLabel,
    unit: bmNode?.unit || '点',
    url: bmNode?.url || (profile.isPoly ? 'https://gu.qq.com/hkHSI' : 'https://gu.qq.com/sh000300'),
    source: bmNode?.source || '腾讯证券',
    error: bmNode?.error || '',
  };
  const benchAll = normalizeMarketSeries(bmNode?.points || [], endDay, false);
  const benchWin = benchAll.filter((p) => p.date >= startDay && p.date <= endDay);
  const benchMap = new Map(benchAll.map((p) => [p.date, p.close]));
  const normComp = computeNormalizedComparison(stockWin, benchWin);

  const dxyNode = mkt?.dxy || null;
  const dxyMeta = {
    label: dxyNode?.label || 'ICE 美元指数 (DXY)',
    unit: dxyNode?.unit || '点',
    url: dxyNode?.url || 'https://finance.yahoo.com/quote/DX-Y.NYB/history/',
    spec_url: dxyNode?.spec_url || 'https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices',
    source: dxyNode?.source || 'Yahoo Finance / ICE Data Indices',
    error: dxyNode?.error || '',
  };
  const dxySeries = normalizeMarketSeries(dxyNode?.points || [], endDay, true);
  const dxyWin = dxySeries.filter((p) => p.date >= startDay && p.date <= endDay);
  const dxyMap = new Map(dxySeries.map((p) => [p.date, p]));

  const statusMessages = [];
  if (macro?.message) statusMessages.push(String(macro.message));
  if (mkt?.message) statusMessages.push(String(mkt.message));
  const hasError = Boolean(benchMeta.error || dxyMeta.error);

  return {
    profile,
    cutoff: endDay,
    startDay,
    endDay,
    calendar,
    calendarIndexMap,
    requestedDays,
    cadence,
    stockAll,
    stockWin,
    stockMap,
    stockCoverageUrl,
    stockCoverageSource,
    benchMeta,
    benchAll,
    benchWin,
    benchMap,
    normComp,
    macroMeta: {
      loaded: macroLoaded,
      label: macroLabel,
      unit: macroUnit,
      message: macro?.message || '',
      note: data?.drivers?.macro_note || '',
      statusText: macroLoaded ? (macro?.message || '无可用宏观记录') : '正在请求 /market-context/macro …',
    },
    macroSeries,
    track1SeriesObj,
    microNote: data?.drivers?.micro_note || '',
    microSeriesList,
    dxyMeta,
    dxySeries,
    dxyWin,
    dxyMap,
    combinedStatus: statusMessages.join(' ｜ '),
    hasError,
  };
}

export function renderDriverChart(host, data, macro, days) {
  if (!host || !(host instanceof HTMLElement)) return;
  injectStyles();

  // Clean up previous event listeners on this host before re-rendering
  const prevState = STATE_MAP.get(host);
  if (prevState && prevState.abortController) {
    prevState.abortController.abort();
  }

  const model = buildDataModel(data || {}, macro, days);
  const abortController = new AbortController();
  const { signal } = abortController;

  // Preserve cursorDay and pinned state across the two-pass render (macro=null -> macro=loaded) on the same host & cutoff/window
  let cursorDay = model.endDay;
  let pinned = false;
  if (
    prevState &&
    prevState.companyCode === model.profile.code &&
    prevState.cutoff === model.endDay &&
    isValidDay(prevState.cursorDay) &&
    model.calendarIndexMap.has(prevState.cursorDay)
  ) {
    cursorDay = prevState.cursorDay;
    pinned = Boolean(prevState.pinned);
  }

  const state = {
    companyCode: model.profile.code,
    cutoff: model.endDay,
    days: model.requestedDays,
    cursorDay,
    pinned,
    hovering: false,
    abortController,
  };
  STATE_MAP.set(host, state);

  const clueHeading = model.profile.isPoly
    ? '保利物业经营与市场对照线索：外部地产交付环境 × 贸易应收回款占用 × 相对恒生指数表现 × DXY美元强弱观察'
    : '格力电器经营与市场对照线索：国家统计局家电和音像零售 × 合并存货与合同负债各自变动 × 相对沪深300表现 × DXY美元强弱观察';

  const track0AxisDesc = model.normComp.hasCommon
    ? `同轴归一化刻度（共同首日 ${model.normComp.baseDate} = 100）｜ 原币收盘（${model.profile.stockUnit}）与相对基准区间价差见右上角读数`
    : `纵轴：${model.profile.companyName}未复权原币收盘（${model.profile.stockUnit}，当前窗口无共同基准交易日）`;

  const track0LegendDesc = model.normComp.hasCommon
    ? `实线：${model.profile.companyName}归一化（${model.normComp.baseDate}=100）｜虚线：${model.benchMeta.label}归一化（${model.normComp.baseDate}=100）；自首个共同交易日起绘，区间价差仅按共同交易日计算`
    : `实线：${model.profile.companyName}未复权原币日收盘（${model.profile.stockUnit}，工作日缺失自动断线，孤立点单绘）`;

  const cadenceDesc = model.cadence === 6
    ? '半年报/年报披露阶梯（不插值，按实际公告发布日跳变）'
    : '季报/年报披露阶梯（不插值，按实际公告发布日跳变）';

  host.innerHTML = `
    <section class="er-mo-wb" data-theme="${escText(model.profile.theme)}">
      <header class="er-mo-top">
        <div class="er-mo-title-group">
          <span class="er-mo-badge">${escText(model.profile.code)}</span>
          <h3 class="er-mo-heading">${escText(model.profile.companyName)} · 四轨市场联动与基本面工作台</h3>
          <span class="er-mo-subtag">窗口 ${escText(model.startDay)} 至 ${escText(model.endDay)}（${escText(String(model.requestedDays))}交易日档 / 历史截止日锁死）</span>
        </div>
        <div class="er-mo-cursor-bar">
          <span class="er-mo-day-pill" data-driver-day data-pinned="${state.pinned ? '1' : '0'}">${escText(state.cursorDay)}</span>
          <button type="button" class="er-mo-btn" data-action="reset-cursor">回到截止日</button>
        </div>
      </header>

      <div class="er-mo-clue-box">
        <div class="er-mo-clue-head">
          <span class="er-mo-clue-title">${escText(clueHeading)}</span>
          <span class="er-mo-clue-rule">悬停看日明细 · 单击固定日期 · 左右方向键逐日核查（严格仅显示 &lt;= 选中日已公开数据）</span>
        </div>
        <section class="er-mo-case" data-driver-attribution hidden></section>
        <div class="er-mo-kpi-grid" data-role="kpi-grid"></div>
      </div>

      <div class="er-mo-tracks">
        <article class="er-mo-track" data-driver-track="0">
          <div class="er-mo-track-hdr">
            <div class="er-mo-track-lhs">
              <span class="er-mo-track-tag">轨 0 · 市场相对联动</span>
              <span class="er-mo-track-name">${escText(model.profile.companyName)} 与 ${escText(model.benchMeta.label)}</span>
              <span class="er-mo-track-unit">${escText(track0AxisDesc)}</span>
            </div>
            <div class="er-mo-track-val" data-driver-value></div>
          </div>
          <div class="er-mo-plot" data-driver-plot tabindex="0" role="application" aria-label="股票与市场基准联动轨迹，支持左右键切换日期">
            ${renderTrack0Svg(model)}
          </div>
          <div class="er-mo-track-foot">
            <span>${escText(track0LegendDesc)}</span>
            <span>时效标签：已收盘日线历史数据（&lt;= ${escText(model.endDay)}）</span>
          </div>
        </article>

        <article class="er-mo-track" data-driver-track="1">
          <div class="er-mo-track-hdr">
            <div class="er-mo-track-lhs">
              <span class="er-mo-track-tag">轨 1 · 行业宏观环境</span>
              <span class="er-mo-track-name">${escText(model.macroMeta.label)}</span>
              <span class="er-mo-track-unit">单位：${escText(model.macroMeta.unit)} ｜ 按国家统计局实际发布日阶梯延续（1–2月合并发布不断档，缺期虚线）</span>
            </div>
            <div class="er-mo-track-val" data-driver-value></div>
          </div>
          <div class="er-mo-plot" data-driver-plot tabindex="0" role="application" aria-label="行业宏观阶梯序列">
            ${renderStepTrackSvg(model, 1, model.track1SeriesObj)}
          </div>
          <div class="er-mo-track-foot">
            <span>${escText(model.macroMeta.note || '左轴三角标表示窗口起点前最近一次已公开前值延续；圆点为当期真实发布日。')}</span>
            <span>口径边界：行业宏观增速≠公司自身收入或面积增速</span>
          </div>
        </article>

        <article class="er-mo-track" data-driver-track="2">
          <div class="er-mo-track-hdr">
            <div class="er-mo-track-lhs">
              <span class="er-mo-track-tag">轨 2 · 公司经营披露</span>
              <span class="er-mo-track-name">${escText(model.microSeriesList.map((s) => s.label).join(' / ') || '核心资产负债经营科目')}</span>
              <span class="er-mo-track-unit">单位：${escText(model.microSeriesList[0]?.unit || '亿元')} ｜ ${escText(cadenceDesc)}</span>
            </div>
            <div class="er-mo-track-val" data-driver-value></div>
          </div>
          <div class="er-mo-plot" data-driver-plot tabindex="0" role="application" aria-label="公司财报经营序列">
            ${renderStepTrackSvg(model, 2, model.microSeriesList)}
          </div>
          <div class="er-mo-track-foot">
            <span>${escText(model.microNote || (model.profile.isPoly ? '贸易应收款项及票据净额受在管项目规模、结算节奏与坏账减值准备共同影响，反映期末回款资金占用而非当期实际坏账损失。' : '合并存货（公司备货）与合并合同负债（渠道预收）分别独立展示各自期末余额与同季同比/较上期变化。'))}</span>
            <span>披露对齐：严格以定期报告公告日入图，杜绝按报告期末日提前穿越</span>
          </div>
        </article>

        <article class="er-mo-track" data-driver-track="3">
          <div class="er-mo-track-hdr">
            <div class="er-mo-track-lhs">
              <span class="er-mo-track-tag">轨 3 · 美元强弱观察</span>
              <span class="er-mo-track-name">${escText(model.dxyMeta.label)}</span>
              <span class="er-mo-track-unit">单位：${escText(model.dxyMeta.unit)}（ICE DX-Y.NYB 原生指数，非期货/汇率中间价代理）</span>
            </div>
            <div class="er-mo-track-val" data-driver-value></div>
          </div>
          <div class="er-mo-plot" data-driver-plot tabindex="0" role="application" aria-label="ICE美元指数日线轨迹">
            ${renderTrack3DxySvg(model)}
          </div>
          <div class="er-mo-track-foot">
            <span>跨时区防穿越标签：仅取纽约零点完整收盘日线（剔除盘中实时柱），按保守约定于香港下一自然日标示可用；悬停同时列出香港可用日与纽约交易日。</span>
            <span>含义界定：仅供跨市场美元强弱观察，与公司经营及股价走势的关系需另做独立统计验证</span>
          </div>
        </article>
      </div>

      <div class="er-mo-status-strip" data-warn="${model.hasError ? '1' : '0'}">
        <strong>数据覆盖与源状态：</strong>${escText(model.combinedStatus || (model.macroMeta.loaded ? '股票、基准指数、宏观与定期报告均已按 <= 截止日对齐。' : '股票与财报已就绪，正在后台加载宏观、基准指数与 DXY 序列…'))}
      </div>

      <footer class="er-mo-guardrails">
        <span>研究纪律说明：① 曲线同向波动不代表因果关系；② 国家统计局零售/地产增速不等于公司自身增速；③ 保利应收净额受项目规模、结算节奏与减值计提影响，反映回款资金占用而非已发生坏账；④ DXY 仅表征美元强弱，与经营及股价关系需另做验证。</span>
        <span>交互支持：鼠标跨四轨同步游标 / 单击锁定 / 方向键微调</span>
      </footer>
    </section>
  `;

  updateCursorVisuals(host, model, state);

  // Bind interactive cursor events cleanly inside host
  const plots = host.querySelectorAll('[data-driver-plot]');
  const dayFromPointerEvent = (evt, plotEl) => {
    const svg = plotEl.querySelector('svg[data-svg-track]');
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return null;
    const vbWidth = Number(svg.getAttribute('data-width')) || 860;
    const padL = Number(svg.getAttribute('data-pad-l')) || 52;
    const padR = Number(svg.getAttribute('data-pad-r')) || 54;
    const relX = ((evt.clientX - rect.left) / rect.width) * vbWidth;
    const ratio = Math.max(0, Math.min(1, (relX - padL) / Math.max(1, vbWidth - padL - padR)));
    const idx = Math.round(ratio * (model.calendar.length - 1));
    return model.calendar[idx] || model.endDay;
  };

  plots.forEach((plotEl) => {
    plotEl.addEventListener(
      'mousemove',
      (evt) => {
        if (state.pinned) return;
        const d = dayFromPointerEvent(evt, plotEl);
        if (!d) return;
        state.hovering = true;
        if (state.cursorDay !== d) {
          state.cursorDay = d;
        }
        updateCursorVisuals(host, model, state);
      },
      { signal }
    );

    plotEl.addEventListener(
      'mouseleave',
      () => {
        if (state.pinned) return;
        state.hovering = false;
        state.cursorDay = model.endDay;
        updateCursorVisuals(host, model, state);
      },
      { signal }
    );

    plotEl.addEventListener(
      'click',
      (evt) => {
        // Ignore clicks on external links if any ever existed inside plot
        if (evt.target && evt.target.closest && evt.target.closest('a')) return;
        const d = dayFromPointerEvent(evt, plotEl);
        if (!d) return;
        if (state.pinned && state.cursorDay === d) {
          state.pinned = false;
          state.hovering = true;
        } else {
          state.cursorDay = d;
          state.pinned = true;
        }
        updateCursorVisuals(host, model, state);
      },
      { signal }
    );

    plotEl.addEventListener(
      'keydown',
      (evt) => {
        const currIdx = model.calendarIndexMap.get(state.cursorDay) ?? (model.calendar.length - 1);
        let nextIdx = currIdx;
        if (evt.key === 'ArrowLeft') {
          nextIdx = Math.max(0, currIdx - (evt.shiftKey ? 5 : 1));
        } else if (evt.key === 'ArrowRight') {
          nextIdx = Math.min(model.calendar.length - 1, currIdx + (evt.shiftKey ? 5 : 1));
        } else if (evt.key === 'Home') {
          nextIdx = 0;
        } else if (evt.key === 'End') {
          nextIdx = model.calendar.length - 1;
        } else if (evt.key === 'Escape') {
          state.pinned = false;
          state.hovering = false;
          state.cursorDay = model.endDay;
          updateCursorVisuals(host, model, state);
          evt.preventDefault();
          return;
        } else {
          return;
        }
        evt.preventDefault();
        state.cursorDay = model.calendar[nextIdx];
        state.pinned = true;
        updateCursorVisuals(host, model, state);
      },
      { signal }
    );
  });

  const resetBtn = host.querySelector('[data-action="reset-cursor"]');
  if (resetBtn) {
    resetBtn.addEventListener(
      'click',
      () => {
        state.pinned = false;
        state.hovering = false;
        state.cursorDay = model.endDay;
        updateCursorVisuals(host, model, state);
      },
      { signal }
    );
  }
}
