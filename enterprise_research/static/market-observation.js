'use strict';

function observationValue(value, unit) {
  if (value == null) return '—';
  if (unit === '股') return value.toLocaleString('zh-CN') + ' 股';
  return value.toFixed(unit === '欧元/股' ? 4 : 2) + (unit === '%' ? '%' : unit === '指数' ? '' : ' ' + unit);
}

function observationControls(state, modes, running) {
  return `<div class="market-controls">
    <label>走势 <select data-observation-mode>${modes.map(mode =>
      `<option value="${esc(mode.key)}" ${mode.key === state.mode ? 'selected' : ''}>${esc(mode.label)}</option>`).join('')}</select></label>
    <label>窗口 <select data-observation-days>${[60, 120, 270].map(days =>
      `<option value="${days}" ${days === state.days ? 'selected' : ''}>${days === 270 ? '约一年' : days + ' 个工作日'}</option>`).join('')}</select></label>
    <label>历史截止 <input data-observation-date type="date" value="${esc(state.date)}"></label>
    ${state.date ? '<button type="button" class="btn secondary" data-observation-latest>最新</button>' : ''}
    <button class="btn secondary" type="button" data-observation-refresh ${running ? 'disabled' : ''}>${running ? '正在更新…' : '更新行情'}</button>
  </div>`;
}

function observationCards(cards) {
  if (!cards.length) return '<p class="market-note">截至所选日期，暂无已公开且口径可比的观察指标。</p>';
  return `<div class="observation-cards">${cards.map(card => `<article class="observation-card">
      <h4>${esc(card.title)}</h4>
      <p class="market-note">${esc(card.period)} · ${esc(card.published)} 披露</p>
      <dl>${card.metrics.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>
      <p>${esc(card.note)}</p>
      <div class="observation-sources">${card.sources.map(([title, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(title)} ↗</a>`).join('')}</div>
    </article>`).join('')}</div>`;
}

function observationValuation(valuation, prices) {
  if (!valuation.url) return `<p class="market-note">${esc(valuation.reason)}</p>`;
  return `<p class="market-note">${esc(valuation.date)} 研究快照 · ${esc(valuation.published_on)} 成版</p>
    <p><strong>${esc(valuation.cash)}</strong> · ${esc(valuation.summary)}</p>
    ${valuation.figure_url ? `<figure class="observation-figure"><a href="${esc(valuation.figure_url)}" target="_blank" rel="noopener"><img src="${esc(valuation.figure_url)}" alt="普通股现金情景和 A/H 价格要求" loading="lazy"></a></figure>` : ''}
    ${prices ? `<div class="observation-cards observation-prices">${prices.metrics.map(metric => `<article class="observation-card">
        <h4>${esc(metric.label)}</h4><strong>${metric.cash_yi.toFixed(1)} 亿元/年</strong>
        <p>折人民币 ${metric.price_cny.toFixed(2)} 元/股</p>
      </article>`).join('')}</div>
      <p class="market-note">${esc(prices.date)} 未复权收盘，同日人民币中间价，10% 股权回报率、投资者个人税前。按 <a href="${esc(prices.share_url)}" target="_blank" rel="noopener">${esc(prices.shares_on)} 月报登记已发行股本</a> ${prices.shares.toLocaleString('zh-CN')} 股测算。各市场收盘时刻不同。</p>` : ''}
    <a class="text-link" href="${esc(valuation.url)}" data-observation-edition>打开正式版 · 现金与估值 →</a>`;
}

function observationDetails(data) {
  const refresh = data.refresh || {};
  const codes = [...data.coverage.map(item => item.code), ...(data.observation === 'haier' ? ['CFETS'] : [])];
  const errors = Object.entries(refresh.errors || {}).filter(([code]) => codes.includes(code));
  const lagging = Object.entries(refresh.lagging || {}).filter(([code]) => codes.includes(code));
  const lastCheck = refresh.finished_at && new Date(refresh.finished_at).toLocaleString('zh-CN', {
    timeZone: 'Asia/Hong_Kong', hour12: false,
  });
  return `${errors.length ? `<p class="market-note" data-observation-source-errors>${errors.map(([code]) => esc(code)).join('、')} 更新未成功。可展开查看结果。</p>` : ''}
  ${lagging.length ? `<p class="market-note" data-observation-source-lag>${lagging.map(([code, state]) => `${esc(code)} 源数据更新至 ${esc(state.last)}，已检查到 ${esc(state.checked_through)}`).join('。')}。稍后自动重试。</p>` : ''}
  <details class="observation-details"><summary>行情来源与覆盖</summary>
    <p class="market-note">按各市场收盘时间和中间价发布时间自动拉取。${lastCheck ? '最近尝试 ' + esc(lastCheck) + '（香港时间）。' : ''}</p>
    ${errors.length ? `<ul>${errors.map(([code, message]) => `<li>${esc(code)} · ${esc(message)}</li>`).join('')}</ul>` : ''}
    <ul>${data.coverage.map(source => `<li>${source.url
      ? `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.label)} · ${esc(source.source)} ↗</a> · ${esc(source.start)} 至 ${esc(source.end)} · ${source.count} 条`
      : esc(source.code) + ' · 截至所选日期暂无已取得的数据'}</li>`).join('')}</ul>
  </details>`;
}

function observationMarkup(data, mode, heading) {
  const lanes = mode.lanes.map((lane, index) => `<div class="observation-lane" data-observation-lane="${index}">
    <div class="observation-legend">${lane.items.map(item => `<span><i class="ob-color-${item.color}"></i>${esc(item.label)} · ${esc(item.unit)}</span>`).join('')}</div>
    <div class="market-plot observation-plot"></div>
  </div>`).join('');
  const events = data.events.map(event => `<li><time>${esc(event.date)}</time> <a href="${esc(event.url)}" target="_blank" rel="noopener">${esc(event.label)} ↗</a> ${event.start ? `<span class="market-note">接受期 ${esc(event.start)} 至 ${esc(event.end)}（欧洲中部时间）</span>` : ''}${event.plot_on ? `<span class="market-note">图标位于下一交易日 ${esc(event.plot_on)}</span>` : ''}</li>`).join('');
  return heading + `<section class="observation-section" data-observation-section="trend">
      <h3>走势与事件</h3>${lanes}<p class="observation-readout market-note"></p>
      ${mode.normalize ? '<p class="market-note">窗口内首个三项齐全的交易日归一为 100，展示价格和汇率变化。</p>' : ''}
      ${data.observation === 'haier' && mode.key === 'cny' ? '<p class="market-note">以未复权收盘配对同日中间价。任一必要序列缺数，受影响的换算与折价断开。</p>' : ''}
      ${events ? `<details class="observation-details"><summary>披露与资本运作</summary><ul>${events}</ul></details>` : ''}
    </section>
    <section class="observation-section" data-observation-section="drivers"><h3>经营驱动</h3>${observationCards(data.cards)}</section>
    <section class="observation-section" data-observation-section="valuation"><h3>价格与现金要求</h3>${observationValuation(data.valuation, data.price_snapshot)}</section>
    ${observationDetails(data)}`;
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
      <line data-left="${left}" data-span="${span}" y1="${top}" y2="${bottom}" class="observation-guide"/>${pins}
    </svg>`;
    host.querySelector('svg').onpointermove = event => {
      const box = host.getBoundingClientRect();
      const px = (event.clientX - box.left) * width / box.width;
      inspect(Math.min(rows.length - 1, Math.max(0, Math.round((px - left) / span * (rows.length - 1)))));
    };
  }
  if (rows.some(row => mode.lanes.some(lane => lane.items.some(item => row.values[item.key] != null)))) {
    inspect(rows.length - 1);
  }
}

