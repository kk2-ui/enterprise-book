'use strict';

function observationValue(value, unit) {
  if (value == null) return '—';
  if (unit === '股') return value.toLocaleString('zh-CN') + ' 股';
  return value.toFixed(unit === '欧元/股' ? 4 : 2) + (unit === '%' ? '%' : unit === '指数' ? '' : ' ' + unit);
}

function observationControls(state) {
  return `<div class="market-controls">
    <label>窗口 <select data-observation-days>${[60, 120, 270].map(days =>
      `<option value="${days}" ${days === state.days ? 'selected' : ''}>${days === 270 ? '约一年' : days + ' 个工作日'}</option>`).join('')}</select></label>
    <label>历史截止 <input data-observation-date type="date" value="${esc(state.date)}" ${state.limit ? `max="${esc(state.limit)}"` : ""}></label>
    <button type="button" class="btn secondary" data-observation-latest ${state.date && !state.limit ? '' : 'hidden'}>最新</button>
    <button class="btn secondary" type="button" data-observation-refresh disabled>更新行情</button>
  </div>`;
}

function observationDetails(data) {
  const refresh = data.refresh || {};
  const codes = [...data.coverage.map(item => item.code), ...(data.observation === 'haier' ? ['CFETS'] : [])];
  const errors = Object.entries(refresh.errors || {}).filter(([code]) => codes.includes(code));
  const lagging = Object.entries(refresh.lagging || {}).filter(([code]) => codes.includes(code));
  const lastCheck = refresh.finished_at && new Date(refresh.finished_at).toLocaleString('zh-CN', {
    timeZone: 'Asia/Hong_Kong', hour12: false,
  });
  const warnings = `${errors.length ? `<p class="market-note" data-observation-source-errors>${errors.map(([code]) => esc(code)).join('、')} 更新未成功。可展开查看结果。</p>` : ''}
  ${lagging.length ? `<p class="market-note" data-observation-source-lag>${lagging.map(([code, state]) => `${esc(code)} 源数据更新至 ${esc(state.last)}，已检查到 ${esc(state.checked_through)}`).join('。')}。${data.observation === 'company' ? '可点击「更新行情」重新获取。' : '稍后自动重试。'}</p>` : ''}`;
  const body = `
    <p class="market-note">按各市场收盘时间和中间价发布时间自动拉取。${lastCheck ? '最近尝试 ' + esc(lastCheck) + '（香港时间）。' : ''}</p>
    ${errors.length ? `<ul>${errors.map(([code, message]) => `<li>${esc(code)} · ${esc(message)}</li>`).join('')}</ul>` : ''}
    <ul>${data.coverage.map(source => `<li>${source.url
      ? `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.label)} · ${esc(source.source)} ↗</a> · ${esc(source.start)} 至 ${esc(source.end)} · ${source.count} 条`
      : esc(source.code) + ' · 截至所选日期暂无已取得的数据'}</li>`).join('')}</ul>`;
  return {warnings, body};
}

// Each chart supplies its own date scale and shares the same research panel.
function marketWaveItems(data, dates) {
  if (!data?.code || !dates.length) return [];
  const overlaps = wave => wave.start <= dates.at(-1) && wave.end >= dates[0];
  return [
    ...data.reviewed.filter(overlaps).reverse(),
    ...data.pending.filter(overlaps).reverse().slice(0, 3),
  ];
}

