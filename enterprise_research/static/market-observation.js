'use strict';

function observationValue(value, unit) {
  if (value == null) return '—';
  if (unit === '股') return value.toLocaleString('zh-CN') + ' 股';
  return value.toFixed(unit === '欧元/股' ? 4 : 2) + (unit === '%' ? '%' : unit === '指数' ? '' : ' ' + unit);
}

function observationControls(state, running) {
  return `<div class="market-controls">
    <label>窗口 <select data-observation-days>${[60, 120, 270].map(days =>
      `<option value="${days}" ${days === state.days ? 'selected' : ''}>${days === 270 ? '约一年' : days + ' 个工作日'}</option>`).join('')}</select></label>
    <label>历史截止 <input data-observation-date type="date" value="${esc(state.date)}"></label>
    ${state.date ? '<button type="button" class="btn secondary" data-observation-latest>最新</button>' : ''}
    <button class="btn secondary" type="button" data-observation-refresh ${running ? 'disabled' : ''}>${running ? '正在更新…' : '更新行情'}</button>
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
  let data, renderAtlas, poll, resize;
  let requestSeq = 0;
  let refreshing = false;
  let extraOpen = false;
  let extraMode = 'd';
  const view = {
    days: 120, date: new URLSearchParams(location.hash.split('?')[1]).get('market_as_of') || '',
    mode: '', pinnedIdx: null, hoverIdx: null, activeEventId: null,
  };

  function display(message = '', failed = false) {
    resize?.disconnect();
    if (!root.isConnected) return;
    const ready = data && !failed;
    root.innerHTML = `<header class="market-heading"><h2>市场观察</h2>
      ${observationControls(view, refreshing || data?.refresh?.running)}</header>
      ${message ? `<p class="market-note" role="status">${esc(message)}</p>` : ''}
      ${failed ? '<button type="button" class="btn secondary" data-observation-retry>重新读取</button>' : ''}
      ${ready ? '<div data-market-atlas></div>' : ''}
      ${ready && data.observation === 'haier' ? `<details class="observation-details" data-more-charts ${extraOpen ? 'open' : ''}>
        <summary>单市场、折价与汇率分解</summary><div data-extra-chart></div></details>` : ''}
      ${ready ? observationDetails(data) : ''}`;
    root.querySelector('[data-observation-date]').onchange = event => changeDate(event.target.value);
    const latest = root.querySelector('[data-observation-latest]');
    if (latest) latest.onclick = () => changeDate('');
    root.querySelector('[data-observation-days]').onchange = event => {
      view.days = Number(event.target.value);
      load();
    };
    root.querySelector('[data-observation-refresh]').onclick = refresh;
    const retry = root.querySelector('[data-observation-retry]');
    if (retry) retry.onclick = () => load();
    if (!ready) return;

    const links = state.companies.filter(hasMarketObservation).map(company => ({
      name: company.name, active: company.id === cid,
      url: '#/company/' + encodeURIComponent(company.id) + '/market' +
        (view.date ? '?market_as_of=' + encodeURIComponent(view.date) : ''),
    }));
    renderAtlas(root.querySelector('[data-market-atlas]'), data.atlas, view, links);
    const details = root.querySelector('[data-more-charts]');
    if (!details) return;
    const section = details.querySelector('[data-extra-chart]');
    const draw = () => {
      if (root.isConnected && details.open) {
        const mode = data.modes.find(item => item.key === extraMode) || data.modes[0];
        observationExtraCharts(section, data, mode, view.days);
      }
    };
    details.ontoggle = () => { extraOpen = details.open; if (extraOpen) draw(); };
    section.onchange = event => { extraMode = event.target.value; draw(); };
    if (details.open) draw();
    let lastWidth;
    resize = new ResizeObserver(entries => {
      const width = entries[0].contentRect.width;
      if (!root.isConnected) resize.disconnect();
      else if (width !== lastWidth && details.open) draw();
      lastWidth = width;
    });
    resize.observe(details);
  }

  function changeDate(date) {
    view.date = date;
    const [path, query] = location.hash.split('?');
    const params = new URLSearchParams(query);
    if (date) params.set('market_as_of', date);
    else params.delete('market_as_of');
    history.replaceState(null, '', path + (params.size ? '?' + params : ''));
    load();
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    const request = requestSeq;
    root.querySelector('[data-observation-refresh]').disabled = true;
    try {
      await api(`/api/companies/${encodeURIComponent(cid)}/market-context/refresh`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({observation: 1}),
      });
    } catch (error) {
      if (request === requestSeq) display(error.message, true);
      return;
    } finally {
      refreshing = false;
      const button = root.querySelector('[data-observation-refresh]');
      if (button) button.disabled = Boolean(data?.refresh?.running);
    }
    if (root.isConnected) load(false);
  }

  async function load(clear = true) {
    clearTimeout(poll);
    if (!root.isConnected) return;
    const request = ++requestSeq;
    if (clear) {
      data = null;
      display('正在读取所选日期…');
    }
    const query = new URLSearchParams({observation: '1', layout: 'atlas', days: view.days});
    if (view.date) query.set('as_of', view.date);
    try {
      const [next, module] = await Promise.all([
        api(`/api/companies/${encodeURIComponent(cid)}/market-context?${query}`), import('/market-atlas.js'),
      ]);
      if (request !== requestSeq || !root.isConnected) return;
      data = next;
      renderAtlas = module.renderMarketAtlas;
      view.pinnedIdx = view.hoverIdx = view.activeEventId = null;
      display();
      if (data.refresh?.running) poll = setTimeout(() => load(false), 2000);
    } catch (error) {
      if (request === requestSeq) display(error.message, true);
    }
  }

  load();
}
