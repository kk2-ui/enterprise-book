'use strict';
function industryMonitorMarkup(m) {
  if(!m)return '';
  const c=m.company, research=c.research, econ=c.economic, g=m.groups[c.group], job=m.latest_job;
  const num=(v,s='倍')=>v==null?'尚不能计算':Number(v).toFixed(2)+s;
  const pe=c.pe_ttm.value,pb=c.pb.value;
  const position=m.peer_position?.pe;
  const broad=m.index_valuations?.find(x=>x.index==='HSCI');
  const qs='?run='+encodeURIComponent(m.run_id);
  return `<section class="industry-monitor" aria-label="行业估值与经济研究">
    <div class="industry-title"><div><p class="eyebrow">估值为锚 · 市场环境辅助</p><h2>便宜程度与行业位置</h2></div><a class="btn secondary" href="/api/industries/property/monitor/export${qs}" target="_blank" rel="noopener">行业明细与完整报告 ↗</a></div>
    <p class="market-note">行情 ${esc(m.as_of)} · 财报 ${esc(c.financial_period||'未核定')} · 股本 ${esc(c.shares_date||'未核定')} · 研究 ${esc(research?.as_of||'尚未完成')}</p>
    ${m.status==='partial'?'<p class="market-notice">本批覆盖尚不完整。报表便宜程度与经济重估分别展示，未采用的研究不产生低估结论。</p>':''}
    <div class="industry-metrics"><div><span>报表 PE TTM</span><strong>${num(pe)}</strong><p>基础物业中位数 ${num(g.pe.median)}<br>整体PE ${num(g.pe.overall.value)} · ${g.pe.valid}/${g.pe.selected}家同口径</p></div>
      <div><span>报表 PB</span><strong>${num(pb)}</strong><p>按归母权益计算<br>行业中位数 ${num(g.pb.median)}</p></div>
      <div><span>价格 / 已采用条件 EPV</span><strong>${econ?.epv?.price_to_value==null?'尚未形成':num(econ.epv.price_to_value)}</strong><p>${econ?.epv?`采用 ${(econ.epv.capital_cost*100).toFixed(0)}% 资本成本情景；展开可见假设与反方。`:'正常盈利、可持续股东现金与资产调整须分别核实，不能由低PE直接推断。'}</p></div></div>
    ${econ?`<p>${esc(econ.boundary)}。研究 ${esc(econ.research_date)}，本批引用 ${esc(econ.adopted_on)}。</p>`:''}
    ${position&&pe!=null?`<p>排除保利后，${position.positive_multiple_count}家有正PE；其中${position.lower_count}家倍数低于保利。便宜排序不代表质量排序。</p>`:''}
    <p>自身历史位置：${['pe','pb'].map(k=>{const h=c.historical_percentiles?.[k];return h?.value==null?`${k.toUpperCase()}尚无足够有效月末值`:`${k.toUpperCase()}为第${h.value.toFixed(1)}百分位（${h.count}个月，${h.start}至${h.end}）`;}).join('；')}。历史低位不是已证明的内在低估。</p>
    <p class="market-note">基础物业 ${m.coverage.economic_research}/${m.coverage.basic}家已采用逐项研究；盈利比率含亏损有效${g.pe.valid}家，非正利润${g.pe.nonpositive}家。有效分母覆盖可取得市值的${(g.pe.market_cap_coverage*100).toFixed(1)}%，缺价公司另列。</p>
    ${broad?`<p class="market-note">恒生综合官方PE ${num(broad.pe)}（${esc(broad.as_of)}），股息率 ${broad.dividend_yield==null?'未披露':(broad.dividend_yield*100).toFixed(2)+'%'}。指数估值沿用官方口径，历史估值分位待数据补齐。</p>`:''}
    <details><summary>展开估值分母、调整和会改变判断的缺口</summary><p>总普通股市值 ${c.market_cap==null?'尚不能计算':(c.market_cap/1e8).toFixed(2)+'亿港元'}；经营现金减资本开支筛查比率 ${num(c.cash_proxy_multiple.value)}，尚非可分配股东现金。过去一年税前现金股息率 ${c.dividend_yield==null?'未核定':(c.dividend_yield*100).toFixed(2)+'%'}（含特别股息，不作未来承诺）。</p>
      ${econ?`<p>${esc(econ.operating_earnings_label||'正常经营收益未核定')}：${econ.operating_earnings_yield==null?'未核定':(econ.operating_earnings_yield*100).toFixed(2)+'%'}。</p><p>普通股现金：${esc(econ.owner_cash_reason||'见逐项现金计算')}。</p><p>${esc(research.current_view)}</p><p>反方与改判依据：${esc(research.rival)}</p>`:''}
      <ul>${c.issues.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
      ${c.adjustments.map(a=>`<p><b>${esc(a.key)}</b> · ${esc(a.status)}<br>${esc(a.reason)}<br>依据：${esc(a.basis)}<br>反方：${esc(a.rival)}</p>`).join('')}
      <a href="/api/research-subjects/${encodeURIComponent(c.subject_id)}/monitor${qs}" target="_blank" rel="noopener">冻结输入与研究数据</a> · <a href="/api/industries/property/monitor/export${qs}#${encodeURIComponent(c.subject_id)}" target="_blank" rel="noopener">本公司详细研究</a></details>
    ${job?`<p class="market-note" role="status">更新任务 ${esc(job.status)}${job.phase?' · '+esc(job.phase):''}${job.reason?' · '+esc(job.reason):''}${job.failures?.length?' · '+job.failures.length+'项取得问题':''}</p>${['failed','interrupted','needs_research'].includes(job.status)?`<button class="btn secondary" data-industry-retry="${esc(job.id)}">重试未完成任务</button>`:''}`:''}
    ${m.versions?.length?`<label class="market-note">已发布快照 <select data-industry-version>${m.versions.map(v=>`<option value="${esc(v.id)}" ${v.id===m.run_id?'selected':''}>${esc(v.as_of)} · ${esc(v.id)}</option>`).join('')}</select></label>`:''}
    <p class="market-note">${esc(m.boundary)} · 快照 ${esc(m.run_id)}</p></section>`;
}
