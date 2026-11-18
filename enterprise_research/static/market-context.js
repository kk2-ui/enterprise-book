'use strict';

const marketObservationCodes = new Set(['600690.SH', '06690.HK', '690D.DE', '601857.SH', '00857.HK']);

function hasMarketObservation(company) {
  return marketObservationCodes.has(String(company.code).trim().toUpperCase());
}

function withMarketObservationTab(company, tabs) {
  return hasMarketObservation(company) ? [tabs[0], ['market', '市场观察'], ...tabs.slice(1)] : tabs;
}

function marketObservationShell(company) {
  return `<section class="panel market-context observation" data-market-company="${esc(company.id)}" data-observation aria-label="市场观察">
    <h2>市场观察</h2><p class="market-note" role="status">正在读取行情与披露…</p>
  </section>`;
}


function isPetroChinaMarketPilot(c) {
  const code = String(c?.code || '').trim().toUpperCase();
  return code === '601857.SH' || code === '00857.HK';
}


function marketContextShell(c) {
  if (hasMarketObservation(c)) return marketObservationShell(c);
  if (isPetroChinaMarketPilot(c)) {
    return `<section class="panel market-context" data-market-company="${esc(c.id)}" aria-label="市场观察">
      <div class="market-heading"><div><h2>市场观察</h2><p class="muted">正在读取中国石油行情与披露快照…</p></div></div>
    </section>`;
  }
  return `<section class="panel market-context" data-market-company="${esc(c.id)}" aria-label="市场环境与主导力量">
    <div class="market-heading"><div><h2>市场环境与主导力量</h2><p class="muted">正在读取可比行情…</p></div></div>
  </section>`;
}

function marketNumber(value, suffix='%', signed=true) {
  if (value == null) return '—';
  return `${signed && value > 0 ? '+' : ''}${Number(value).toFixed(2)}${suffix}`;
}

function bearMonitorMarkup(m) {
  if (!m) return '';
  const names={market:'大盘',industry:'行业参照',stock:'个股'};
  const cards=Object.entries(names).map(([key,name])=>{
    const r=m[key];
    if(r.status!=='ok')return `<div><span>${name}</span><strong>数据不足</strong><p>${esc(r.reason||'等待完整历史')}</p></div>`;
    return `<div><span>${name}${key==='industry'?' · '+r.breadth.selected+'家':''} · 长期位置</span><strong>${esc(r.state)}</strong>
      <p>距已取得历史高点 ${marketNumber(r.drawdown_pct)}<br>高点 ${esc(r.peak_date)} · 已过 ${r.days_since_peak} 天</p>
      <p>距200日均线 ${marketNumber(r.ma200_gap_pct)}<br>均线近20日变化 ${marketNumber(r.ma200_change20_pct)}</p>
      ${key==='industry'?`<p>${r.breadth.below_ma200} / ${r.breadth.valid} 家低于200日线${r.breadth.selected<3?' · 有限参照':''}</p>`:''}
      ${key==='industry'?`<p>同行成交活跃度中位数 ${marketNumber(r.volume.median_activity,' 倍',false)}</p>`:''}
      ${key==='stock'?`<p>${esc(r.volume.label)}</p>`:''}
      <p class="market-note">实际覆盖 ${esc(r.history_start)} 起，${r.history_days} 日</p></div>`;
  }).join('');
  const factorNames={market:'大盘',size:'规模风格',industry:'行业增量',specific:'未解释偏离',drift:'历史平均项'};
  const columns=['20','60','252'];
  return `<div class="market-verdict"><div><h3>熊市与压力来源 · ${esc(m.research_priority)}</h3><p>${esc(m.research_reason)}</p><p class="market-note">用于逆向研究筛选；是否错杀由企业分析判断。</p></div></div>
    <div class="market-observations">${cards}</div>
    <div class="market-table-wrap"><table class="market-table"><thead><tr><th>压力与相对强弱</th>${columns.map(h=>`<th>${h}个交易日</th>`).join('')}</tr></thead><tbody>
      <tr><th>负向影响主要来源</th>${columns.map(h=>`<td>${esc(m.windows[h].driver_label||'数据不足')}</td>`).join('')}</tr>
      <tr><th>行业相对大盘</th>${columns.map(h=>`<td>${marketNumber(m.windows[h].relative_returns.industry_market)}</td>`).join('')}</tr>
      <tr><th>个股相对行业</th>${columns.map(h=>`<td>${marketNumber(m.windows[h].relative_returns.stock_industry)}</td>`).join('')}</tr>
      <tr><th>同行跑输大盘家数</th>${columns.map(h=>`<td>${m.windows[h].industry_laggards.below_market??'—'} / ${m.windows[h].industry_laggards.valid}</td>`).join('')}</tr>
    </tbody></table></div>
    <details class="market-monitor-method"><summary>展开压力分解与监测口径</summary>
      <p>回撤深度与长期趋势分开：高点距今至少60个自然日，且当前较已取得历史高点回撤至少20%，记为深回撤；结合200日均线的位置及方向，区分下行、震荡与修复。20%用于观察，不是买入门槛。</p>
      <p>每个窗口只用此前最多252日估计敏感度，至少126日。下表为对数收益百分点，可相加；主导标签只说明模型中的统计压力。252日分解跨期较长，更容易受敏感度变化影响。</p>
      <div class="market-table-wrap"><table class="market-table"><thead><tr><th>分项</th>${columns.map(h=>`<th>${h}日影响</th>`).join('')}</tr></thead><tbody>
        ${Object.entries(factorNames).map(([k,label])=>`<tr><th>${label}</th>${columns.map(h=>`<td>${marketNumber(m.windows[h].contributions_log_pp?.[k],' 点')}</td>`).join('')}</tr>`).join('')}
        <tr><th>实际对数收益</th>${columns.map(h=>`<td>${marketNumber(m.windows[h].observed_log_pp,' 点')}</td>`).join('')}</tr>
        <tr><th>历史拟合解释率</th>${columns.map(h=>`<td>${m.windows[h].r2==null?'—':Math.round(m.windows[h].r2*100)+'%'}</td>`).join('')}</tr>
      </tbody></table></div>
      ${columns.map(h=>{const a=m.windows[h];return `<p class="market-note">${h}日：${a.status==='ok'?`训练 ${esc(a.training_start)} 至 ${esc(a.training_end)}，${a.training_days}日；最大VIF ${a.max_vif}，个股偏离 / 异常尺度 ${a.specific_z}（不是概率）；${esc(a.warnings.join('；')||'')}`:esc(a.reason)}</p>`;}).join('')}
      <p>个股成交活跃度 ${marketNumber(m.stock.volume?.activity_ratio,' 倍',false)}；涨跌日量能差 ${marketNumber(m.stock.volume?.signed_volume_balance==null?null:m.stock.volume.signed_volume_balance*100)}。后者按涨跌日归类成交量，不是净流入流出。</p>
      ${m.warnings.map(w=>`<p class="market-note">${esc(w)}</p>`).join('')}
    </details>`;
}