function bindMarketObservation(root) {
  const cid = root.dataset.marketCompany;
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const state = { date: params.get('market_as_of') || '', days: 270, mode: '' };
  let data;
  let requests = 0;
  let resize;
  let poll;

  function display(loading = false, error = '') {
    resize?.disconnect();
    if (!root.isConnected) return;
    const mode = data?.modes.find(mode => mode.key === state.mode) || data?.modes[0];
    const lastQuote = data?.chart.at(-1)?.date;
    const caption = loading ? '正在读取所选日期…' : data
      ? `观察截止 ${data.cutoff}${lastQuote ? ' · 最近行情 ' + lastQuote : ''}` : '';
    const heading = `<div class="market-heading">
        <div><h2>市场观察</h2><p class="market-note" role="status">${esc(caption)}</p></div>
        ${mode ? observationControls(state, data.modes, data.refresh?.running) : ''}
      </div>`;
    root.innerHTML = loading || error
      ? heading + (error ? `<p class="market-note">${esc(error)}</p><button class="btn secondary" data-observation-retry>重新读取</button>` : '')
      : observationMarkup(data, mode, heading);
    root.querySelector('[data-observation-mode]')?.addEventListener('change', event => {
      state.mode = event.target.value;
      display(loading, error);
    });
    root.querySelector('[data-observation-days]')?.addEventListener('change', event => {
      state.days = Number(event.target.value);
      display(loading, error);
    });
    root.querySelector('[data-observation-date]')?.addEventListener('change', event => {
      state.date = event.target.value;
      load();
    });
    root.querySelector('[data-observation-latest]')?.addEventListener('click', () => {
      state.date = '';
      load();
    });
    root.querySelector('[data-observation-retry]')?.addEventListener('click', () => load());
    root.querySelector('[data-observation-refresh]')?.addEventListener('click', refresh);
    if (loading || error || !mode) return;
    drawObservation(root, data, mode, state.days);
    resize = new ResizeObserver(() => {
      if (root.isConnected) drawObservation(root, data, mode, state.days);
      else resize.disconnect();
    });
    resize.observe(root.querySelector('[data-observation-section="trend"]'));
  }

  async function refresh(event) {
    event.currentTarget.disabled = true;
    try {
      await api(`/api/companies/${encodeURIComponent(cid)}/market-context/refresh`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({observation: 1}),
      });
      load(false);
    } catch (error) {
      display(false, error.message);
    }
  }

  async function load(showLoading = true) {
    clearTimeout(poll);
    if (!root.isConnected) return;
    const request = ++requests;
    if (showLoading) display(true);
    const query = new URLSearchParams({ observation: '1' });
    if (state.date) query.set('as_of', state.date);
    try {
      const next = await api(`/api/companies/${encodeURIComponent(cid)}/market-context?${query}`);
      if (request !== requests || !root.isConnected) return;
      data = next;
      if (!state.mode) state.mode = data.modes[0].key;
      display();
      if (data.refresh?.running) poll = setTimeout(() => load(false), 2000);
    } catch (error) {
      if (request === requests) display(false, error.message);
    }
  }

  load();
}
