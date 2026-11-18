/* Gemini's three aligned tracks, rendered from published observations on a calendar axis. */
const DAY = 86400000;
const left = 66, right = 906, top = 12, bottom = 93;
const palette = ['#333f43', '#39709c', '#17715c', '#ad7329'];
const ms = day => Date.parse(day + 'T00:00:00Z');
const iso = time => new Date(time).toISOString().slice(0, 10);
const number = (value, unit) => (unit === '%' && value > 0 ? '+' : '') + value.toFixed(unit === '%' ? 1 : 2) + (unit === '%' ? '%' : ' ' + unit);
const monthIndex = date => Number(date.slice(0, 4)) * 12 + Number(date.slice(5, 7));

function sourceURL(value) {
  if (!value) return '';
  const url = new URL(value, location.href);
  return ['https:', 'http:'].includes(url.protocol) ? esc(url.href) : '';
}

function missedRelease(a, b, cadence) {
  if (cadence === 0) {
    for (let t = ms(a.published) + DAY; t < ms(b.published); t += DAY) {
      if (![0, 6].includes(new Date(t).getUTCDay())) return true;
    }
    return false;
  }
  const distance = monthIndex(b.period) - monthIndex(a.period);
  // NBS publishes January and February together after the Spring Festival.
  if (cadence === 1 && a.period.endsWith('-12') && b.period.endsWith('-02') && distance === 2) return false;
  return distance > cadence;
}

function seriesPath(item, from, to, x, y) {
  const points = item.points;
  const parts = [], dots = [], known = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i], at = ms(p.published), py = y(p.value);
    const next = points[i + 1];
    if (at >= from && at <= to && item.cadence) {
      dots.push(`<circle cx="${x(at)}" cy="${py}" r="3.1"/>`);
    }
    if (item.cadence) {
      const gap = next && missedRelease(p, next, item.cadence);
      const end = gap ? at : Math.min(to, next ? ms(next.published) : to);
      if (gap && at <= to && ms(next.published) >= from) {
        known.push(`M${x(Math.max(at, from))} ${py}H${x(Math.min(ms(next.published), to))}`);
      }
      if (at > to || end < from) continue;
      parts.push(`M${x(Math.max(at, from))} ${py}H${x(end)}`);
      if (next && !gap && ms(next.published) <= to) parts.push(`V${y(next.value)}`);
    } else if (at >= from && at <= to) {
      const prev = i && points[i - 1];
      parts.push(`${!prev || ms(prev.published) < from || missedRelease(prev, p, 0) ? 'M' : 'L'}${x(at)} ${py}`);
      if (points.length === 1) dots.push(`<circle cx="${x(at)}" cy="${py}" r="2.5"/>`);
    }
  }
  return `<g fill="${item.color}"><path data-driver-series="${esc(item.label)}" d="${parts.join(' ')}" fill="none" stroke="${item.color}" stroke-width="2" vector-effect="non-scaling-stroke"/>${known.length ? `<path d="${known.join(' ')}" fill="none" stroke="${item.color}" stroke-dasharray="3 5" opacity=".55" vector-effect="non-scaling-stroke"/>` : ''}${dots.join('')}</g>`;
}