function sectorHistoryMarkup(h) {
  if(!h)return '';
  if(h.status!=='ready')return `<p class="market-notice">${esc(h.reason)}</p>`;
  const b=h.main.groups.basic;
  const names=h.group_names;
  const row=(r)=>`<tr ${r.code==='06049.HK'?'class="market-own"':''}><th>${esc(r.name)} <small>${esc(r.code)}</small></th><td>${marketNumber(r.return_pct)}</td><td>${r.return_pct==null?`${esc(r.last_date||'无行情')} · 末次 ${marketNumber(r.last_observed_pct)}`:'同日可比'}</td></tr>`;
  return `<section class="market-sector" aria-label="2021年以来物业复盘"><h3>2021年以来：行业与保利的位置</h3>${h.cross_basis_warning?`<p class="market-notice">${esc(h.cross_basis_warning)}</p>`:""}
    <p class="market-note">${esc(h.baseline)} → ${esc(h.as_of)} · 同日起点 · 广样本，商管单列</p>
    <div class="market-observations"><div><span>恒生综合指数</span><strong>${marketNumber(h.main.market_pct)}</strong><p>价格指数</p></div>
      <div><span>基础物业 · 个股区间涨跌中位数</span><strong>${marketNumber(b.median_pct)}</strong><p>${b.below_market??"—"} / ${b.valid} 家同行跑输大盘<br>${b.unknown} 家缺当前可比价，停牌 / 退出见明细</p></div>
      <div><span>保利物业</span><strong>${marketNumber(b.own_pct)}</strong><p>可比 ${b.rank_total} 家中第 ${b.own_rank} 名<br>排名从涨幅最高起，包含保利</p></div></div>
    <div class="market-sector-plot market-plot"></div>
    <div class="market-legend"><span><i class="market-color-stock"></i>保利</span><span><i class="market-color-industry"></i>基础物业中位数</span><span><i class="market-color-market"></i>恒生综合</span></div>
    <p class="market-sector-readout market-note"></p>
    <p class="market-note">这是个股区间变动的横截面中位数；每个时点显示覆盖数，不是每日调仓组合。${h.return_basis==='PRICE_ONLY'?'本节股票和指数均为价格变化，未计分红，不能解释为投资总回报。':'股票前复权、指数不含股息，不能当作统一含息投资收益。'}</p>
    <details class="market-monitor-method"><summary>逐年复盘、换起点验证与完整分组名单</summary>
    <p>以下均从2020年末累计。原始基础物业名单含保利共 ${b.selected+1} 家，后上市公司单列；缺失成员保留在分母。即使把 ${b.unknown} 家缺失成员都视为跑赢，已有 ${marketNumber(b.below_market_min_pct,'%',false)} 的原始同行可确认跑输。</p>
    <div class="market-table-wrap"><table class="market-table"><thead><tr><th>观察终点</th><th>大盘累计</th><th>物业中位数</th><th>保利累计</th><th>同行跑输 / 可比</th></tr></thead><tbody>
      ${h.cumulative.map(c=>{const g=c.groups.basic;return `<tr><th>${esc(c.end)}</th><td>${marketNumber(c.market_pct)}</td><td>${marketNumber(g.median_pct)}</td><td>${marketNumber(g.own_pct)}</td><td>${g.below_market} / ${g.valid}</td></tr>`}).join('')}</tbody></table></div>
    <p>换起点仍沿用2021年原名单，不把后上市公司混进来：</p>
    <div class="market-table-wrap"><table class="market-table"><thead><tr><th>起点 → 当前</th><th>大盘</th><th>物业中位数</th><th>保利</th><th>同行跑输 / 可比</th></tr></thead><tbody>
      ${h.sensitivity.map(c=>{const g=c.groups.basic;return `<tr><th>${esc(c.start)}</th><td>${marketNumber(c.market_pct)}</td><td>${marketNumber(g.median_pct)}</td><td>${marketNumber(g.own_pct)}</td><td>${g.below_market} / ${g.valid}</td></tr>`}).join('')}</tbody></table></div>
    <p>期初等权的区间涨跌均值 ${marketNumber(b.initial_equal_mean_pct)}，与中位数分开观察。极端强势小盘股会显著拉高均值。</p>
    ${Object.entries(names).map(([k,n])=>`<h4>${esc(n)} · 2021年起点已有行情</h4><div class="market-table-wrap"><table class="market-table"><thead><tr><th>公司</th><th>区间变动</th><th>覆盖</th></tr></thead><tbody>${h.main.groups[k].records.map(row).join('')}</tbody></table></div>`).join('')}
    <h4>较晚上市 · 各自首个交易日起算，不参与2021排名</h4>
    <div class="market-table-wrap"><table class="market-table"><thead><tr><th>公司 / 分组</th><th>首日</th><th>至今</th><th>同期大盘</th></tr></thead><tbody>${h.later_listings.map(r=>`<tr><th>${esc(r.name)} / ${esc(names[r.group])}</th><td>${esc(r.first_date||'未取得')}</td><td>${marketNumber(r.return_pct)}</td><td>${marketNumber(r.market_pct)}</td></tr>`).join('')}</tbody></table></div>
    <p>${esc(h.scope)}</p>
    ${h.members.map(r=>`<p class="market-note"><a href="${esc(r.source)}" target="_blank" rel="noopener">${esc(r.name)} · ${esc(names[r.group])}</a>：${esc(r.reason)}${r.status_source?` <a href="${esc(r.status_source)}" target="_blank" rel="noopener">停牌 / 退出依据</a>`:''}</p>`).join('')}
    </details></section>`;
}