function marketWaveBands(items, dates, x, top, bottom) {
  return items.map((wave, index) => {
    const first = dates.findIndex(day => day >= wave.start);
    const last = dates.findLastIndex(day => day <= wave.end);
    if (first < 0 || last < first) return '';
    const color = wave.notes ? '#287264' : '#936324';
    const label = (wave.notes ? '研' : '待') + (index + 1);
    const cx = x(last) - 12;
    const cy = top + 22 + index % 3 * 18;
    const title = wave.notes ? wave.notes.at(-1).title : '待核证据 ' + wave.change + '%';
    return `<g>
      <rect x="${x(first)}" y="${top}" width="${Math.max(2, x(last) - x(first))}" height="${bottom - top}" fill="${color}" opacity=".08" pointer-events="none" />
      <g role="button" tabindex="0" data-wave-marker="${esc(wave.id)}" aria-label="${esc(wave.start + ' 至 ' + wave.end + ' ' + title)}" style="cursor:pointer">
        <title>${esc(title)}</title>
        <rect x="${cx - 13}" y="${cy - 10}" width="26" height="19" rx="4" fill="${color}" />
        <text x="${cx}" y="${cy + 3}" text-anchor="middle" font-size="11" style="fill:#fff;pointer-events:none">${label}</text>
      </g>
    </g>`;
  }).join('');
}