export function renderDriverChart(host, data, macro, days) {
  const end = ms(data.cutoff);
  const prices = data.chart.slice(-days);
  const start = prices.length >= days ? ms(prices[0].date) : end - Math.round(days * 7 / 5) * DAY;
  const x = t => left + (t - start) / Math.max(DAY, end - start) * (right - left);
  const profile = data.drivers, quote = data.coverage[0];
  const micro = profile.series.map((item, i) => ({...item, color: palette[2 + i], cadence: profile.cadence}));
  const macroItem = {label: profile.macro_label, unit: '%', points: macro?.points || [], color: palette[1], cadence: 1};
  const stock = {label: data.company, color: palette[0], unit: data.modes[0].lanes[0].items[0].unit, cadence: 0,
    points: prices.map(row => ({published: row.date, period: row.date, value: row.values[quote.code], url: quote.url, source: quote.source}))};
  const lanes = [
    {name: '股价', title: '未复权收盘', items: [stock], note: ''},
    {name: '宏观', title: profile.macro_label, items: [macroItem], note: [profile.macro_note, macro?.message].filter(Boolean).join(' '), zero: true,
      empty: macro ? (macro.message || '截至所选日期，已收录的原表中暂无可用数据。') : '正在读取国家统计局原表…'},
    {name: '微观', title: micro.length === 1 ? micro[0].label : data.company + '经营指标', items: micro, note: profile.micro_note},
  ];
  let focusDay = host.dataset.focusDay || data.cutoff;
  let pinned = host.dataset.pinned === 'yes';

  function track(lane, index) {
    const visible = lane.items.flatMap(s => {
      const prior = s.cadence ? s.points.filter(p => ms(p.published) < start).at(-1) : null;
      return [...(prior ? [prior] : []), ...s.points.filter(p => ms(p.published) >= start && ms(p.published) <= end)];
    });
    const empty = !visible.length;
    const values = visible.map(p => p.value);
    if (lane.zero) values.push(0);
    const min = Math.min(...values), max = Math.max(...values);
    const pad = Math.max((max - min) * .12, Math.abs(max) * .015, .1);
    const low = min - pad, high = max + pad;
    const y = v => top + (high - v) / (high - low) * (bottom - top);
    const unit = lane.items[0]?.unit || '';
    const ticks = [max, (min + max) / 2, min].filter((v, i, a) => !i || v !== a[i - 1]);
    const grid = ticks.map(v => `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" class="driver-grid"/><text x="${left-9}" y="${y(v)+4}" text-anchor="end">${v.toFixed(unit === '%' ? 1 : 2)}</text>`).join('');
    const chart = empty ? `<p class="market-note">${esc(lane.empty || '截至所选日期尚无可定位的原始数据。')}</p>` :
      `<svg data-driver-plot viewBox="0 0 925 114" aria-label="${esc(lane.title)}，单位${esc(unit)}">
        ${grid}${lane.zero && low < 0 && high > 0 ? `<line class="driver-zero" x1="${left}" x2="${right}" y1="${y(0)}" y2="${y(0)}"/>` : ''}
        ${lane.items.map(s => seriesPath(s,start,end,x,y)).join('')}
        <line data-driver-guide class="driver-guide" x1="${right}" x2="${right}" y1="5" y2="${bottom+4}"/>
        <text x="${left}" y="111">${iso(start)}</text><text x="${right}" y="111" text-anchor="end">${data.cutoff}</text></svg>`;
    return `<section class="driver-track" data-driver-track="${index}"><header><div><span class="driver-kicker">${lane.name}</span>
      <h3>${esc(lane.title)}</h3></div><div data-driver-value></div></header>${chart}
      ${lane.note ? `<p class="driver-note">${esc(lane.note)}</p>` : ''}</section>`;
  }
  host.innerHTML = `<div class="driver-board" tabindex="0" aria-label="三轨对照图，可用左右方向键选择日期">
    <div class="driver-guidebar"><span>按公开日对齐 · 各轨独立刻度</span><span data-driver-day></span></div>
    ${lanes.map(track).join('')}<p class="driver-help">移动指针查看当日已知值，点击固定或解锁。圆点标记实际披露，虚线延续缺报期间最后已知值。点击读数下的日期可打开来源。</p></div>`;
  const board = host.firstElementChild;
  function inspect(day, showLatest = false) {
    focusDay = host.dataset.focusDay = day;
    host.dataset.pinned = pinned ? 'yes' : 'no';
    board.querySelector('[data-driver-day]').textContent = day + (pinned ? ' · 已固定' : '');
    for (const guide of board.querySelectorAll('[data-driver-guide]')) {
      guide.setAttribute('x1',x(ms(day))); guide.setAttribute('x2',x(ms(day)));
    }
    for (const [i,lane] of lanes.entries()) {
      const readout = board.querySelector(`[data-driver-track="${i}"] [data-driver-value]`);
      readout.innerHTML = lane.items.map(item => {
        const p = item.cadence || showLatest ? item.points.filter(point => point.published <= day).at(-1) : item.points.find(point => point.published === day);
        if (!p) return `<span class="driver-reading">${esc(item.label)} · ${item.cadence ? '尚无披露' : '当日无收盘'}</span>`;
        const url = sourceURL(p.url);
        const period = item.unit === '%' ? `${p.period.slice(0,4)}年1—${Number(p.period.slice(5,7))}月` : p.period;
        const ref = item.cadence ? `${period} · ${p.published} 公开` : `${p.published} ${showLatest && p.published < day ? '最近收盘' : '收盘'}`;
        return `<span class="driver-reading"><b style="color:${item.color}">${lane.items.length>1 ? esc(item.label)+' ' : ''}${esc(number(p.value,item.unit))}</b>
          ${url ? `<a href="${url}" target="_blank" rel="noopener">${esc(ref)} ↗</a>` : esc(ref)}</span>`;
      }).join('');
    }
  }
  for (const svg of board.querySelectorAll('[data-driver-plot]')) {
    const pointed = event => {
      const box = svg.getBoundingClientRect(), fraction = ((event.clientX - box.left) * 925 / box.width - left) / (right - left);
      return iso(start + Math.round(Math.max(0, Math.min(1, fraction)) * (end - start) / DAY) * DAY);
    };
    svg.onpointermove = e => { if (!pinned) inspect(pointed(e)); };
    svg.onclick = e => { pinned = !pinned; inspect(pointed(e)); };
  }
  board.onkeydown = e => {
    if (!['ArrowLeft','ArrowRight','Escape'].includes(e.key)) return;
    e.preventDefault(); pinned = e.key !== 'Escape';
    inspect(pinned ? iso(Math.max(start, Math.min(end, ms(focusDay) + (e.key === 'ArrowRight' ? DAY : -DAY)))) : data.cutoff);
  };
  inspect(focusDay, !pinned && focusDay === data.cutoff);
}