function drawSectorChart(root,data) {
  const h=data.sector_history,host=root.querySelector('.market-sector-plot');
  if(!host||h?.status!=='ready')return;
  const rows=h.chart,keys=['stock','industry','market'];
  const all=rows.flatMap(r=>keys.map(k=>r[k])).filter(v=>v!=null);
  const width=Math.max(280,Math.round(host.getBoundingClientRect().width)),height=width<500?240:280,left=45,right=width-16,top=15,bottom=height-36;
  const low=Math.floor(Math.min(...all)/20)*20,high=Math.ceil(Math.max(20,...all)/20)*20;
  const x=i=>left+(right-left)*i/(rows.length-1),y=v=>bottom-(v-low)/(high-low)*(bottom-top);
  const path=k=>rows.map((r,i)=>r[k]==null?'':`${i&&rows[i-1][k]!=null?'L':'M'}${x(i).toFixed(2)},${y(r[k]).toFixed(2)}`).join(' ');
  const ticks=Array.from({length:Math.round((high-low)/20)+1},(_,i)=>low+20*i);
  host.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="保利、基础物业中位数与大盘自2021年以来的累计表现"><title>同日起点累计行情表现；中位数可比家数随停牌退出变化</title>
    ${ticks.map(v=>`<line class="${v===0?'market-zero':'market-gridline'}" x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end">${v.toFixed(0)}%</text>`).join('')}
    ${keys.map(k=>`<path class="market-line market-color-${k}" d="${path(k)}"/>`).join('')}
    ${[0,Math.floor((rows.length-1)/2),rows.length-1].map(i=>`<text x="${x(i)}" y="${bottom+23}" text-anchor="${i===0?'start':i===rows.length-1?'end':'middle'}">${esc(width<500?rows[i].date.slice(0,7):rows[i].date)}</text>`).join('')}
    <line class="market-guide" x1="${right}" x2="${right}" y1="${top}" y2="${bottom}"/><rect class="market-hit" x="${left}" y="${top}" width="${right-left}" height="${bottom-top}"/></svg>`;
  const svg=host.querySelector('svg'),guide=host.querySelector('.market-guide');
  function inspect(i){const r=rows[i];guide.setAttribute('x1',x(i));guide.setAttribute('x2',x(i));root.querySelector('.market-sector-readout').textContent=`${r.date} · 保利 ${marketNumber(r.stock)} · 物业中位数 ${marketNumber(r.industry)}（${r.valid}/${r.selected} 家同行） · 大盘 ${marketNumber(r.market)}`;}
  svg.addEventListener('pointermove',e=>{const box=svg.getBoundingClientRect(),pos=(e.clientX-box.left)*width/box.width;inspect(Math.max(0,Math.min(rows.length-1,Math.round((pos-left)/(right-left)*(rows.length-1)))))});
  inspect(rows.length-1);
}

function marketContextMarkup(data, days) {
  const refresh = `<button class="btn secondary" data-market-refresh ${data.refreshing?'disabled':''}>${data.refreshing?'更新中…':'更新行情'}</button>`;
  if (data.status !== 'ready') {
    return `<div class="market-heading"><h2>市场环境与主导力量</h2>${data.status==='unsupported'?'':refresh}</div>
      <p class="market-notice" role="status">${esc(data.reason || data.refresh_error || '首次整理个股、同业与市场基准日线，稍后自动显示。')}</p>
      ${data.as_of?`<p>个股日期 ${esc(data.as_of)} · 市场日期 ${esc(data.market_as_of||'待取数')}</p>`:''}
      ${(data.errors||[]).length?`<details><summary>行情来源问题</summary>${data.errors.map(e=>`<p>${esc(e.code)} · ${esc(e.error)}</p>`).join('')}</details>`:''}`;
  }
  const included = data.peers.filter(p=>p.included);
  const updated = new Date(data.captured_at).toLocaleString('zh-CN', {timeZone:'Asia/Hong_Kong', hour12:false});
  const noPeer = included.length < 2;
  const fresh = data.lag_days > 3 || data.cache_age_hours > 24;
  const compareRows = [
    {name:data.name, metrics:data.metrics, own:true},
    ...data.benchmarks.map(x=>({name:x.name, metrics:x.metrics})),
    ...data.peers.filter(x=>x.included).map(x=>({name:x.name, metrics:x.metrics}))
  ];
  return `<div class="market-heading">
      <div><h2>市场环境与主导力量</h2><p class="market-note">截至 ${esc(data.as_of)} 收盘 · 港股及A股交易日期</p></div>
      <div class="market-controls"><label>走势图 <select data-market-window>${[20,60,252].map(n=>`<option value="${n}" ${String(n)===String(days)?'selected':''}>${n} 个交易日</option>`).join('')}</select></label>${refresh}</div>
    </div>
    ${fresh || data.errors.length || data.refresh_error?`<p class="market-notice">${fresh?'显示最近取得的数据，请核对日期。 ':''}${data.errors.length?'部分行情更新失败，沿用已取得的同日数据或剔除缺失参照。 ':''}${esc(data.refresh_error||'')}</p>`:''}
    ${sectorHistoryMarkup(data.sector_history)}
    ${bearMonitorMarkup(data.monitor)}
    <p class="market-note">负向影响可能被其他上涨因素抵消；“个股额外下跌”是待查偏离，不能单凭行情确定为公司问题。</p>
    ${data.profile.aggregation==='daily_median'?`<p class="market-note">下图行业线：${included.length}家当前合格同行，每天至少80%且不少于5家有可比价格，逐日涨跌中位数连乘。上方2021年复盘采用固定起点的个股区间中位数，两者用途不同。</p>`:''}
    <div class="market-plot market-current-plot" aria-label="个股与参照走势"></div>
    <div class="market-legend">${['stock','industry','market','small'].filter(key=>key!=='industry'||!noPeer).map(key=>`<span><i class="market-color-${key}"></i>${esc(data.labels[key])}</span>`).join('')}</div>
    <p class="market-chart-readout market-note" aria-live="off">${days}个交易日，同起点回报。移动到曲线上可查看当日数值。</p>
    <details class="market-monitor-method"><summary>展开当前个股与同行涨跌、量能</summary><div class="market-table-wrap"><table class="market-table"><thead><tr><th>对照</th><th>20日</th><th>60日</th><th>252日</th><th>短期趋势</th><th>成交活跃度</th></tr></thead><tbody>
      ${compareRows.map(row=>`<tr ${row.own?'class="market-own"':''}><th>${esc(row.name)}</th>${[20,60,252].map(n=>`<td>${marketNumber(row.metrics.returns[n])}</td>`).join('')}<td>${esc(row.metrics.trend)}</td><td>${marketNumber(row.metrics.volume_ratio,' 倍',false)}</td></tr>`).join('')}
    </tbody></table></div></details>
    <div class="market-detail-columns">
      <details><summary>同行选择与剔除 · ${included.length} / ${data.peers.length} 家进入模型</summary>
        <p>${esc(data.profile.scope)}</p>
        <p class="market-note">${data.profile.aggregation==='daily_median'?'逐日取同行涨跌中位数，剔除本公司；每天需至少80%入选同行且不少于5家有相邻日价格，当前曲线是该逐日参照的连乘，区别于上方长期区间中位数。':'每家等权，剔除本公司。'}流通市值在本股 1/3 至 3 倍内标记为规模接近，规模差异另由风格因子观察。近60日同行两两日收益相关性中位数 ${data.peer_correlation60==null?'待计算':data.peer_correlation60}，越接近1越同步。</p>
        ${data.peers.map(peer=>`<article class="market-peer"><div><strong>${esc(peer.name)}</strong> <span>${esc(peer.code)}</span><b>${peer.included?'已纳入':esc(peer.exclusion||'未纳入')}</b></div><p>${esc(peer.reason)}</p>
          ${peer.size_ratio!=null?`<p class="market-note">流通市值约为本股 ${peer.size_ratio} 倍 · ${peer.similar_size?'规模接近':'规模差异较大'} · ${esc((data.cap_as_of||'').slice(0,10))}</p>`:''}
          <a href="${esc(peer.source)}" target="_blank" rel="noopener">业务选择依据 ↗</a></article>`).join('') || '<p>尚未建立业务可比名单。新增企业需先核对赚钱方式与上市市场。</p>'}
        ${data.profile.excluded.map(peer=>`<p class="market-note">${esc(peer.name)}未纳入 · ${esc(peer.reason)}</p>`).join('')}
      </details>
      <details><summary>成熟方法与当前边界</summary>
        <p>本面板组合因子模型、相对强弱、市场广度、长期均线与涨跌日量能。组合判定参数是首版观察口径，尚未验证为逆向交易策略。R²描述此前拟合程度，不是当前涨跌的因果比例。</p>
        <p>全市场个股广度尚未接入。行业仅为列明的业务参照，不等于完整板块。当前名单与当前复权历史适合观察当前状态，不能直接用于历史时点回测。</p>
        <p>${data.return_basis?.matched?esc(data.return_convention)+'。股票与指数统一为税前含息口径。':'股票为前复权，指数为价格指数，分红口径存在差异。'}成交活跃度为近20日成交量中位数除以前60日中位数；放量说明交易增多，不代表净流出。短期趋势为收盘价、20日、60日均线排列。</p>
        <p><a href="https://www.msci.com/documents/10199/ed6e42a3-c1fa-4430-89ba-efd5a5b52558" target="_blank" rel="noopener">MSCI 因子分解</a> · <a href="https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/relative-strength-comparison" target="_blank" rel="noopener">相对强弱</a> · <a href="https://www.fidelity.com/learning-center/trading-investing/advance-decline" target="_blank" rel="noopener">涨跌广度</a></p>
      </details>
      <details><summary>行情来源与更新时间</summary><p class="market-note">本次计算 ${esc(updated)}（香港时间）</p>
        ${data.sources.map(source=>`<p><a href="${esc(source.source_url)}" target="_blank" rel="noopener">${esc(source.name)} · ${esc(source.source)}</a><small>截至 ${esc(source.last_date)}</small></p>`).join('')}
        ${data.errors.map(error=>`<p class="market-note">${esc(error.code)} · ${esc(error.error)}</p>`).join('')}
      </details>
    </div>`;
}

function drawMarketChart(root, data, days) {
  const host = root.querySelector('.market-current-plot');
  if (!host) return;
  // Compound only complete daily observations within the selected window.
  // A gap invalidates the following portfolio levels, rather than implying a zero return.
  let peerLevel = 100;
  const rows = data.chart.slice(-Number(days)-1).map((row,index)=>{
    if (!row.peer_available || (index && row.peer_return == null)) peerLevel = null;
    else if (index && peerLevel != null) peerLevel *= 1 + row.peer_return;
    return {...row, industry:peerLevel};
  });
  const keys = ['stock','industry','market','small'].filter(key=>rows[0]?.[key] > 0);
  const values = rows.map(row=>({...row, values:Object.fromEntries(keys.map(key=>[key,row[key]==null?null:(row[key]/rows[0][key]-1)*100]))}));
  const all = values.flatMap(row=>Object.values(row.values)).filter(value=>value!=null);
  if (!all.length) return;
  const width = Math.max(260, Math.round(host.getBoundingClientRect().width));
  const height = 235, left = 48, right = width-15, top = 24, bottom = 200;
  const min = Math.min(0,...all), max = Math.max(0,...all), padding = Math.max(.5,(max-min)*.12);
  const low = min-padding, high = max+padding;
  const x = i=>left+i/(rows.length-1)*(right-left);
  const y = value=>bottom-(value-low)/(high-low)*(bottom-top);
  const grid = Array.from({length:4},(_,i)=>{const value=low+(high-low)*i/3;return `<line x1="${left}" x2="${right}" y1="${y(value)}" y2="${y(value)}" class="market-gridline"/><text x="${left-7}" y="${y(value)+4}" text-anchor="end">${value.toFixed(1)}%</text>`;}).join('');
  const lines = keys.map(key=>{
    let drawing=false;
    const path=values.map((row,i)=>{const value=row.values[key];if(value==null){drawing=false;return '';}const command=drawing?'L':'M';drawing=true;return `${command}${x(i).toFixed(1)},${y(value).toFixed(1)}`;}).join(' ');
    return `<path class="market-line market-color-${key}" d="${path}"><title>${esc(data.labels[key])}，期末 ${marketNumber(values.at(-1).values[key])}</title></path>`;
  }).join('');
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(days+'个交易日个股与市场同起点回报')}">${grid}<line class="market-zero" x1="${left}" x2="${right}" y1="${y(0)}" y2="${y(0)}"/>${lines}<text x="${left}" y="224">${esc(rows[0].date)}</text><text x="${right}" y="224" text-anchor="end">${esc(rows.at(-1).date)}</text><line class="market-guide" x1="${right}" x2="${right}" y1="${top}" y2="${bottom}"/><rect class="market-hit" x="${left}" y="${top}" width="${right-left}" height="${bottom-top}"/></svg>`;
  const readout = root.querySelector('.market-chart-readout');
  function inspect(index) {
    const row=values[index];
    readout.textContent=row.date+' · '+keys.map(key=>data.labels[key]+' '+marketNumber(row.values[key])).join('　');
    const guide=host.querySelector('.market-guide');guide.setAttribute('x1',x(index));guide.setAttribute('x2',x(index));
  }
  host.querySelector('.market-hit').onpointermove=event=>{
    const box=host.querySelector('svg').getBoundingClientRect();
    const position=(event.clientX-box.left)*width/box.width;
    inspect(Math.max(0,Math.min(rows.length-1,Math.round((position-left)/(right-left)*(rows.length-1)))));
  };
  inspect(values.length-1);
}

