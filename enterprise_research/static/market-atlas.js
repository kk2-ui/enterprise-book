function fmt(num, digits = 2) {
  if (num === null || num === undefined || Number.isNaN(Number(num))) return "休市/缺失";
  return Number(num).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

function niceDomain(values, padRatio = 0.12) {
  const valid = values.filter(v => v !== null && v !== undefined && !Number.isNaN(v));
  if (!valid.length) return { min: 0, max: 10, ticks: [0, 5, 10] };
  let min = Math.min(...valid);
  let max = Math.max(...valid);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  const paddedMin = Math.max(0, min - span * padRatio);
  const paddedMax = max + span * padRatio;
  const stepRaw = (paddedMax - paddedMin) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(stepRaw)));
  const norm = stepRaw / mag;
  let step = mag;
  if (norm > 5) step = 10 * mag;
  else if (norm > 2.5) step = 5 * mag;
  else if (norm > 1.5) step = 2 * mag;

  const niceMin = Math.floor(paddedMin / step) * step;
  const niceMax = Math.ceil(paddedMax / step) * step;
  const ticks = [];
  for (let v = niceMin; v <= niceMax + step * 0.001; v += step) {
    ticks.push(Number(v.toFixed(6)));
  }
  return { min: niceMin, max: niceMax, ticks };
}

/**
 * 构建严格断线的 SVG Path：遇到 null/undefined 立即断开，绝不跨缺失日期连线
 * 同时返回孤立有效点（前后均为 null 的单日交易点）与缺失区间，确保视觉完整准确
 */
function buildBrokenSeries(points) {
  let d = "";
  let inSegment = false;
  const segments = [];
  let currentSeg = [];

  points.forEach((pt, idx) => {
    if (pt.valid) {
      if (!inSegment) {
        d += `M ${pt.x.toFixed(2)} ${pt.y.toFixed(2)} `;
        inSegment = true;
        currentSeg = [pt];
      } else {
        d += `L ${pt.x.toFixed(2)} ${pt.y.toFixed(2)} `;
        currentSeg.push(pt);
      }
    } else {
      if (inSegment) {
        segments.push(currentSeg);
        currentSeg = [];
      }
      inSegment = false;
    }
    if (idx === points.length - 1 && currentSeg.length) {
      segments.push(currentSeg);
    }
  });

  const isolated = segments.filter(seg => seg.length === 1).map(seg => seg[0]);
  const breakCaps = [];
  points.forEach((pt, i) => {
    if (!pt.valid) return;
    const prevMissing = i > 0 && !points[i - 1].valid;
    const nextMissing = i < points.length - 1 && !points[i + 1].valid;
    if (prevMissing || nextMissing) breakCaps.push(pt);
  });

  return { pathD: d.trim(), isolated, breakCaps };
}

/**
 * 为两条序列在共同有效区间内生成折价填充多边形（遇到任一序列缺失立即断开填充）
 */
