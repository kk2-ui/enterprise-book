'use strict';

function marketContextShell(c) {
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

function bindMarketContext() {
  const root=document.querySelector('[data-market-company]');
  if (!root) return;
  const cid=root.dataset.marketCompany;
  let data, days='20', polling, resize, monitorRun='';
  function display() {
    if (!root.isConnected) { resize?.disconnect(); clearTimeout(polling); return; }
    resize?.disconnect();
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
  async function load(force=false) {
    clearTimeout(polling);
    if (!root.isConnected) { resize?.disconnect(); return; }
    const button=root.querySelector('[data-market-refresh]');if(button)button.disabled=true;
    try {
      if(force)monitorRun='';
      data=await api(`/api/companies/${encodeURIComponent(cid)}/market-context${force?'/refresh':monitorRun?'?run='+encodeURIComponent(monitorRun):''}`,force?{method:'POST'}:{});
      display();
      if(data.refreshing && root.isConnected)polling=setTimeout(()=>load(),3000);
    } catch(error) {
      if(root.isConnected)root.innerHTML=`<h2>市场环境与主导力量</h2><p>${esc(error.message)}</p><button class="btn secondary" data-market-refresh>重新读取</button>`;
      root.querySelector('[data-market-refresh]')?.addEventListener('click',()=>load(true));
    }
  }
  load();
}