function buildBrokenSeriesSvg(rows, field, xFn, yFn) {
  let drawing = false;
  const segments = [];
  const dots = [];
  for (let i = 0; i < rows.length; i++) {
    const val = rows[i][field];
    if (val == null || !Number.isFinite(val)) {
      drawing = false;
      continue;
    }
    const px = xFn(i).toFixed(1), py = yFn(val).toFixed(1);
    segments.push(`${drawing ? 'L' : 'M'}${px},${py}`);
    const prevMissing = i === 0 || rows[i - 1][field] == null || !Number.isFinite(rows[i - 1][field]);
    const nextMissing = i === rows.length - 1 || rows[i + 1][field] == null || !Number.isFinite(rows[i + 1][field]);
    if (prevMissing && nextMissing) {
      dots.push(`<circle cx="${px}" cy="${py}" r="2.3"/>`);
    }
    drawing = true;
  }
  return { path: segments.join(' '), dots: dots.join('') };
}

function petroChinaPilotControlsMarkup(activeCode, viewState, refreshHtml) {
  return `<div class="market-controls">
      <label>股票 <select data-pilot-listing>
        <option value="601857.SH" ${activeCode === '601857.SH' ? 'selected' : ''}>A股 601857.SH（元/股）</option>
        <option value="00857.HK" ${activeCode === '00857.HK' ? 'selected' : ''}>H股 00857.HK（港元/股）</option>
      </select></label>
      <label>窗口 <select data-market-window>
        ${[60, 120, 252].map(n => `<option value="${n}" ${String(n) === String(viewState.days) ? 'selected' : ''}>${n} 个交易日</option>`).join('')}
      </select></label>
      <label>历史截止 <input type="date" data-pilot-as-of value="${esc(viewState.asOf || '')}" aria-label="历史截止日期"></label>
      ${viewState.asOf ? '<button type="button" class="btn secondary" data-pilot-reset-cutoff>最新</button>' : ''}
      ${refreshHtml}
    </div>`;
}