function buildBandAreaPaths(upperPts, lowerPts) {
  const areas = [];
  let segTop = [];
  let segBot = [];

  for (let i = 0; i < upperPts.length; i++) {
    if (upperPts[i].valid && lowerPts[i].valid) {
      segTop.push(upperPts[i]);
      segBot.push(lowerPts[i]);
    } else {
      if (segTop.length >= 2) {
        areas.push({ top: segTop, bot: segBot });
      }
      segTop = [];
      segBot = [];
    }
  }
  if (segTop.length >= 2) areas.push({ top: segTop, bot: segBot });

  return areas.map(({ top, bot }) => {
    const forward = top.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");
    const backward = [...bot].reverse().map(p => `L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");
    return `${forward} ${backward} Z`;
  });
}

// Gemini 绘制的市场观察图，数据与正式企业书共用同一披露截面。
export function renderMarketAtlas(host, company, state, companyLinks) {
  const shadow = host.shadowRoot || host.attachShadow({mode: 'open'});
  if (!shadow.firstChild) {
    shadow.innerHTML = '<link rel="stylesheet" href="/market-atlas.css"><div class="page-shell" id="app"></div>';
  }
  if (!state.mode) state.mode = company.mainChart.defaultMode;
  function renderPublication() {
    const comp = company;
    const mode = state.mode;
    const app = shadow.getElementById("app");
    app.innerHTML = `
      <header class="masthead">
        <div class="masthead-brand">
          <div class="masthead-title">市场观察图志</div>
          <div class="masthead-sub">企业书 · Gemini 设计</div>
        </div>
        <nav class="company-switcher" aria-label="切换公司">
          ${companyLinks.map(link => `<a class="company-btn ${link.active ? 'active' : ''}" href="${esc(link.url)}">${esc(link.name)}</a>`).join('')}
        </nav>
      </header>

      <section class="editorial-header">
        <div class="company-kicker">${esc(comp.name)} · ${esc(comp.codes)} · 数据截至 ${esc(comp.cutoff)}</div>
        <h1 class="company-headline">${esc(comp.headline)}</h1>
        <p class="company-deck">${esc(comp.deck)}</p>

        <div class="three-questions-strip">
          ${comp.threeQuestions.map(q => `
            <div class="q-card">

              <div class="q-title">${esc(q.title)}</div>
              <div class="q-metric">${esc(q.highlightMetric)}</div>
              <div class="q-takeaway">${esc(q.summary)}</div>
            </div>
          `).join("")}
        </div>
      </section>

      <!-- 模块一：走势与事件主图 -->
      <section class="section-block" data-observation-section="trend">
        <div class="section-top">
          <div>
            <div class="section-label">第一部分 · 走势与事件</div>
            <h2 class="section-heading">${esc(comp.mainChart.sectionTitle)}</h2>
            <p class="section-sub">${esc(comp.mainChart.sectionSub)}</p>
          </div>
          <div class="mode-group" aria-label="走势图模式">
            ${comp.mainChart.modes.map(m => `
              <button class="mode-btn ${m.id === mode ? "active" : ""}" aria-pressed="${m.id === mode}" data-mode="${esc(m.id)}">${esc(m.label)}</button>
            `).join("")}
          </div>
        </div>

        <div class="chart-hud">
          <div class="legend-row" id="chart-legend"></div>
          <div class="hud-readout" id="hud-readout"></div>
        </div>

        <div class="svg-stage" id="main-svg-stage">
          <div id="main-svg-mount"></div>
          <div class="floating-tooltip" id="chart-tooltip"></div>
        </div>

        <div class="events-tray" ${comp.mainChart.events.length ? '' : 'hidden'}>
          <div class="events-tray-title">关键公告与事件时间轴核验（点击卡片或图中编号定位日期，点击链接查阅原件）</div>
          <div class="events-list" id="events-list">
            ${comp.mainChart.events.map(ev => `
              <article class="event-card ${state.activeEventId === ev.id ? "active" : ""}" data-event-id="${esc(ev.id)}" data-event-date="${esc(ev.date)}">
                <div class="event-head">
                  <span class="event-badge"><span class="event-pin-num">${esc(ev.pin)}</span>公告</span>
                  <span>${ev.onChart ? '图上日期 ' + esc(ev.date) : '等待对应交易日行情'}</span>
                </div>
                <div class="event-title">${esc(ev.title)}</div>
                <div class="event-desc">${esc(ev.impact)}</div>
                <div class="provenance-bar">
                  <span>首次披露 ${esc(ev.firstDisclosed)}</span>
                  <a class="doc-link" href="${esc(ev.sourceUrl)}" target="_blank" rel="noopener noreferrer" >查看公告原件 ↗</a>
                </div>
              </article>
            `).join("")}
          </div>
        </div>
      </section>

      <!-- 下半部分：经营驱动 + 价格与现金要求 -->
      <div class="dual-grid">
        <!-- 模块二：经营驱动 -->
        <section class="section-block" data-observation-section="drivers" style="margin-top:0;">
          <div class="section-top">
            <div>
              <div class="section-label">第二部分 · 经营驱动与事实溯源</div>
              <h2 class="section-heading">${esc(comp.operating.sectionTitle)}</h2>
              <p class="section-sub">${esc(comp.operating.sectionSub)}</p>
            </div>
          </div>

          <div class="sub-svg-box" id="operating-svg-mount"></div>

          <div class="fact-stack">
            ${comp.operating.source ? `<p><a class="doc-link" target="_blank" rel="noopener" href="${esc(comp.operating.source)}">2025 年年度报告 · PDF 第 225 页 ↗</a> · 2026-03-27 披露</p>` : ''}
            ${comp.operating.facts.map(f=>`<article class="fact-item"><div class="fact-label">${esc(f.title)}</div>
              ${(comp.id === "petrochina" && f.title === "单位油气操作成本" ? [] : f.metrics).map(([name,value])=>`<div class="fact-top"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join("")}
              <div class="fact-body">${esc(f.note)}</div><div class="provenance-bar"><span>${esc(f.period)} · ${esc(f.published)} 披露</span>
              ${f.sources.map(([label,url])=>`<a class="doc-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>`).join(' ')}</div></article>`).join('')}
          </div>
        </section>

        <!-- 模块三：价格与现金要求 -->
        <section class="section-block" data-observation-section="valuation" style="margin-top:0;">
          <div class="section-top">
            <div>
              <div class="section-label">第三部分 · 价格与普通股正常现金主例</div>
              <h2 class="section-heading">${esc(comp.valuation.sectionTitle)}</h2>
              <p class="section-sub">${esc(comp.valuation.sectionSub)}</p>
            </div>
          </div>

          ${comp.valuation.linkedEdition ? `<p>${esc(comp.valuation.editionTitle)} · 信息时点 ${esc(comp.valuation.researchDate)} · ${esc(comp.valuation.published)} 成版</p>
          <a class="doc-link" data-observation-edition href="${esc(comp.valuation.url)}">打开本版现金与估值 →</a>` : comp.valuation.available ? `<div class="val-stamp-grid">
            <div class="val-stamp">
              <div class="val-stamp-k">研究日期</div>
              <div class="val-stamp-v">${esc(comp.valuation.researchDate)}</div><small>${esc(comp.valuation.published)} 成版</small>
            </div>
            <div class="val-stamp">
              <div class="val-stamp-k">要求现金回报率基准</div>
              <div class="val-stamp-v">${fmt(comp.valuation.requiredReturnPct, 2)}% / 年</div>
            </div>
            <div class="val-stamp">
              <div class="val-stamp-k">普通股正常现金主例</div>
              <div class="val-stamp-v">${fmt(comp.valuation.baseline, 1)} 亿元</div>
            </div>
          </div>

          <p class="section-sub">价格比较日 ${esc(comp.valuation.priceDate || "暂无同日价格")}</p>
          <div class="sub-svg-box" id="valuation-svg-mount"></div>

          <div class="assumptions-box">
            <div class="assumptions-title">估值口径、汇率与核心假设说明</div>
            <ul class="assumptions-list">
              ${comp.valuation.assumptions.map(a => `<li>${esc(a)}</li>`).join("")}
            </ul>
            <a class="doc-link" data-observation-edition href="${esc(comp.valuation.url)}">打开正式版 · 现金与估值 →</a>
            ${comp.valuation.figureUrl ? `<a class="doc-link" href="${esc(comp.valuation.figureUrl)}" target="_blank" rel="noopener">查看正式版原图 ↗</a>` : ''}
            ${comp.valuation.shareUrl ? `<a class="doc-link" href="${esc(comp.valuation.shareUrl)}" target="_blank" rel="noopener">查看股本月报 ↗</a>` : ''}
          </div>` : `<p class="fact-body">${esc(comp.valuation.reason)}</p>`}
        </section>
      </div>
    `;
    renderMainChart(comp, mode);
    renderOperatingGraphic(comp);
    renderValuationGraphic(comp);
    bindPageEvents(comp);
  }

  /* ============================================================================
   * 五、主视觉 SVG 绘制（海尔三地比较 + 德国量价 / 中石油 A·H 切换 + 布伦特分轨）
   * ============================================================================ */
  function renderMainChart(comp, mode) {
    const mc = comp.mainChart;
    const rows = mc.timeline;
    const n = rows.length;
    if (!n) {
      shadow.getElementById("main-svg-mount").textContent = "截至所选日期暂无已取得的行情。";
      return;
    }
    const W = 1160;
    const H = mc.layoutType === "haier_tri_market" && mode === "native" ? 560 : 500;
    const padL = 74;
    const padR = 78;
    const plotW = W - padL - padR;

    const xAt = idx => padL + (n <= 1 ? plotW / 2 : (idx / (n - 1)) * plotW);

    // 构建事件按日期映射
    const eventByIdx = new Map();
    mc.events.forEach(ev => {
      const idx = rows.findIndex(r => r.date === ev.date);
      if (idx >= 0) eventByIdx.set(idx, ev);
    });

    // 渲染动态图例
    const legendEl = shadow.getElementById("chart-legend");
    if (mc.layoutType === "haier_tri_market") {
      const m = mc.seriesMeta;
      legendEl.innerHTML = `
        <span class="legend-item"><i class="swatch-line" style="background:${m.sh.color}"></i>${esc(m.sh.label)} (${mode === "cny" ? "CNY/股" : m.sh.nativeUnit})</span>
        <span class="legend-item"><i class="swatch-line" style="background:${m.hk.color}"></i>${esc(m.hk.label)} (${mode === "cny" ? m.hk.cnyUnit : m.hk.nativeUnit})</span>
        <span class="legend-item"><i class="swatch-line" style="background:${m.de.color}"></i>${esc(m.de.label)} (${mode === "cny" ? m.de.cnyUnit : m.de.nativeUnit})</span>
        <span class="legend-item"><i class="swatch-bar" style="background:${m.deVol.color}"></i>${esc(m.deVol.label)} (${esc(m.deVol.unit)})</span>
        <span class="legend-item"><i class="swatch-gap"></i>休市/缺失日期断线</span>
      `;
    } else {
      const stockKey = mode === "a" ? "a" : "h";
      const sm = mc.seriesMeta[stockKey];
      const bm = mc.seriesMeta.brent;
      legendEl.innerHTML = `
        <span class="legend-item"><i class="swatch-line" style="background:${sm.color}"></i>${esc(sm.label)} (${esc(sm.nativeUnit)})</span>
        <span class="legend-item"><i class="swatch-line" style="background:${bm.color}"></i>${esc(bm.label)} (${esc(bm.nativeUnit)})</span>
        <span class="legend-item"><i class="swatch-gap"></i>跨市场休市/缺失断线</span>
      `;
    }

    // 组织 SVG 内容
    let svgInner = `
      <defs>
        <pattern id="gap-hatch" width="6" height="6" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#D5CEC0" stroke-width="1.6" />
        </pattern>
      </defs>
    `;

    // 找出存在缺失值的日期列并绘制浅色斜纹背景带
    const colStep = n > 1 ? plotW / (n - 1) : 24;
    const activeGapIndices = [];
    rows.forEach((r, idx) => {
      const hasMissing = mc.layoutType === "haier_tri_market"
        ? (r.sh === null || r.hk === null || r.de === null || (mode === "cny" && (r.hkCny === null || r.deCny === null)))
        : ((mode === "a" ? r.a === null : r.h === null) || r.brent === null);
      if (hasMissing) activeGapIndices.push(idx);
    });

    const trackTop = 28;
    const trackBottom = H - 42;

    activeGapIndices.forEach(idx => {
      const cx = xAt(idx);
      const bw = Math.min(26, colStep * 0.72);
      svgInner += `<rect x="${(cx - bw / 2).toFixed(2)}" y="${trackTop}" width="${bw.toFixed(2)}" height="${trackBottom - trackTop}" fill="url(#gap-hatch)" opacity="0.68" />`;
    });

    // 存储供悬停联动读取的节点坐标
    const interactiveDotsByIdx = Array.from({ length: n }, () => []);

    if (mc.layoutType === "haier_tri_market" && mode === "cny") {
      // 上轨：三地按同日汇率折算为人民币同轴直比；下轨：德国 690D 原币股价 (EUR) + 成交量 (千股)
      const topY0 = 28, topY1 = 292;
      const botY0 = 338, botY1 = 456;

      const shVals = rows.map(r => r.sh);
      const hkCnyVals = rows.map(r => r.hkCny);
      const deCnyVals = rows.map(r => r.deCny);

      const domTop = niceDomain([...shVals, ...hkCnyVals, ...deCnyVals], 0.1);
      const yTop = v => topY1 - ((v - domTop.min) / (domTop.max - domTop.min)) * (topY1 - topY0);

      svgInner += `<text x="${padL}" y="${topY0 - 10}" font-size="11.5" font-weight="600" fill="#4A4843" font-family="var(--mono)">上轨：按同日汇率折算人民币股价比较（单位：CNY / 股）</text>`;
      domTop.ticks.forEach(tk => {
        const yy = yTop(tk);
        svgInner += `
          <line x1="${padL}" y1="${yy.toFixed(2)}" x2="${W - padR}" y2="${yy.toFixed(2)}" stroke="#E2DDD2" stroke-width="1" />
          <text x="${padL - 10}" y="${(yy + 4).toFixed(2)}" text-anchor="end" font-size="11" fill="#78746C" font-family="var(--mono)">${fmt(tk, 1)}</text>
        `;
      });

      const ptsSh = shVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yTop(v) : 0, valid: v !== null, val: v }));
      const ptsHk = hkCnyVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yTop(v) : 0, valid: v !== null, val: v }));
      const ptsDe = deCnyVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yTop(v) : 0, valid: v !== null, val: v }));

      // A 股与 D 股折人民币折价带
      const bandPaths = buildBandAreaPaths(ptsSh, ptsDe);
      bandPaths.forEach(bp => {
        svgInner += `<path d="${bp}" fill="#B83A2D" opacity="0.07" />`;
      });

      [
        { pts: ptsSh, color: mc.seriesMeta.sh.color, width: 2.5 },
        { pts: ptsHk, color: mc.seriesMeta.hk.color, width: 2.2 },
        { pts: ptsDe, color: mc.seriesMeta.de.color, width: 2.4 }
      ].forEach(s => {
        const built = buildBrokenSeries(s.pts);
        svgInner += `<path d="${built.pathD}" fill="none" stroke="${s.color}" stroke-width="${s.width}" stroke-linejoin="round" stroke-linecap="round" />`;
        built.breakCaps.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3" fill="#FCFBF8" stroke="${s.color}" stroke-width="1.8" />`;
        });
        built.isolated.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3.8" fill="${s.color}" />`;
        });
        s.pts.forEach((p, idx) => {
          if (p.valid) interactiveDotsByIdx[idx].push({ x: p.x, y: p.y, color: s.color });
        });
      });

      // 下轨：德国 690D.DE 原币股价 (左轴 EUR/股) + 成交量柱 (右轴 千股)
      const deEurVals = rows.map(r => r.de);
      const deVolVals = rows.map(r => r.deVol);
      const domEur = niceDomain(deEurVals, 0.16);
      const maxVol = Math.max(...deVolVals.filter(v => v !== null), 100) * 1.25;
      const yEur = v => botY1 - ((v - domEur.min) / (domEur.max - domEur.min)) * (botY1 - botY0);
      const yVol = v => botY1 - (v / maxVol) * (botY1 - botY0);

      svgInner += `
        <line x1="${padL}" y1="${botY0 - 20}" x2="${W - padR}" y2="${botY0 - 20}" stroke="#CFC8B8" stroke-dasharray="3 3" />
        <text x="${padL}" y="${botY0 - 6}" font-size="11.5" font-weight="600" fill="#B83A2D" font-family="var(--mono)">下轨：Xetra D 股 (690D.DE) 原币股价（左轴：EUR/股）与成交量（右轴：千股）</text>
      `;

      domEur.ticks.filter((_, idx) => idx % 2 === 0 || domEur.ticks.length <= 4).forEach(tk => {
        const yy = yEur(tk);
        svgInner += `
          <line x1="${padL}" y1="${yy.toFixed(2)}" x2="${W - padR}" y2="${yy.toFixed(2)}" stroke="#E7E2D8" stroke-width="1" />
          <text x="${padL - 10}" y="${(yy + 4).toFixed(2)}" text-anchor="end" font-size="11" fill="#B83A2D" font-family="var(--mono)">${fmt(tk, 2)}</text>
        `;
      });

      [0, Math.round(maxVol / 2), Math.round(maxVol)].forEach(vk => {
        const yy = yVol(vk);
        svgInner += `<text x="${W - padR + 10}" y="${(yy + 4).toFixed(2)}" text-anchor="start" font-size="10.5" fill="#647B8C" font-family="var(--mono)">${vk}k</text>`;
      });

      // 成交量柱
      const barW = Math.min(18, colStep * 0.52);
      deVolVals.forEach((v, i) => {
        if (v === null) return;
        const bx = xAt(i) - barW / 2;
        const by = yVol(v);
        svgInner += `<rect x="${bx.toFixed(2)}" y="${by.toFixed(2)}" width="${barW.toFixed(2)}" height="${(botY1 - by).toFixed(2)}" fill="${mc.seriesMeta.deVol.color}" opacity="0.42" />`;
      });

      // 德国原币价格折线
      const ptsDeNative = deEurVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yEur(v) : 0, valid: v !== null }));
      const builtDeNative = buildBrokenSeries(ptsDeNative);
      svgInner += `<path d="${builtDeNative.pathD}" fill="none" stroke="${mc.seriesMeta.de.color}" stroke-width="2" />`;
      builtDeNative.breakCaps.forEach(p => {
        svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="2.8" fill="#FCFBF8" stroke="${mc.seriesMeta.de.color}" stroke-width="1.6" />`;
      });
      builtDeNative.isolated.forEach(p => {
        svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3.5" fill="${mc.seriesMeta.de.color}" />`;
      });
      ptsDeNative.forEach((p, idx) => {
        if (p.valid) interactiveDotsByIdx[idx].push({ x: p.x, y: p.y, color: mc.seriesMeta.de.color });
      });

      // 事件标记锚定在主曲线上
      eventByIdx.forEach((ev, idx) => {
        const anchorY = ptsDe[idx].valid ? ptsDe[idx].y : (ptsSh[idx].valid ? ptsSh[idx].y : topY0 + 24);
        svgInner += renderSvgEventPin(ev, xAt(idx), anchorY - 16);
      });

    } else if (mc.layoutType === "haier_tri_market" && mode === "native") {
      // 三地原币各自独立刻度三轨视图（避免将 28 CNY 与 2.1 EUR 强行压在同一纵轴导致失真）
      const lanes = [
        { key: "sh", title: "轨 1 · 沪 A 原币股价（单位：CNY / 股）", y0: 28, y1: 152, vals: rows.map(r => r.sh), color: mc.seriesMeta.sh.color, digits: 2 },
        { key: "hk", title: "轨 2 · 港 H 原币股价（单位：HKD / 股）", y0: 194, y1: 318, vals: rows.map(r => r.hk), color: mc.seriesMeta.hk.color, digits: 2 },
        { key: "de", title: "轨 3 · 德 D 原币股价（左轴：EUR / 股）及成交量（右轴：千股）", y0: 360, y1: 514, vals: rows.map(r => r.de), color: mc.seriesMeta.de.color, digits: 2, withVol: true }
      ];

      lanes.forEach(ln => {
        const dom = niceDomain(ln.vals, 0.14);
        const yFn = v => ln.y1 - ((v - dom.min) / (dom.max - dom.min)) * (ln.y1 - ln.y0);

        svgInner += `<text x="${padL}" y="${ln.y0 - 8}" font-size="11.5" font-weight="600" fill="${ln.color}" font-family="var(--mono)">${esc(ln.title)}</text>`;
        dom.ticks.filter((_, i) => i % 2 === 0 || dom.ticks.length <= 4).forEach(tk => {
          const yy = yFn(tk);
          svgInner += `
            <line x1="${padL}" y1="${yy.toFixed(2)}" x2="${W - padR}" y2="${yy.toFixed(2)}" stroke="#E4DFD4" stroke-width="1" />
            <text x="${padL - 10}" y="${(yy + 4).toFixed(2)}" text-anchor="end" font-size="11" fill="${ln.color}" font-family="var(--mono)">${fmt(tk, ln.digits)}</text>
          `;
        });

        if (ln.withVol) {
          const volVals = rows.map(r => r.deVol);
          const maxVol = Math.max(...volVals.filter(v => v !== null), 100) * 1.3;
          const yVol = v => ln.y1 - (v / maxVol) * (ln.y1 - ln.y0);
          const barW = Math.min(18, colStep * 0.52);
          volVals.forEach((v, i) => {
            if (v === null) return;
            const by = yVol(v);
            svgInner += `<rect x="${(xAt(i) - barW / 2).toFixed(2)}" y="${by.toFixed(2)}" width="${barW.toFixed(2)}" height="${(ln.y1 - by).toFixed(2)}" fill="${mc.seriesMeta.deVol.color}" opacity="0.4" />`;
          });
          [0, Math.round(maxVol)].forEach(vk => {
            svgInner += `<text x="${W - padR + 10}" y="${(yVol(vk) + 4).toFixed(2)}" font-size="10.5" fill="#647B8C" font-family="var(--mono)">${vk}k</text>`;
          });
        }

        const pts = ln.vals.map((v, i) => ({ x: xAt(i), y: v !== null ? yFn(v) : 0, valid: v !== null }));
        const built = buildBrokenSeries(pts);
        svgInner += `<path d="${built.pathD}" fill="none" stroke="${ln.color}" stroke-width="2.3" />`;
        built.breakCaps.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="2.8" fill="#FCFBF8" stroke="${ln.color}" stroke-width="1.6" />`;
        });
        built.isolated.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3.6" fill="${ln.color}" />`;
        });
        pts.forEach((p, idx) => {
          if (p.valid) interactiveDotsByIdx[idx].push({ x: p.x, y: p.y, color: ln.color });
        });

        if (ln.key === "de") {
          eventByIdx.forEach((ev, idx) => {
            const py = pts[idx].valid ? pts[idx].y - 16 : ln.y0 + 18;
            svgInner += renderSvgEventPin(ev, xAt(idx), py);
          });
        }
      });

    } else {
      // 中国石油：上轨所选 A 股或 H 股原币走势，下轨同日期布伦特原油（USD/桶）独立单位分轨
      const stockKey = mode === "a" ? "a" : "h";
      const sm = mc.seriesMeta[stockKey];
      const bm = mc.seriesMeta.brent;

      const topY0 = 28, topY1 = 232;
      const botY0 = 286, botY1 = 456;

      const stockVals = rows.map(r => r[stockKey]);
      const brentVals = rows.map(r => r.brent);

      const domStock = niceDomain(stockVals, 0.14);
      const domBrent = niceDomain(brentVals, 0.14);

      const yStock = v => topY1 - ((v - domStock.min) / (domStock.max - domStock.min)) * (topY1 - topY0);
      const yBrent = v => botY1 - ((v - domBrent.min) / (domBrent.max - domBrent.min)) * (botY1 - botY0);

      svgInner += `<text x="${padL}" y="${topY0 - 10}" font-size="11.5" font-weight="600" fill="${sm.color}" font-family="var(--mono)">上轨：${esc(sm.label)}（独立刻度单位：${esc(sm.nativeUnit)}）</text>`;
      domStock.ticks.forEach(tk => {
        const yy = yStock(tk);
        svgInner += `
          <line x1="${padL}" y1="${yy.toFixed(2)}" x2="${W - padR}" y2="${yy.toFixed(2)}" stroke="#E2DDD2" stroke-width="1" />
          <text x="${padL - 10}" y="${(yy + 4).toFixed(2)}" text-anchor="end" font-size="11" fill="${sm.color}" font-family="var(--mono)">${fmt(tk, 2)}</text>
        `;
      });

      svgInner += `
        <line x1="${padL}" y1="${botY0 - 24}" x2="${W - padR}" y2="${botY0 - 24}" stroke="#CFC8B8" stroke-dasharray="4 3" />
        <text x="${padL}" y="${botY0 - 8}" font-size="11.5" font-weight="600" fill="${bm.color}" font-family="var(--mono)">下轨：${esc(bm.label)} 同日期分轨走势（独立刻度单位：${esc(bm.nativeUnit)}）</text>
      `;
      domBrent.ticks.forEach(tk => {
        const yy = yBrent(tk);
        svgInner += `
          <line x1="${padL}" y1="${yy.toFixed(2)}" x2="${W - padR}" y2="${yy.toFixed(2)}" stroke="#E7E2D8" stroke-width="1" />
          <text x="${padL - 10}" y="${(yy + 4).toFixed(2)}" text-anchor="end" font-size="11" fill="${bm.color}" font-family="var(--mono)">${fmt(tk, 1)}</text>
        `;
      });

      const ptsStock = stockVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yStock(v) : 0, valid: v !== null }));
      const ptsBrent = brentVals.map((v, i) => ({ x: xAt(i), y: v !== null ? yBrent(v) : 0, valid: v !== null }));

      [
        { pts: ptsStock, color: sm.color, width: 2.6 },
        { pts: ptsBrent, color: bm.color, width: 2.4 }
      ].forEach(s => {
        const built = buildBrokenSeries(s.pts);
        svgInner += `<path d="${built.pathD}" fill="none" stroke="${s.color}" stroke-width="${s.width}" stroke-linejoin="round" stroke-linecap="round" />`;
        built.breakCaps.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3.1" fill="#FCFBF8" stroke="${s.color}" stroke-width="1.8" />`;
        });
        built.isolated.forEach(p => {
          svgInner += `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="3.8" fill="${s.color}" />`;
        });
        s.pts.forEach((p, idx) => {
          if (p.valid) interactiveDotsByIdx[idx].push({ x: p.x, y: p.y, color: s.color });
        });
      });

      eventByIdx.forEach((ev, idx) => {
        const py = ptsStock[idx].valid ? ptsStock[idx].y - 16 : topY0 + 20;
        svgInner += renderSvgEventPin(ev, xAt(idx), py);
      });
    }

    // 底部共享日期刻度轴
    const axisY = H - 38;
    svgInner += `<line x1="${padL}" y1="${axisY}" x2="${W - padR}" y2="${axisY}" stroke="#161614" stroke-width="1.2" />`;
    const tickStride = Math.max(1, Math.ceil(n / 10));
    rows.forEach((r, idx) => {
      const isTick = idx === 0 || idx === n - 1 || idx % tickStride === 0;
      const xx = xAt(idx);
      if (isTick) {
        svgInner += `
          <line x1="${xx.toFixed(2)}" y1="${axisY}" x2="${xx.toFixed(2)}" y2="${axisY + 6}" stroke="#161614" stroke-width="1" />
          <text x="${xx.toFixed(2)}" y="${axisY + 20}" text-anchor="middle" font-size="11" fill="#4A4843" font-family="var(--mono)">${esc(r.date.slice(5))}</text>
        `;
      } else {
        svgInner += `<line x1="${xx.toFixed(2)}" y1="${axisY}" x2="${xx.toFixed(2)}" y2="${axisY + 3}" stroke="#ABA496" stroke-width="1" />`;
      }
    });
    svgInner += `<text x="${padL}" y="${axisY + 34}" font-size="10.5" fill="#78746C" font-family="var(--mono)">起点 ${esc(rows[0]?.date || "")}</text>`;
    svgInner += `<text x="${W - padR}" y="${axisY + 34}" text-anchor="end" font-size="10.5" fill="#78746C" font-family="var(--mono)">终点 ${esc(rows[n - 1]?.date || "")}</text>`;

    // 悬停十字准星层 + 透明交互热区
    svgInner += `
      <g id="svg-crosshair-layer" style="pointer-events:none;"></g>
      <rect id="svg-hit-rect" x="${padL}" y="${trackTop}" width="${plotW}" height="${axisY - trackTop}" fill="transparent" style="cursor:crosshair;" />
    `;

    const mount = shadow.getElementById("main-svg-mount");
    mount.innerHTML = `<svg class="main-svg" id="primary-svg" viewBox="0 0 ${W} ${H}" aria-label="${esc(mc.sectionTitle)}">${svgInner}</svg>`;

    // 绑定悬停与点击锁定逻辑
    const svgEl = shadow.getElementById("primary-svg");
    const hitRect = shadow.getElementById("svg-hit-rect");
    // 公告标记要在透明的悬停层上方，否则圆点点击会被截走。
    svgEl.querySelectorAll(".svg-event-pin").forEach(pin => svgEl.append(pin));
    const crossLayer = shadow.getElementById("svg-crosshair-layer");
    const tooltipEl = shadow.getElementById("chart-tooltip");

    function updateFocus(idx, showFloating) {
      const safeIdx = Math.max(0, Math.min(n - 1, idx));
      const row = rows[safeIdx];
      const cx = xAt(safeIdx);
      const dots = interactiveDotsByIdx[safeIdx] || [];
      const ev = eventByIdx.get(safeIdx);

      crossLayer.innerHTML = `
        <line x1="${cx.toFixed(2)}" y1="${trackTop}" x2="${cx.toFixed(2)}" y2="${axisY}" stroke="#161614" stroke-width="1.1" stroke-dasharray="3 3" />
        ${dots.map(d => `<circle cx="${d.x.toFixed(2)}" cy="${d.y.toFixed(2)}" r="5" fill="${d.color}" stroke="#FCFBF8" stroke-width="2" />`).join("")}
      `;

      // 顶部固定读数栏更新
      const hud = shadow.getElementById("hud-readout");
      const pinHtml = state.pinnedIdx !== null
        ? `<span class="pin-badge" id="unlock-pin-btn" title="点击解除日期锁定">已锁定 ${esc(row.date)} ×</span>`
        : `<span>日期 ${esc(row.date)}</span>`;

      if (mc.layoutType === "haier_tri_market") {
        const hkCny = row.hkCny;
        const deCny = row.deCny;
        const spreadPct = (row.sh !== null && deCny !== null) ? ((deCny / row.sh - 1) * 100) : null;
        hud.innerHTML = `
          ${pinHtml}
          <span>沪A: <b>${row.sh !== null ? fmt(row.sh, 2) + " CNY" : "无行情"}</b></span>
          <span>港H: <b>${row.hk !== null ? fmt(row.hk, 2) + " HKD" : "无行情"}</b>${hkCny !== null ? ` (折 ${fmt(hkCny, 2)} CNY)` : ""}</span>
          <span>德D: <b>${row.de !== null ? fmt(row.de, 3) + " EUR" : "无行情"}</b>${deCny !== null ? ` (折 ${fmt(deCny, 2)} CNY)` : ""}</span>
          <span>德量: <b>${row.deVol !== null ? fmt(row.deVol * 1000, 0) + " 股" : "--"}</b></span>
          ${spreadPct !== null ? `<span style="color:var(--crimson)">D 相对 A: <b>${fmt(spreadPct, 1)}%</b></span>` : ""}
        `;
      } else {

        hud.innerHTML = `
          ${pinHtml}
          <span>A股: <b>${row.a !== null ? fmt(row.a, 2) + " CNY/股" : "无行情"}</b></span>
          <span>H股: <b>${row.h !== null ? fmt(row.h, 2) + " HKD/股" : "无行情"}</b></span>
          <span style="color:var(--ochre)">布伦特: <b>${row.brent !== null ? fmt(row.brent, 2) + " USD/桶" : "缺失"}</b></span>
        `;
      }

      const unlockBtn = shadow.getElementById("unlock-pin-btn");
      if (unlockBtn) {
        unlockBtn.onclick = () => {
          state.pinnedIdx = null;
          state.activeEventId = null;
          renderPublication();
        };
      }

      // 浮层提示框
      if (!showFloating) {
        tooltipEl.style.display = "none";
        return;
      }

      let ttBody = "";
      if (mc.layoutType === "haier_tri_market") {
        const hkCny = row.hkCny != null ? fmt(row.hkCny, 2) + " CNY" : "缺数断线";
        const deCny = row.deCny != null ? fmt(row.deCny, 2) + " CNY" : "缺数断线";
        ttBody = `
          <div class="tt-date"><span>${esc(row.date)}</span><span>同日汇率折算对照</span></div>
          <div class="tt-row"><span>沪 A (600690.SH)</span><span>${row.sh !== null ? fmt(row.sh, 2) + " CNY" : "缺数断线"}</span></div>
          <div class="tt-row"><span>港 H 原币 / 折人民币</span><span>${row.hk !== null ? fmt(row.hk, 2) + " HKD / " + hkCny : "缺数断线"}</span></div>
          <div class="tt-row"><span>德 D 原币 / 折人民币</span><span>${row.de !== null ? fmt(row.de, 3) + " EUR / " + deCny : "缺数断线"}</span></div>
          <div class="tt-row"><span>德国 690D 成交量</span><span>${row.deVol !== null ? fmt(row.deVol * 1000, 0) + " 股" : "无记录"}</span></div>
          <div class="tt-row" style="opacity:0.76;font-size:11px;margin-top:3px;"><span>同日汇率 HKD / EUR</span><span>${fmt(row.fxHkdCny, 5)} / ${fmt(row.fxEurCny, 4)}</span></div>
        `;
      } else {

        ttBody = `
          <div class="tt-date"><span>${esc(row.date)}</span><span>股油同日分轨读数</span></div>
          <div class="tt-row"><span>A 股 (601857.SH)</span><span>${row.a !== null ? fmt(row.a, 2) + " CNY/股" : "缺数断线"}</span></div>
          <div class="tt-row"><span>H 股 (00857.HK)</span><span>${row.h !== null ? fmt(row.h, 2) + " HKD/股" : "缺数断线"}</span></div>

          <div class="tt-row" style="color:#FFD98E;"><span>布伦特原油 (Brent)</span><span>${row.brent !== null ? fmt(row.brent, 2) + " USD/桶" : "缺失断线"}</span></div>
        `;
      }

      if (row.gapNote) {
        ttBody += `<div class="tt-gap">断线说明：${esc(row.gapNote)}</div>`;
      }
      if (ev) {
        ttBody += `<div class="tt-event">[公告 ${esc(ev.pin)}] ${esc(ev.title)}（点击固定并可在下方打开原件）</div>`;
      }

      tooltipEl.innerHTML = ttBody;
      tooltipEl.style.display = "block";

      const stageRect = shadow.getElementById("main-svg-stage").getBoundingClientRect();
      const relX = (cx / W) * stageRect.width;
      const tipW = tooltipEl.offsetWidth || 260;
      const leftPos = relX + tipW + 28 > stageRect.width ? Math.max(8, relX - tipW - 16) : relX + 16;
      tooltipEl.style.left = `${leftPos}px`;
      tooltipEl.style.top = `24px`;
    }

    function clientXToIndex(clientX) {
      const rect = svgEl.getBoundingClientRect();
      const svgX = ((clientX - rect.left) / rect.width) * W;
      const ratio = (svgX - padL) / plotW;
      return Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))));
    }

    hitRect.addEventListener("mousemove", e => {
      if (state.pinnedIdx !== null) return;
      const idx = clientXToIndex(e.clientX);
      state.hoverIdx = idx;
      updateFocus(idx, true);
    });

    hitRect.addEventListener("mouseleave", () => {
      if (state.pinnedIdx !== null) return;
      state.hoverIdx = null;
      updateFocus(n - 1, false);
    });

    hitRect.addEventListener("click", e => {
      const idx = clientXToIndex(e.clientX);
      if (state.pinnedIdx === idx) {
        state.pinnedIdx = null;
        state.activeEventId = null;
      } else {
        state.pinnedIdx = idx;
        const ev = eventByIdx.get(idx);
        state.activeEventId = ev ? ev.id : null;
      }
      renderPublication();
    });

    // 绑定 SVG 内公告圆点点击
    svgEl.querySelectorAll(".svg-event-pin").forEach(pinEl => {
      pinEl.addEventListener("click", e => {
        e.stopPropagation();
        const evId = pinEl.getAttribute("data-event-id");
        const evDate = pinEl.getAttribute("data-event-date");
        const idx = rows.findIndex(r => r.date === evDate);
        state.pinnedIdx = idx >= 0 ? idx : null;
        state.activeEventId = evId;
        renderPublication();
      });
    });

    // 初始状态渲染（若有锁定日期则高亮锁定日，否则展示期末最新交易日）
    const initIdx = state.pinnedIdx !== null ? state.pinnedIdx : n - 1;
    updateFocus(initIdx, state.pinnedIdx !== null);
  }

  function renderSvgEventPin(ev, x, y) {
    const safeY = Math.max(20, y);
    const isSelected = state.activeEventId === ev.id;
    return `
      <g class="svg-event-pin" data-event-id="${esc(ev.id)}" data-event-date="${esc(ev.date)}">
        <line x1="${x.toFixed(2)}" y1="${(safeY + 10).toFixed(2)}" x2="${x.toFixed(2)}" y2="${(safeY + 18).toFixed(2)}" stroke="#B83A2D" stroke-width="1.4" />
        <circle cx="${x.toFixed(2)}" cy="${safeY.toFixed(2)}" r="${isSelected ? 11 : 9.5}" fill="${isSelected ? "#161614" : "#B83A2D"}" stroke="#FCFBF8" stroke-width="1.8" />
        <text x="${x.toFixed(2)}" y="${(safeY + 3.8).toFixed(2)}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#FFFFFF" font-family="var(--mono)">${esc(ev.pin)}</text>
      </g>
    `;
  }

  /* ============================================================================
   * 六、第二模块原创 SVG：经营驱动专图（海尔多币种收入结构 / 中石油上游单位成本对比）
   * ============================================================================ */
  function renderOperatingGraphic(comp) {
    const op = comp.operating;
    const mount = shadow.getElementById("operating-svg-mount");
    if (!op.visualItems.length) {
      mount.textContent = "截至所选日期暂无该项可比披露。";
      return;
    }
    const W = 560;

    if (op.visualType === "haier_fx_revenue") {
      const H = 225;
      let curX = 20;
      const barW = W - 40;
      const barY = 38;
      const barH = 26;

      let stackedRects = "";
      let legendRows = "";

      op.visualItems.forEach((item, i) => {
        const segW = (item.sharePct / 100) * barW;
        stackedRects += `
          <rect x="${curX.toFixed(2)}" y="${barY}" width="${Math.max(2, segW - 1.5).toFixed(2)}" height="${barH}" fill="${item.color}" />
          ${segW > 46 ? `<text x="${(curX + segW / 2).toFixed(2)}" y="${barY + 17}" text-anchor="middle" font-size="11" font-weight="700" fill="#FFFFFF" font-family="var(--mono)">${fmt(item.sharePct, 1)}%</text>` : ""}
        `;
        curX += segW;

        const rowY = 92 + i * 28;
        legendRows += `
          <rect x="20" y="${rowY - 9}" width="10" height="10" fill="${item.color}" />
          <text x="38" y="${rowY}" font-size="12" fill="#161614" font-weight="600">${esc(item.region)}</text>
          <text x="275" y="${rowY}" font-size="11.5" fill="#78746C" font-family="var(--mono)">${esc(item.currency)}</text>
          <text x="395" y="${rowY}" font-size="12" fill="#161614" font-weight="700" font-family="var(--mono)">${fmt(item.sharePct, 1)}%</text>
          <text x="${W - 20}" y="${rowY}" text-anchor="end" font-size="11.5" fill="#237A5B" font-family="var(--mono)">${esc(item.yoyText)}</text>
        `;
      });

      mount.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
          <text x="20" y="22" font-size="12" font-weight="700" fill="#161614">${esc(op.visualTitle)}（${esc(op.visualUnit)}）</text>
          ${stackedRects}
          ${legendRows}
          <text x="20" y="${H - 8}" font-size="10.8" fill="#78746C">${esc(op.visualNote)}</text>
        </svg>
      `;
    } else {
      // 中石油：上游单位操作成本独立对比图（USD/桶）
      const H = 65 + op.visualItems.length * 52;
      const leftX = 185;
      const maxBarW = W - leftX - 115;
      const maxRef = Math.max(...op.visualItems.map(d => d.value * 1.2));

      let barsSvg = "";
      op.visualItems.forEach((item, idx) => {
        const y = 48 + idx * 52;
        const w = (item.value / maxRef) * maxBarW;
        barsSvg += `
          <text x="16" y="${y + 15}" font-size="12" font-weight="600" fill="#161614">${esc(item.label)}</text>
          <rect x="${leftX}" y="${y}" width="${maxBarW}" height="22" fill="#EAE5DA" />
          <rect x="${leftX}" y="${y}" width="${w.toFixed(2)}" height="22" fill="${item.color}" />
          <text x="${(leftX + w + 8).toFixed(2)}" y="${y + 15}" font-size="12.5" font-weight="700" fill="${item.color}" font-family="var(--mono)">${fmt(item.value, 2)} ${esc(op.visualUnit)}</text>
          <text x="${leftX}" y="${y + 36}" font-size="10.8" fill="#5A5751" font-family="var(--mono)">报告期 ${esc(item.period)} · ${esc(item.badge)}</text>
        `;
      });

      mount.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
          <text x="16" y="22" font-size="12" font-weight="700" fill="#161614">${esc(op.visualTitle)}</text>
          ${barsSvg}
          <text x="16" y="${H - 8}" font-size="10.8" fill="#78746C">${esc(op.visualNote)}</text>
        </svg>
      `;
    }
  }

  /* ============================================================================
   * 七、第三模块原创 SVG：普通股年度现金要求与各上市地等值市值/隐含回报率图
   * ============================================================================ */
  function renderValuationGraphic(comp) {
    const val = comp.valuation;
    if (!val.available || val.linkedEdition) return;
    const mount = shadow.getElementById("valuation-svg-mount");
    if (!val.venues.length) {mount.textContent="截至所选日期暂无同日价格、汇率及股本配对。"; return;}
    const W = 520;
    const venues = val.venues;
    const maxCash = Math.max(val.baseline, ...venues.map(v => v.cash))*1.16;
    const barStart = 125;
    const barMaxW = W-barStart-96;
    const anchorX = barStart+val.baseline/maxCash*barMaxW;
    const rowH = 68;
    const topOffset = 68;
    const H = topOffset + venues.length * rowH + 46;

    let rowsSvg = "";
    venues.forEach((v, i) => {
      const yy = topOffset + i * rowH;
      const bw = (v.cash / maxCash) * barMaxW;
      const barColor = v.cash <= val.baseline ? "#237A5B" : "#1B4965";
      rowsSvg += `
        <text x="14" y="${yy + 13}" font-size="12" font-weight="700" fill="#161614">${esc(v.market)}</text>
        <text x="14" y="${yy + 29}" font-size="11" fill="#78746C" font-family="var(--mono)">${fmt(v.cnyPrice, 2)} 元/股</text>
        <rect x="${barStart}" y="${yy}" width="${barMaxW}" height="24" fill="#EAE5DA" />
        <rect x="${barStart}" y="${yy}" width="${bw.toFixed(2)}" height="24" fill="${barColor}" opacity="0.9" />
        <text x="${(barStart + bw + 7).toFixed(2)}" y="${yy + 16}" font-size="11.5" font-weight="700" fill="${barColor}" font-family="var(--mono)">${fmt(v.cash, 1)} 亿元</text>
      `;
    });

    // 正常现金和按价格反算的现金要求共用年度现金刻度。
    const cashBarW = val.baseline / maxCash * barMaxW;

    mount.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
        <text x="14" y="20" font-size="11.5" font-weight="700" fill="#B83A2D">各股价隐含的年度普通股现金 · 亿元/年</text>

        <!-- 单独绘制年度普通股现金要求刻度条 -->
        <text x="14" y="46" font-size="11.5" font-weight="600" fill="#161614">正常现金主例</text>
        <rect x="${barStart}" y="32" width="${barMaxW}" height="18" fill="#F2ECE1" />
        <rect x="${barStart}" y="32" width="${cashBarW.toFixed(2)}" height="18" fill="#B83A2D" />
        <text x="${(barStart + cashBarW + 7).toFixed(2)}" y="45" font-size="11.5" font-weight="700" fill="#B83A2D" font-family="var(--mono)">${fmt(val.baseline, 1)} 亿元 RMB / 年</text>

        ${rowsSvg}

        <!-- 正常现金主例参照线 -->
        <line x1="${anchorX.toFixed(2)}" y1="${topOffset - 8}" x2="${anchorX.toFixed(2)}" y2="${H - 30}" stroke="#B83A2D" stroke-width="1.6" stroke-dasharray="4 3" />
        <text x="${anchorX.toFixed(2)}" y="${H - 12}" text-anchor="middle" font-size="10.8" font-weight="700" fill="#B83A2D" font-family="var(--mono)">
          主例 ${fmt(val.baseline, 0)} 亿元/年
        </text>
      </svg>
    `;
  }

  /* ============================================================================
   * 八、页面级交互事件绑定（主图模式切换、公告定位）
   * ============================================================================ */
  function bindPageEvents(comp) {
    shadow.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        state.mode = btn.dataset.mode;
        renderPublication();
      });
    });

    shadow.querySelectorAll(".event-card").forEach(card => {
      card.addEventListener("click", event => {
        if (event.target.closest("a")) return;
        const evId = card.getAttribute("data-event-id");
        const evDate = card.getAttribute("data-event-date");
        const idx = comp.mainChart.timeline.findIndex(r => r.date === evDate);
        if (state.activeEventId === evId) {
          state.activeEventId = null;
          state.pinnedIdx = null;
        } else {
          state.activeEventId = evId;
          state.pinnedIdx = idx >= 0 ? idx : null;
        }
        renderPublication();
      });
    });

  }
  renderPublication();
}