function renderMarketWavePanel(panel, items, threshold, selected = '') {
  if (!panel) return;
  const wave = items.find(item => item.id === selected) || items[0];
  const label = item => item.start + ' 至 ' + item.end + (item.notes ? ' · 已审核' : ' · 待核证');
  const link = source => /^https?:\/\//.test(source.url)
    ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.label)} ↗</a>` : '';
  const renderNote = note => `<article style="margin:.6em 0"><time datetime="${esc(note.date)}">${esc(note.date)}</time>
    · ${esc(note.kind)}　<strong>${esc(note.title)}</strong><p style="margin:.25em 0">${esc(note.text)}</p>
    <div>${note.sources.map(link).filter(Boolean).join(' · ')}</div></article>`;
  panel.innerHTML = `<section style="margin:1em 0;padding:.75em 1em;border:1px solid #cbd9d3;border-radius:6px;font-size:13px;line-height:1.6" aria-label="波段归因">
    <strong>波段归因</strong>
    ${wave ? `<div style="display:flex;gap:.5em;flex-wrap:wrap;margin:.45em 0">
      ${items.map((item,i) => `<button type="button" data-wave-select="${esc(item.id)}" aria-pressed="${item === wave}">
        ${item.notes ? '研' : '待'}${i + 1}　${esc(label(item))}</button>`).join('')}
    </div>${wave.notes ? `${renderNote(wave.notes.at(-1))}
      ${wave.notes.length > 1 ? `<details><summary>关键日期与原件</summary>${wave.notes.slice(0, -1).map(renderNote).join('')}</details>` : ''}`
      : `<p>已列入待研究。自 ${esc(wave.start)} 至 ${esc(wave.end)} 股价变动 ${esc(wave.change)}%，等待核对公告、行业变化和市场资金证据。</p>`}`
      : `<p>该窗口暂无已审核案例或达到 ${esc(threshold ?? 7)}% 的待核波段。</p>`}
  </section>`;
  for (const button of panel.querySelectorAll('[data-wave-select]')) {
    button.onclick = () => renderMarketWavePanel(panel, items, threshold, button.dataset.waveSelect);
  }
}

function bindMarketWaveMarkers(svg, panel, items, threshold) {
  if (!svg || !panel) return;
  for (const marker of svg.querySelectorAll('[data-wave-marker]')) {
    const select = event => {
      event.stopPropagation();
      renderMarketWavePanel(panel, items, threshold, marker.dataset.waveMarker);
      panel.querySelector('button[aria-pressed="true"]')?.focus();
    };
    marker.addEventListener('click', select);
    marker.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        select(event);
      }
    });
  }
}

function observationExtraCharts(section, data, mode, days) {
  section.innerHTML = `<label>走势 <select data-observation-mode>${data.modes.map(item =>
    `<option value="${esc(item.key)}" ${item.key === mode.key ? 'selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label>
    ${mode.lanes.map((lane, index) => `<div class="observation-lane" data-observation-lane="${index}">
      <div class="observation-legend">${lane.items.map(item => `<span><i class="ob-color-${item.color}"></i>${esc(item.label)} · ${esc(item.unit)}</span>`).join('')}</div>
      <div class="market-plot observation-plot"></div></div>`).join('')}
    <p class="observation-readout market-note"></p>
    ${mode.normalize ? '<p class="market-note">从窗口内首个价格和汇率齐备的交易日起，以 100 为基准。</p>' : ''}`;
  drawObservation(section, data, mode, days);
}

function observationPath(rows, item, x, y) {
  let drawing = false;
  let path = '';
  const dots = [];
  for (const [index, row] of rows.entries()) {
    const value = row.values[item.key];
    if (value == null) {
      drawing = false;
      continue;
    }
    const px = x(index).toFixed(1);
    const py = y(value).toFixed(1);
    path += `${drawing ? 'L' : 'M'}${px},${py} `;
    if (!drawing && rows[index + 1]?.values[item.key] == null) {
      dots.push(`<circle cx="${px}" cy="${py}" r="2.6" />`);
    }
    drawing = true;
  }
  return `<g class="ob-color-${item.color}"><path data-observation-series="${esc(item.key)}" d="${path.trim()}" />${dots.join('')}</g>`;
}

function drawObservation(root, data, mode, days) {
  const windowRows = data.chart.slice(-days);
  const keys = mode.normalize ? mode.lanes.flatMap(lane => lane.items.map(item => item.key)) : [];
  const first = mode.normalize ? windowRows.findIndex(row => keys.every(key => row.values[key] > 0)) : -1;
  const rows = mode.normalize ? windowRows.map((row, index) => ({
    ...row,
    values: Object.fromEntries(keys.map(key => [key, first < 0 || index < first || row.values[key] == null
      ? null : 100 * row.values[key] / windowRows[first].values[key]])),
  })) : windowRows;
  const readout = root.querySelector('.observation-readout');
  const wavePanel = root.parentElement.querySelector('[data-wave-panel]');
  const waveDates = rows.map(row => row.date);
  const waveItems = marketWaveItems(data.attribution, waveDates);
  if (wavePanel) renderMarketWavePanel(wavePanel, waveItems, data.attribution?.threshold_pct);
  const hosts = [...root.querySelectorAll('.observation-plot')];
  function inspect(index) {
    const row = rows[index];
    readout.textContent = row.date + ' · ' + mode.lanes.flatMap(lane => lane.items).map(item => {
      const value = row.values[item.key];
      const missing = item.key === 'd_volume' ? '无价量记录' : '无可用数据';
      return item.label + ' ' + (value == null ? missing : observationValue(value, item.unit));
    }).join('　');
    if (row.values.d_volume === 0) readout.textContent += '　D 股零成交';
    for (const guide of root.querySelectorAll('.observation-guide')) {
      const px = Number(guide.dataset.left) + index / Math.max(1, rows.length - 1) * Number(guide.dataset.span);
      guide.setAttribute('x1', px);
      guide.setAttribute('x2', px);
    }
  }

  for (const [index, lane] of mode.lanes.entries()) {
    const host = hosts[index];
    const active = lane.items.flatMap(item => rows.map(row => row.values[item.key]).filter(value => value != null));
    if (active.length === 0) {
      host.innerHTML = '<p class="market-note">所选日期范围暂无可用数据。</p>';
      continue;
    }
    const width = Math.max(420, Math.round(host.getBoundingClientRect().width || 760));
    const height = lane.bars ? 112 : 180;
    const left = 61, right = width - 15, top = 11, bottom = height - 24;
    const span = right - left;
    const x = i => rows.length === 1 ? left : left + i / (rows.length - 1) * span;
    const offer = index === 0 && data.events.find(event => event.offer_mode === mode.key
      && rows.some(row => row.date >= event.start && row.date <= event.end));
    const min = Math.min(...active, ...(offer ? [offer.offer] : []));
    const max = Math.max(...active, ...(offer ? [offer.offer] : []));
    const pad = Math.max((max - min) * .09, Math.abs(max) * .006, .001);
    const low = lane.bars ? 0 : min - pad, high = max + pad;
    const y = value => bottom - (value - low) / (high - low) * (bottom - top);
    const ticks = [0, .5, 1].map(fraction => {
      const v = low + fraction * (high - low), py = y(v);
      const label = lane.bars ? Math.round(v).toLocaleString('zh-CN') : v.toFixed(2);
      return `<line x1="${left}" x2="${right}" y1="${py}" y2="${py}" class="market-gridline"/><text x="${left - 6}" y="${py + 4}" text-anchor="end">${label}</text>`;
    }).join('');
    const tab = x(1) - x(0);
    const bars = active.length && lane.bars ? rows.map((row, i) => {
      const v = row.values[lane.items[0].key];
      if (v == null) return '';
      const w = Math.max(1.3, Math.min(Math.abs(tab) * .68, 8));
      return `<rect x="${x(i) - w / 2}" width="${w}" y="${y(v)}" height="${Math.max(1, bottom - y(v))}" class="observation-bar" />`;
    }).join('') : '';
    const lines = lane.bars ? bars : lane.items.map(item => observationPath(rows, item, x, y)).join('');
    let band = '';
    if (offer) {
      const start = rows.findIndex(row => row.date >= offer.start);
      const end = rows.findLastIndex(row => row.date <= offer.end);
      const yOffer = y(offer.offer).toFixed(1);
      band = `<rect x="${x(start)}" width="${Math.max(x(end) - x(start), 1)}" y="${top}" height="${bottom - top}" class="observation-band"/>
        <line class="observation-offer" x1="${x(start)}" x2="${x(end)}" y1="${yOffer}" y2="${yOffer}"><title>€1.87 要约价 · 仅接受期 · 受参与条件限制</title></line>`;
    }
    const pins = index === 0 ? data.events.map(event => {
      const plotOn = event.plot_on || event.date;
      if (plotOn < rows[0].date) return '';
      const at = rows.findIndex(row => row.date >= plotOn);
      if (at < 0) return '';
      return `<a href="${esc(event.url)}" target="_blank" rel="noopener" aria-label="${esc(event.date + ' ' + event.label)}"><title>${esc(event.date + ' ' + event.label)}</title>
        <line x1="${x(at)}" x2="${x(at)}" y1="${top + 6}" y2="${bottom}" class="observation-event"/>
        <circle cx="${x(at)}" cy="${top + 5}" r="3.8" class="observation-pin"/></a>`;
    }).join('') : '';
    host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(lane.items.map(item => item.label).join('、'))}">
      ${ticks}${band}${lines}
      <text x="${left}" y="${height - 4}">${esc(rows[0].date)}</text>
      ${rows.length > 1 ? `<text x="${right}" y="${height - 4}" text-anchor="end">${esc(rows.at(-1).date)}</text>` : ''}
      <line data-left="${left}" data-span="${span}" y1="${top}" y2="${bottom}" class="observation-guide"/>${pins}${index === 0 && wavePanel ? marketWaveBands(waveItems, waveDates, x, top, bottom) : ''}
    </svg>`;
    const svg = host.querySelector('svg');
    if (index === 0) bindMarketWaveMarkers(svg, wavePanel, waveItems, data.attribution?.threshold_pct);
    svg.onpointermove = event => {
      const box = host.getBoundingClientRect();
      const px = (event.clientX - box.left) * width / box.width;
      inspect(Math.min(rows.length - 1, Math.max(0, Math.round((px - left) / span * (rows.length - 1)))));
    };
  }
  if (rows.some(row => mode.lanes.some(lane => lane.items.some(item => row.values[item.key] != null)))) {
    inspect(rows.length - 1);
  }
}

function renderCompanyObservation(root, data, days) {
  const last = data.chart.at(-1);
  const code = data.coverage[0]?.code;
  const mode = data.modes[0];
  const quote = last && observationValue(last.values[code], mode.lanes[0].items[0].unit);
  const value = data.valuation;
  const sources = observationDetails(data);
  root.innerHTML = `<div class="observation-company">
    <section class="observation-section" data-observation-section="trend">
      <div class="section-head"><div><h2 class="section-heading">${esc(data.company)}${data.drivers ? '股价、行业与经营走势' : '股价走势'}</h2>
      <p class="section-sub">观察截至 ${esc(data.cutoff)}${data.historical_limit ? ' · 本版固定截止日 ' + esc(data.historical_limit) : ''}</p></div></div>
      ${data.drivers ? '<div data-company-drivers></div>' : last ? `<p class="market-note">${esc(code)} · ${esc(last.date)} · 未复权收盘 <strong>${esc(quote)}</strong></p><div data-company-price-chart></div>`
        : `<p class="market-note">${code ? '所选时段没有可用日线。' : '未登记受支持的沪深港股票代码。'}</p>`}
      ${!data.drivers && data.attribution?.code ? '<div data-wave-panel></div>' : ''}
    </section>
    <section class="observation-section" data-observation-section="operating">
      <h2 class="section-heading">经营披露</h2>
      <div class="observation-cards">${data.cards.map(card => `<div class="observation-card">
        <span>${esc(card.period)} · ${esc(card.published)} 公开</span><h4>${esc(card.title)}</h4>
        <dl>${card.metrics.map(([name, number]) => `<div><dt>${esc(name)}</dt><dd>${esc(number)}</dd></div>`).join('')}</dl>
        ${card.sources.map(([label, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>`).join(' · ')}
      </div>`).join('') || '<p class="market-note">截至所选日期暂无可用的结构化经营披露。</p>'}</div>
    </section>
    <section class="observation-section" data-observation-section="valuation">
      <h2 class="section-heading">本版现金与估值</h2>
      ${value.url ? `<p>${esc(value.title)} · 信息时点 ${esc(value.date)} · ${esc(value.published_on)} 成版</p>
        <div class="observation-cards">
        ${value.cash ? `<div><span>研究现金</span><strong>${esc(value.cash)}</strong><p>${esc(value.cash_label || '')}</p></div>` : ''}
        ${value.value ? `<div><span>本版条件价值</span><strong>${esc(value.value)}</strong><p>${esc(value.value_label || '')}</p></div>` : ''}
        </div><a data-observation-edition href="${esc(value.url)}">打开本版现金与估值 →</a>`
        : `<p class="market-note">${esc(value.reason)}</p>`}
    </section>
    ${sources.warnings}<details class="observation-details"><summary>行情来源与覆盖</summary>${sources.body}</details>
  </div>`;
  const chart = root.querySelector('[data-company-price-chart]');
  if (chart) observationExtraCharts(chart, data, mode, days);
  else if (!data.drivers) renderMarketWavePanel(root.querySelector('[data-wave-panel]'), [], data.attribution?.threshold_pct);
}

function bindMarketObservation(root) {
  const cid = root.dataset.marketCompany;
  const edition = root.dataset.observationEdition;
  let limit = root.dataset.observationLimit;
  let data, renderAtlas, renderDrivers, poll, resize;
  let windowChosen = false;
  let requestSeq = 0;
  let refreshing = false;
  let extraOpen = false;
  let extraMode = 'd';
  const requested = new URLSearchParams(location.hash.split('?')[1]).get('market_as_of') || '';
  const view = {
    days: 120, limit, date: limit && (!requested || requested > limit) ? limit : requested,
    mode: '', pinnedIdx: null, hoverIdx: null, activeEventId: null,
  };

  let running = false;
  const endpoint = `/api/companies/${encodeURIComponent(cid)}/market-context`;
  root.innerHTML = `<header class="market-heading"><h2>市场观察</h2>${observationControls(view)}</header>
    <p class="market-note" role="status" data-observation-message hidden></p>
    <button type="button" class="btn secondary" data-observation-retry hidden>重新读取</button>
    <div data-observation-content></div>`;
  const content = root.querySelector('[data-observation-content]');
  const button = root.querySelector('[data-observation-refresh]');
  const latest = root.querySelector('[data-observation-latest]');
  const retry = root.querySelector('[data-observation-retry]');
  const note = root.querySelector('[data-observation-message]');
  button.onclick = refresh;
  latest.onclick = () => changeDate('');
  retry.onclick = () => load(false);
  root.querySelector('[data-observation-date]').onchange = event => changeDate(event.target.value);
  root.querySelector('[data-observation-days]').onchange = event => {
    windowChosen = true;
    view.days = Number(event.target.value);
    load();
  };

  function updateButton() {
    const busy = refreshing || running;
    button.disabled = busy || !data || !data.coverage.length;
    const label = busy ? '正在更新…' : '更新行情';
    if (button.textContent !== label) button.textContent = label;
  }

  function message(text = '', failed = false) {
    note.textContent = text;
    note.hidden = !text;
    retry.hidden = !failed;
  }

  function drawExtra() {
    const details = content.querySelector('[data-more-charts]');
    if (!details?.open || !data) return;
    const mode = data.modes.find(item => item.key === extraMode) || data.modes[0];
    observationExtraCharts(details.querySelector('[data-extra-chart]'), data, mode, view.days);
  }

  function mount() {
    content.innerHTML = `<div data-market-atlas></div>
      ${data.observation === 'haier' ? `<details class="observation-details" data-more-charts ${extraOpen ? 'open' : ''}>
        <summary>单市场、折价与汇率分解</summary><div data-extra-chart></div></details>` : ''}
      <div data-source-warnings></div><details class="observation-details"><summary>行情来源与覆盖</summary>
        <div data-source-body></div></details>`;
    const details = content.querySelector('[data-more-charts]');
    if (!details) return;
    details.ontoggle = () => { extraOpen = details.open; drawExtra(); };
    details.onchange = event => { extraMode = event.target.value; drawExtra(); };
    let lastWidth = details.getBoundingClientRect().width;
    resize = new ResizeObserver(entries => {
      const width = entries[0].contentRect.width;
      if (!root.isConnected) resize.disconnect();
      else if (width !== lastWidth) drawExtra();
      lastWidth = width;
    });
    resize.observe(details);
  }

  function applySnapshot(next) {
    if (next.historical_limit) {
      limit = view.limit = next.historical_limit;
      const input = root.querySelector('[data-observation-date]');
      input.max = limit;
      input.value = view.date = next.cutoff;
      latest.hidden = true;
    }
    if (next.observation === 'company') {
      data = next;
      if (next.drivers && !windowChosen) {
        view.days = 270;
        root.querySelector('[data-observation-days]').value = String(view.days);
      }
      renderCompanyObservation(content, next, view.days);
      if (next.drivers) {
        const host = content.querySelector('[data-company-drivers]');
        const request = requestSeq;
        const params = new URLSearchParams({as_of: next.cutoff});
        if (edition) params.set('edition', edition);
        renderDrivers(host, next, null, view.days);
        api(endpoint + '/macro?' + params).then(macro => {
          if (current(request)) renderDrivers(host, next, macro, view.days);
        }).catch(() => {
          if (current(request)) renderDrivers(host, next, {points: [], message: '行业原表读取失败，可重新读取本页。'}, view.days);
        });
      }
      return;
    }
    const previous = data;
    data = next;
    if (!previous) mount();
    if (!previous || JSON.stringify([previous.atlas, previous.attribution]) !== JSON.stringify([next.atlas, next.attribution])) {
      if (previous) {
        const before = previous.atlas.mainChart, after = next.atlas.mainChart;
        const pinned = before.timeline[view.pinnedIdx]?.date;
        const index = after.timeline.findIndex(row => row.date === pinned);
        view.pinnedIdx = index >= 0 ? index : null;
        view.hoverIdx = null;
        const event = before.events.find(item => item.id === view.activeEventId);
        view.activeEventId = event
          ? after.events.find(item => item.date === event.date && item.title === event.title)?.id ?? null
          : null;
      }
      const links = state.companies.filter(hasMarketObservation).map(company => ({
        name: company.name, active: company.id === cid,
        url: '#/company/' + encodeURIComponent(company.id) + '/market' +
          (view.date ? '?market_as_of=' + encodeURIComponent(view.date) : ''),
      }));
      renderAtlas(content.querySelector('[data-market-atlas]'), next.atlas, view, links, next.attribution);
    }
    if (!previous || JSON.stringify([previous.chart, previous.events]) !== JSON.stringify([next.chart, next.events])) {
      drawExtra();
    }
    const sources = observationDetails(next);
    const oldSources = previous && observationDetails(previous);
    if (sources.warnings !== oldSources?.warnings) content.querySelector('[data-source-warnings]').innerHTML = sources.warnings;
    if (sources.body !== oldSources?.body) content.querySelector('[data-source-body]').innerHTML = sources.body;
  }

  function changeDate(date) {
    date = limit && (!date || date > limit) ? limit : date;
    view.date = date;
    root.querySelector('[data-observation-date]').value = date;
    latest.hidden = !date || Boolean(limit);
    const [path, query] = location.hash.split('?');
    const params = new URLSearchParams(query);
    if (date) params.set('market_as_of', date);
    else params.delete('market_as_of');
    history.replaceState(null, '', path + (params.size ? '?' + params : ''));
    load();
  }

  function current(request) {
    return request === requestSeq && root.isConnected;
  }

  function watch(request) {
    clearTimeout(poll);
    poll = setTimeout(async () => {
      if (!current(request)) return;
      try {
        const status = await api('/api/market-observation/refresh-status');
        if (!current(request)) return;
        if (status.running) watch(request);
        else load(false);
      } catch (error) {
        if (current(request)) message(error.message, true);
      }
    }, 2000);
  }

  async function refresh() {
    if (button.disabled) return;
    refreshing = true;
    updateButton();
    message();
    const request = requestSeq;
    try {
      const status = await api(endpoint + '/refresh', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({observation: 1, as_of: view.date || undefined, edition: edition || undefined}),
      });
      if (!root.isConnected) return;
      if (current(request) && status.running) {
        running = true;
        watch(request);
      } else {
        // The date/window may have changed while the update was starting.
        await load(false);
      }
    } catch (error) {
      if (current(request)) message(error.message, true);
    } finally {
      refreshing = false;
      updateButton();
    }
  }

  async function load(clear = true) {
    clearTimeout(poll);
    if (!root.isConnected) return;
    const request = ++requestSeq;
    if (clear) {
      resize?.disconnect();
      data = null;
      view.pinnedIdx = view.hoverIdx = view.activeEventId = null;
      content.replaceChildren();
    }
    message(data ? '' : '正在读取所选日期…');
    updateButton();
    const query = new URLSearchParams({observation: '1', layout: 'atlas', days: view.days});
    if (view.date) query.set('as_of', view.date);
    if (edition) query.set('edition', edition);
    try {
      const [next, module] = await Promise.all([api(endpoint + '?' + query), import('/market-atlas.js')]);
      if (!current(request)) return;
      if (next.drivers) {
        const driverModule = await import('/market-driver-chart.js');
        if (!current(request)) return;
        renderDrivers = driverModule.renderDriverChart;
      }
      renderAtlas = module.renderMarketAtlas;
      applySnapshot(next);
      running = Boolean(next.refresh?.running);
      updateButton();
      message();
      if (running) watch(request);
    } catch (error) {
      if (current(request)) message(error.message, true);
    }
  }

  load();
}