function petroChinaPilotLoadingMarkup(viewState) {
  const activeCode = viewState.listing || '601857.SH';
  const targetLabel = viewState.asOf || '最新收盘';
  const refresh = '<button class="btn secondary" data-market-refresh disabled>读取中…</button>';
  return `<div class="market-heading">
      <div>
        <h2>市场观察</h2>
        <p class="market-note">中国石油（601857.SH / 00857.HK） · 正在切换至观察截止 ${esc(targetLabel)}…</p>
      </div>
      ${petroChinaPilotControlsMarkup(activeCode, viewState, refresh)}
    </div>
    <p class="market-notice" role="status" data-pilot-loading="true">正在读取截至 ${esc(targetLabel)} 的行情、公告与披露状态，旧日期结果已清空…</p>`;
}

function petroChinaPilotMarkup(cid, data, viewState) {
  const refresh = `<button class="btn secondary" data-market-refresh ${data.refreshing ? 'disabled' : ''}>${data.refreshing ? '更新中…' : '更新行情'}</button>`;
  const trend = data.trend || {};
  const listings = trend.listings || {};
  const activeCode = listings[viewState.listing] ? viewState.listing : (trend.default_listing || '601857.SH');
  const stockMeta = listings[activeCode] || {
    code: activeCode,
    field: activeCode === '00857.HK' ? 'h_stock' : 'a_stock',
    name: activeCode === '00857.HK' ? '中国石油股份 H股 (00857.HK)' : '中国石油 A股 (601857.SH)',
    unit: activeCode === '00857.HK' ? '港元/股' : '元/股',
    adjustment: '前复权收盘',
  };
  const brentMeta = trend.brent || { code: 'BRENT', field: 'brent', name: '布伦特原油期货连续', unit: '美元/桶' };
  const cost = data.cost || {};
  const val = data.valuation || {};
  const updated = data.captured_at ? new Date(data.captured_at).toLocaleString('zh-CN', { timeZone: 'Asia/Hong_Kong', hour12: false }) : null;
  const anns = trend.announcements || [];
  const chartRows = (trend.chart || []).slice(-Number(viewState.days));
  const windowStart = chartRows[0]?.date || '';
  const windowAnns = windowStart ? anns.filter(a => a.published_on >= windowStart) : anns;
  const shownAnns = windowAnns.length ? windowAnns : anns.slice(-3);

  const cutoffIso = data.requested_through || cost.requested_through || '';
  const rawCostSources = Array.isArray(cost.sources)
    ? cost.sources
    : (cost.visible
        ? [
            ...(cost.source_url && (!cost.interim_report_published_on || !cutoffIso || cost.interim_report_published_on <= cutoffIso)
              ? [{ published_on: cost.interim_report_published_on || '2026-09-18', title: `中报原文：中国石油2026年中期报告（PDF第25页，${cost.interim_report_published_on || '2026-09-18'}刊发）`, url: cost.source_url }]
              : []),
            ...(cost.first_disclosure_url
              ? [{ published_on: cost.first_disclosed_on || '2026-08-30', title: `首次公开：2026年中期业绩公告（${cost.first_disclosed_on || '2026-08-30'}）`, url: cost.first_disclosure_url }]
              : []),
          ]
        : []);
  const costLinks = [
    ...rawCostSources
      .filter(s => s && s.url && (!s.published_on || !cutoffIso || s.published_on <= cutoffIso))
      .map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)} ↗</a>`),
    ...(cost.visible && cost.local_source_version && cost.local_doc_id && cost.local_doc_page && (!cost.interim_report_published_on || !cutoffIso || cost.interim_report_published_on <= cutoffIso)
      ? [`<button type="button" class="text-btn inline-source" data-model-action="source" data-cid="${esc(cid)}" data-version="${esc(cost.local_source_version)}" data-doc="${esc(cost.local_doc_id)}" data-page="${cost.local_doc_page}">本库固定资料 · 第${cost.local_doc_page}页 ↗</button>`]
      : []),
  ];

  return `<div class="market-heading">
      <div>
        <h2>市场观察</h2>
        <p class="market-note">中国石油（601857.SH / 00857.HK） · 观察截止 ${esc(data.requested_through || data.as_of || '-')}${data.as_of ? `（最近交易日 ${esc(data.as_of)}）` : ''}${data.brent_through && data.brent_through < (data.requested_through || '') ? ` · 布伦特已收盘截止 ${esc(data.brent_through)}` : ''}${data.custom_cutoff ? ' · 历史截止回看' : ''}</p>
      </div>
      ${petroChinaPilotControlsMarkup(activeCode, viewState, refresh)}
    </div>
    ${(data.errors || []).length || data.refresh_error ? `<p class="market-notice">${(data.errors || []).length ? '部分行情源暂未返回最新序列，缺失交易日已按断线或留空处理。' : ''}${esc(data.refresh_error || '')}</p>` : ''}

    <section class="pilot-block" data-pilot-section="trend" aria-label="1. 趋势">
      <div class="pilot-block-head">
        <h3>1. 趋势</h3>
        <span class="pilot-meta">股价单位：${esc(stockMeta.unit)}（${esc(stockMeta.adjustment)}） · 油价单位：${esc(brentMeta.unit)}（伦敦23:00收盘后收录）</span>
      </div>
      <p class="market-note">复用现有行情入口展示可悬停的股价与布伦特原油期货连续收盘走势（ICE 布伦特按伦敦时间 23:00 收盘截止，未收盘盘中价不进入日线）；休市或缺失行情直接断线，不插值补齐。不在历史股价上倒铺当前估值线，也不把国产原油特别收益金 65 美元/桶起征点画成布伦特触发线；A/H 溢价暂省略。</p>
      ${data.status === 'ready' && chartRows.length ? `
        <div class="market-plot pilot-trend-plot" aria-label="中国石油股价与布伦特油价趋势图"></div>
        <div class="market-legend">
          <span><i class="market-color-stock"></i>${esc(stockMeta.name)}（${esc(stockMeta.unit)}，截至 ${esc(stockMeta.last_date || '无数据')}）</span>
          <span><i class="pilot-color-brent"></i>${esc(brentMeta.name)}（${esc(brentMeta.unit)}，截至 ${esc(brentMeta.last_date || '无数据')}）</span>
          <span><b class="pilot-ann-dot">公</b>公告标记（点击图上标记或下方链接打开原文）</span>
        </div>
        <p class="pilot-trend-readout market-note" aria-live="off">移动到图表上可查看当日日期、股价与布伦特油价。</p>
      ` : `<p class="market-notice" role="status">${esc(data.reason || trend.reason || '正在读取中国石油与布伦特原油可比日线，稍后自动显示。')}</p>`}
      ${shownAnns.length ? `<div class="pilot-ann-list" aria-label="期间公司公告原文">${shownAnns.map(a => `<a class="pilot-ann-chip" href="${esc(a.url)}" target="_blank" rel="noopener"><span>${esc(a.published_on)}</span><strong>${esc(a.short_label)}</strong><small>${esc(a.title)} ↗</small></a>`).join('')}</div>` : ''}
    </section>

    <section class="pilot-block" data-pilot-section="cost" aria-label="2. 成本">
      <div class="pilot-block-head">
        <h3>2. 成本</h3>
        <span class="pilot-meta">报告期：${esc(cost.current_period)}（同比 ${esc(cost.prior_period)}） · 首次公开日期：${esc(cost.first_disclosed_on)}</span>
      </div>
      ${cost.visible ? `
        <div class="market-observations pilot-kpis">
          <div>
            <span>${esc(cost.prior_period)} · ${esc(cost.metric)}</span>
            <strong>${Number(cost.prior_value).toFixed(2)} ${esc(cost.unit)}</strong>
            <p>上年同期可比半年度口径</p>
          </div>
          <div>
            <span>${esc(cost.current_period)} · ${esc(cost.metric)}</span>
            <strong>${Number(cost.current_value).toFixed(2)} ${esc(cost.unit)}</strong>
            <p>2026年中期披露值（首次公开日 ${esc(cost.first_disclosed_on)}）</p>
          </div>
          <div>
            <span>同半年度同比变动</span>
            <strong>+${Number(cost.yoy_pct).toFixed(1)}%</strong>
            <p>同比上升 +${Number(cost.delta_value).toFixed(2)} ${esc(cost.unit)}</p>
          </div>
        </div>
      ` : `
        <div class="market-observations pilot-kpis" data-pilot-cost-blank="true">
          <div><span>${esc(cost.prior_period)} · ${esc(cost.metric)}</span><strong>—</strong><p>待公开日后显示同期对比</p></div>
          <div><span>${esc(cost.current_period)} · ${esc(cost.metric)}</span><strong>—</strong><p>截至 ${esc(cost.requested_through)} 尚未公开</p></div>
          <div><span>同半年度同比变动</span><strong>—</strong><p>避免在历史截止点混入事后披露</p></div>
        </div>
        <p class="market-notice">${esc(cost.blank_reason)}</p>
      `}
      <p class="market-note">${esc(cost.scope_note)}</p>
      ${costLinks.length ? `<p class="pilot-links">${costLinks.join(' · ')}</p>` : ''}
    </section>

    <section class="pilot-block" data-pilot-section="valuation" aria-label="3. 估值">
      <div class="pilot-block-head">
        <h3>3. 估值</h3>
        <span class="pilot-meta">研究快照：${esc(val.snapshot_date)} · 按 ${val.return_rate_pct}% 股权回报反算 · ${esc(val.tax_basis)}</span>
      </div>
      ${val.cutoff_precedes_snapshot ? `<p class="market-notice">当前观察截止日（${esc(data.requested_through)}）早于 ${esc(val.snapshot_date)}；以下仅展示 2026-11-13 正式企业书静态研究快照，不作为历史时点估值。</p>` : ''}
      <p class="market-note">${esc(val.note)}</p>
      <div class="market-observations pilot-kpis">
        <div>
          <span>主情景普通股现金</span>
          <strong>每年 ${ Number(val.base_normal_cash_yi).toLocaleString('zh-CN') } 亿元</strong>
          <p>10% 股权回报对应每股条件价值 ${val.base_epv_cny} 元 / ${val.base_epv_hkd} 港元</p>
        </div>
        <div>
          <span>H 股价格隐含年度现金门槛</span>
          <strong>约 ${ Number(val.h_implied_cash_yi).toLocaleString('zh-CN') } 亿元</strong>
          <p>正式版精确值 ${val.h_implied_cash_exact_yi} 亿元（按 ${val.h_close_hkd} 港元、汇率 ${val.hkd_cny} 反算）</p>
        </div>
        <div>
          <span>A 股价格隐含年度现金门槛</span>
          <strong>约 ${ Number(val.a_implied_cash_yi).toLocaleString('zh-CN') } 亿元</strong>
          <p>正式版精确值 ${val.a_implied_cash_exact_yi} 亿元（按 ${val.a_close_cny} 元人民币反算）</p>
        </div>
      </div>
      ${val.figure_url ? `<figure class="pilot-threshold-figure"><a href="${esc(val.figure_url)}" target="_blank" rel="noopener"><img src="${esc(val.figure_url)}" alt="${esc(val.figure_title)}" loading="lazy"></a><figcaption>${esc(val.figure_title)}（复用正式版企业书已有「年度现金门槛」配图 · 2026-11-13 快照）</figcaption></figure>` : ''}
      <div class="pilot-links">
        ${val.edition_valuation_url ? `<a class="btn secondary" data-pilot-edition-link href="${esc(val.edition_valuation_url)}">打开正式版本 · 现金与估值（${esc(val.edition_title)}） →</a> <a class="text-link" data-pilot-edition-overview href="${esc(val.edition_overview_url)}">打开正式版本全景 →</a>` : `<span class="market-note">尚未定位到匹配的 2026-11-13 正式版本快照（需同时匹配正式版标题、信息时点与固定资料版本）；运行 <code>python3 enterprise_research/research/petrochina_book_20261115/install.py</code> 后即可直达对应正式版本。</span>`}
        ${val.figure_url ? ` · <a href="${esc(val.figure_url)}" target="_blank" rel="noopener">独立打开年度现金门槛图 ↗</a>` : ''}
      </div>
    </section>

    <details class="market-monitor-method">
      <summary>行情来源与更新时间</summary>
      ${updated ? `<p class="market-note">最近抓取时间：${esc(updated)}（香港时间）</p>` : ''}
      ${(data.sources || []).map(source => `<p><a href="${esc(source.source_url)}" target="_blank" rel="noopener">${esc(source.name)} · ${esc(source.source)}</a> <small>截至 ${esc(source.last_date)}</small></p>`).join('') || '<p class="market-note">暂无已缓存行情源记录。</p>'}
      ${(data.errors || []).map(err => `<p class="market-note">${esc(err.code)} · ${esc(err.error)}</p>`).join('')}
    </details>`;
}

function drawPetroChinaTrendChart(root, data, viewState) {
  const host = root.querySelector('.pilot-trend-plot');
  if (!host || data.status !== 'ready') return;
  const trend = data.trend || {};
  const rows = (trend.chart || []).slice(-Number(viewState.days));
  if (!rows.length) return;
  const listings = trend.listings || {};
  const activeCode = listings[viewState.listing] ? viewState.listing : (trend.default_listing || '601857.SH');
  const stockMeta = listings[activeCode] || {
    code: activeCode,
    field: activeCode === '00857.HK' ? 'h_stock' : 'a_stock',
    name: activeCode === '00857.HK' ? '中国石油股份 H股' : '中国石油 A股',
    unit: activeCode === '00857.HK' ? '港元/股' : '元/股',
  };
  const brentMeta = trend.brent || { field: 'brent', name: '布伦特原油期货连续', unit: '美元/桶' };
  const brentThrough = brentMeta.requested_through || data.brent_through || '';
  const stockField = stockMeta.field;
  const stockVals = rows.map(r => r[stockField]).filter(v => v != null && Number.isFinite(v));
  const brentVals = rows.map(r => r.brent).filter(v => v != null && Number.isFinite(v));
  if (!stockVals.length && !brentVals.length) {
    host.innerHTML = '<p class="market-notice">所选窗口内暂无有效股价与布伦特油价数据。</p>';
    return;
  }

  const width = Math.max(300, Math.round(host.getBoundingClientRect().width || 680));
  const height = 310, left = 62, right = width - 18;
  const sTop = 22, sBottom = 132, bTop = 166, bBottom = 272;
  const x = i => rows.length <= 1 ? (left + right) / 2 : left + i / (rows.length - 1) * (right - left);

  function makeScale(vals, top, bottom) {
    if (!vals.length) return { low: 0, high: 1, y: () => (top + bottom) / 2, hasData: false };
    const min = Math.min(...vals), max = Math.max(...vals);
    const pad = max > min ? (max - min) * 0.14 : Math.max(0.4, Math.abs(max) * 0.05 || 1);
    const low = min - pad, high = max + pad;
    return { low, high, y: v => bottom - (v - low) / (high - low) * (bottom - top), hasData: true };
  }

  const sScale = makeScale(stockVals, sTop, sBottom);
  const bScale = makeScale(brentVals, bTop, bBottom);

  const sGrid = sScale.hasData ? [0, 0.5, 1].map(t => {
    const v = sScale.low + (sScale.high - sScale.low) * t, py = sScale.y(v);
    return `<line x1="${left}" x2="${right}" y1="${py.toFixed(1)}" y2="${py.toFixed(1)}" class="market-gridline"/><text x="${left - 8}" y="${(py + 4).toFixed(1)}" text-anchor="end">${v.toFixed(2)}</text>`;
  }).join('') : `<text x="${(left + right) / 2}" y="${(sTop + sBottom) / 2}" text-anchor="middle">该股票暂无日线数据</text>`;

  const bGrid = bScale.hasData ? [0, 0.5, 1].map(t => {
    const v = bScale.low + (bScale.high - bScale.low) * t, py = bScale.y(v);
    return `<line x1="${left}" x2="${right}" y1="${py.toFixed(1)}" y2="${py.toFixed(1)}" class="market-gridline"/><text x="${left - 8}" y="${(py + 4).toFixed(1)}" text-anchor="end">${v.toFixed(1)}</text>`;
  }).join('') : `<text x="${(left + right) / 2}" y="${(bTop + bBottom) / 2}" text-anchor="middle">布伦特原油暂无日线数据</text>`;

  const stockSeries = sScale.hasData ? buildBrokenSeriesSvg(rows, stockField, x, sScale.y) : { path: '', dots: '' };
  const brentSeries = bScale.hasData ? buildBrokenSeriesSvg(rows, 'brent', x, bScale.y) : { path: '', dots: '' };

  const indexByDate = new Map(rows.map((r, idx) => [r.date, idx]));
  const annsInPlot = (trend.announcements || []).map(a => {
    const idx = a.plot_date != null && indexByDate.has(a.plot_date)
      ? indexByDate.get(a.plot_date)
      : rows.findIndex(r => r.date >= a.published_on);
    return (idx >= 0 && a.published_on >= rows[0].date && a.published_on <= (data.requested_through || rows.at(-1).date))
      ? { ...a, idx }
      : null;
  }).filter(Boolean);

  const annByIdx = new Map();
  annsInPlot.forEach(a => {
    if (!annByIdx.has(a.idx)) annByIdx.set(a.idx, []);
    annByIdx.get(a.idx).push(a);
  });

  const annPins = annsInPlot.map((a, order) => {
    const px = x(a.idx).toFixed(1);
    const badgeY = (order % 2 === 0 ? sBottom + 17 : sBottom + 29);
    return `<a class="pilot-ann-pin" href="${esc(a.url)}" target="_blank" rel="noopener" aria-label="${esc(a.published_on + ' ' + a.title)}">
      <title>${esc(a.published_on + ' · ' + a.title + '（点击打开原文）')}</title>
      <line x1="${px}" x2="${px}" y1="${sTop}" y2="${bBottom}" class="pilot-ann-line"/>
      <circle cx="${px}" cy="${badgeY}" r="7.5" class="pilot-ann-circle"/>
      <text x="${px}" y="${badgeY + 3.5}" text-anchor="middle" class="pilot-ann-text">公</text>
    </a>`;
  }).join('');

  const midIdx = Math.floor((rows.length - 1) / 2);
  const dateTicks = (rows.length > 2 ? [0, midIdx, rows.length - 1] : [0]).map((idx, pos, arr) =>
    `<text x="${x(idx).toFixed(1)}" y="296" text-anchor="${pos === 0 ? 'start' : pos === arr.length - 1 ? 'end' : 'middle'}">${esc(rows[idx].date)}</text>`
  ).join('');

  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(stockMeta.name + '与布伦特原油走势')}">
    <text x="${left}" y="${sTop - 7}" class="pilot-lane-label">${esc(stockMeta.name)} · 单位：${esc(stockMeta.unit)}</text>
    ${sGrid}
    ${stockSeries.path ? `<path class="market-line market-color-stock" data-series="stock" d="${stockSeries.path}"/>` : ''}
    <g class="pilot-isolated-dots" data-dots="stock">${stockSeries.dots}</g>
    <text x="${left}" y="${bTop - 7}" class="pilot-lane-label">${esc(brentMeta.name)} · 单位：${esc(brentMeta.unit)}</text>
    ${bGrid}
    ${brentSeries.path ? `<path class="market-line pilot-color-brent" data-series="brent" d="${brentSeries.path}"/>` : ''}
    <g class="pilot-isolated-dots" data-dots="brent">${brentSeries.dots}</g>
    ${dateTicks}
    <line class="market-guide" x1="${x(rows.length - 1).toFixed(1)}" x2="${x(rows.length - 1).toFixed(1)}" y1="${sTop}" y2="${bBottom}"/>
    <circle class="pilot-hover-dot pilot-hover-stock" r="3.6" style="display:none"/>
    <circle class="pilot-hover-dot pilot-hover-brent" r="3.6" style="display:none"/>
    ${annPins}
  </svg>`;

  const svg = host.querySelector('svg');
  const guide = host.querySelector('.market-guide');
  const sDot = host.querySelector('.pilot-hover-stock');
  const bDot = host.querySelector('.pilot-hover-brent');
  const readout = root.querySelector('.pilot-trend-readout');

  function inspect(index) {
    const row = rows[index];
    const px = x(index);
    guide.setAttribute('x1', px.toFixed(1));
    guide.setAttribute('x2', px.toFixed(1));
    const sv = row[stockField], bv = row.brent;
    if (sv != null && Number.isFinite(sv) && sScale.hasData) {
      sDot.style.display = '';
      sDot.setAttribute('cx', px.toFixed(1));
      sDot.setAttribute('cy', sScale.y(sv).toFixed(1));
    } else {
      sDot.style.display = 'none';
    }
    if (bv != null && Number.isFinite(bv) && bScale.hasData) {
      bDot.style.display = '';
      bDot.setAttribute('cx', px.toFixed(1));
      bDot.setAttribute('cy', bScale.y(bv).toFixed(1));
    } else {
      bDot.style.display = 'none';
    }
    const stockText = sv != null && Number.isFinite(sv) ? `${sv.toFixed(2)} ${stockMeta.unit}` : '无行情（断线）';
    const brentText = bv != null && Number.isFinite(bv)
      ? `${bv.toFixed(2)} ${brentMeta.unit}`
      : (brentThrough && row.date > brentThrough ? '当日未收盘（待伦敦23:00收盘）' : '无行情（断线）');
    const dayAnns = annByIdx.get(index);
    const annText = dayAnns ? ' · 公告：' + dayAnns.map(a => `${a.published_on} ${a.short_label}`).join('、') : '';
    if (readout) {
      readout.textContent = `${row.date} · ${stockMeta.code}：${stockText} · 布伦特原油：${brentText}${annText}`;
    }
  }

  svg.addEventListener('pointermove', event => {
    const box = svg.getBoundingClientRect();
    if (!box.width) return;
    const pos = (event.clientX - box.left) * width / box.width;
    const idx = rows.length <= 1 ? 0 : Math.max(0, Math.min(rows.length - 1, Math.round((pos - left) / (right - left) * (rows.length - 1))));
    inspect(idx);
  });
  inspect(rows.length - 1);
}

function bindMarketContext() {
  const root=document.querySelector('[data-market-company]');
  if (!root) return;
  if (root.hasAttribute('data-observation')) {
    const bind = () => { if (root.isConnected) bindMarketObservation(root); };
    if (typeof bindMarketObservation === 'function') return bind();
    const script = document.createElement('script');
    script.src = '/market-observation.js';
    script.onload = bind;
    script.onerror = () => {
      if (root.isConnected) root.querySelector('[role="status"]').textContent = '市场观察脚本加载失败，请刷新页面重试。';
    };
    document.head.append(script);
    return;
  }
  const cid=root.dataset.marketCompany;
  const hashParams=new URLSearchParams(location.hash.split('?')[1]||'');
  let data, days='20', pilotDays='120', pilotListing='', pilotAsOf=hashParams.get('market_as_of')||'';
  let polling, resize, monitorRun='', requestSeq=0, loadingState=false;
  function bindPilotControls() {
    root.querySelector('[data-market-refresh]')?.addEventListener('click',()=>load(true));
    root.querySelector('[data-market-window]')?.addEventListener('change',event=>{pilotDays=event.target.value;display();});
    root.querySelector('[data-pilot-listing]')?.addEventListener('change',event=>{pilotListing=event.target.value;display();});
    root.querySelector('[data-pilot-as-of]')?.addEventListener('change',event=>{pilotAsOf=event.target.value;load(false,true);});
    root.querySelector('[data-pilot-reset-cutoff]')?.addEventListener('click',()=>{pilotAsOf='';load(false,true);});
  }
  function display() {
    if (!root.isConnected) { resize?.disconnect(); clearTimeout(polling); return; }
    resize?.disconnect();
    const isPetroShell = root.getAttribute('aria-label')==='市场观察' || data?.pilot==='petrochina_market_v1';
    if (loadingState && isPetroShell) {
      const viewState={days:pilotDays,listing:pilotListing||'601857.SH',asOf:pilotAsOf};
      root.innerHTML=petroChinaPilotLoadingMarkup(viewState);
      bindPilotControls();
      return;
    }
    if (data?.pilot==='petrochina_market_v1') {
      if (!pilotListing) pilotListing=data.trend?.default_listing||data.code||'601857.SH';
      const viewState={days:pilotDays,listing:pilotListing,asOf:pilotAsOf};
      root.innerHTML=petroChinaPilotMarkup(cid,data,viewState);
      bindPilotControls();
      const plotHost=root.querySelector('.pilot-trend-plot');
      if (data.status==='ready' && plotHost) {
        drawPetroChinaTrendChart(root,data,viewState);
        if (typeof ResizeObserver==='function') {
          resize=new ResizeObserver(()=>{if(root.isConnected)drawPetroChinaTrendChart(root,data,viewState);else resize.disconnect();});
          resize.observe(plotHost);
        }
      }
      return;
    }
    root.innerHTML=industryMonitorMarkup(data.valuation_monitor)+marketContextMarkup(data,days);
    root.querySelector('[data-market-refresh]')?.addEventListener('click',()=>load(true));
    root.querySelector('[data-market-window]')?.addEventListener('change',event=>{days=event.target.value;display();});
    root.querySelector('[data-industry-version]')?.addEventListener('change',event=>{monitorRun=event.target.value;load();});
    root.querySelector('[data-industry-retry]')?.addEventListener('click',async event=>{
      event.target.disabled=true;
      try{await api(`/api/monitor-jobs/${encodeURIComponent(event.target.dataset.industryRetry)}/retry`,{method:'POST'});monitorRun='';load();}
      catch(error){event.target.disabled=false;alert(error.message);}
    });
    if (data.status==='ready') {
      drawMarketChart(root,data,days);
      drawSectorChart(root,data);
      resize=new ResizeObserver(()=>{if(root.isConnected){drawMarketChart(root,data,days);drawSectorChart(root,data);}else resize.disconnect();});
      resize.observe(root.querySelector('.market-current-plot'));
    }
  }
  async function load(force=false, clearPrevious=false) {
    const seq=++requestSeq;
    clearTimeout(polling);
    if (!root.isConnected) { resize?.disconnect(); return; }
    if (clearPrevious) {
      data=undefined;
      loadingState=true;
      display();
    } else {
      const button=root.querySelector('[data-market-refresh]');if(button)button.disabled=true;
    }
    try {
      if(force)monitorRun='';
      const qs=new URLSearchParams();
      if(!force&&monitorRun)qs.set('run',monitorRun);
      if(!force&&pilotAsOf)qs.set('as_of',pilotAsOf);
      const suffix=force?'/refresh':(qs.toString()?'?'+qs.toString():'');
      const opts=force?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pilotAsOf?{as_of:pilotAsOf}:{})}:{};
      const next=await api(`/api/companies/${encodeURIComponent(cid)}/market-context${suffix}`,opts);
      if(seq!==requestSeq || !root.isConnected)return;
      loadingState=false;
      data=next;
      display();
      if(data.refreshing && root.isConnected)polling=setTimeout(()=>{if(seq===requestSeq && root.isConnected)load();},3000);
    } catch(error) {
      if(seq!==requestSeq || !root.isConnected)return;
      loadingState=false;
      const heading=root.getAttribute('aria-label')==='市场观察'?'市场观察':'市场环境与主导力量';
      root.innerHTML=`<h2>${heading}</h2><p>${esc(error.message)}</p><button class="btn secondary" data-market-refresh>重新读取</button>`;
      root.querySelector('[data-market-refresh]')?.addEventListener('click',()=>load(true));
    }
  }
  load();
}
