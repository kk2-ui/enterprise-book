/* A selected book owns its complete text and calculations. Shared evidence stays shared. */
let activeEditionCompany=null;
const editionParams=()=>new URLSearchParams(location.hash.split('?')[1]||'');
const editionURL=(cid,id,view='overview',extra={})=>`#/company/${cid}/editions?`+new URLSearchParams({edition:id,view,...extra});
function preferredBookLocation(c,tab){
 const params=editionParams();
 if(!c.default_book_edition_id||params.has('draft')||(tab==='topics'&&params.has('topic')))return null;
 const edition=c.book_editions?.find(e=>e.id===c.default_book_edition_id);
 const view=({overview:'overview',life:'life',book:'book',topics:'topics',research:'research',finance:'valuation',sources:'sources',track:'track',history:'history',judgment:'judgment'})[tab];
 if(!edition||!view)return null;
 const chapter=params.get('chapter');
 return editionURL(c.id,edition.id,view,view==='book'&&chapter!==null?{chapter}:{});
}
const modelName=e=>`${e.model?.name||'未登记模型'}${e.model?.version?' · '+e.model.version:' · 精确版本未登记'}`;
function modelShelf(c){return `<div class="book-model-bar"><label>企业书版本<select id="model-book-select" aria-label="选择模型企业书"><option value="">当前协作稿</option>${(c.book_editions||[]).map(e=>`<option value="${esc(e.id)}" ${route.tab==='editions'&&editionParams().get('edition')===e.id?'selected':''}>${esc(e.title)}${e.model?.version?' · '+esc(e.model.version):''}</option>`).join('')}</select></label><div class="button-row"><a class="text-link" href="#/company/${c.id}/editions">全部模型版本</a><button class="btn secondary" data-model-action="task-new" data-cid="${c.id}">创建外部 Agent 任务</button></div></div>`;}
function frozenHTML(html,c,e){const box=document.createElement('div');box.innerHTML=html;box.querySelectorAll('a[href]').forEach(a=>{const u=a.getAttribute('href');const m=u.match(/^#\/company\/([^/]+)\/([^?]+)(?:\?(.*))?$/);if(m&&m[1]===c.id&&['overview','book','topics','finance','research','history','life','track','business','ownership','regions','products'].includes(m[2])){a.href=editionURL(c.id,e.id,m[2]==='finance'?'valuation':m[2],Object.fromEntries(new URLSearchParams(m[3]||'')));}});box.querySelectorAll('select[data-task]').forEach(s=>{const label=document.createElement('span');label.textContent=s.value;s.replaceWith(label);});box.querySelectorAll('button').forEach(b=>{if(!b.dataset.modelAction&&!/^(d-|b-|source$|topic-figure$)/.test(b.dataset.action||''))b.remove();});return box.innerHTML;}
function modelBody(text,c,version){const refs=[];const raw=(text||'').replace(/\[\[doc:([\w-]+)@(\d+)\|([^\]\n]+)\]\]/g,(_,id,page,label)=>{refs.push(`<button class="text-btn inline-source" data-model-action="source" data-cid="${c.id}" data-version="${esc(version)}" data-doc="${id}" data-page="${page}">${esc(label)} · 第${page}页 ↗</button>`);return `MODELREF${refs.length-1}END`;});return topicBody(raw,c).replace(/MODELREF(\d+)END/g,(_,i)=>refs[Number(i)]);}
function modelPart(c,e,key){const p=e.parts[key];return p?`<article class="model-book-prose document"><h2>${esc(p.title)}</h2>${modelBody(p.body,c,e.source_version)}</article>`:empty('本版未保存这部分内容','历史成稿按当时内容保留；请从版本选择切换到已补全的新稿。');}

function modelOverview(base,e,context){
 const p=e.parts.overview,data=p.display||{};
 const c={...base,fixedOverviewSource:e.source_version,dossier:{
  as_of:e.information_cutoff,subtitle:data.subtitle||'企业全景',intro:data.intro||'',
  cover_period_text:data.cover_period_text,identity:data.identity||[],
  metrics:data.metrics||{},series:data.series||[],overview:{
   identity_refs:[],revenue_title:'营业收入',revenue_note:'',
   cash_title:'经营现金净额',cash_keys:['cfo'],cash_note:'',...data.overview
  },
  insights:[],gaps:[],chapters:Array.from({length:8},(_,i)=>e.parts['chapter-'+(i+1)])
 }};
 context.company=c;
 const valueLink=`<a class="text-link" href="#/company/${c.id}/finance">查看现金与估值 ${icon('arrow',15)}</a>`;
 const value=data.valuation;
 const current=`<div class="d-current"><section>${modelBody(e.parts.judgment.body,c,e.source_version)}</section><aside>${value?`<span>普通股正常现金</span><strong>${esc(value.cash)}</strong><p>${esc(value.cash_label)}</p><div class="divider"></div><span>既有条件价值</span><b>${esc(value.value)}</b><p>${esc(value.value_label)}</p>`:''}${valueLink}</aside></div>`;
 context.cover=frozenHTML(dCover(c),c,e);
 const content=dOverview(c,{
  analysis:modelPart(c,e,'overview'),current,
  market:!data.historical&&base.default_book_edition_id===e.id?marketContextShell(c):'',
  gaps:`<section class="research-gaps"><div><span class="eyebrow">OPEN QUESTIONS</span><h2>还没有被材料解决的问题</h2></div><div class="document">${modelBody(e.parts.gaps.body,c,e.source_version)}</div></section>`
 });
 return frozenHTML(content,c,e);
}
function legacyResearch(c,e){const p=e.research;if(!p)return empty('没有关联研究','本版未登记独立研究。');return `<section class="model-book-prose"><h2>${esc(p.title)}</h2>${['question','current_view','rival','next_step'].map(k=>p[k]?`<div class="document">${researchProse(p[k],c)}</div>`:'').join('')}${p.entries.map(x=>`<section><h3>${esc(x.title)}</h3><div class="document">${researchProse(x.body,c)}</div></section>`).join('')}${e.calculations.map(x=>`<section><h3>${esc(x.title)}</h3>${researchResult(x,c)}</section>`).join('')}</section>`;}
async function editionsView(base,context={}){const p=editionParams(),id=p.get('edition'),list=base.book_editions||[];
 if(!id){const jobs=await api(`/api/companies/${base.id}/book-tasks`);return `<section class="panel"><h2>模型企业书</h2><p>每个版本是一整本独立内容。模型、资料时点与审阅状态分别保留。</p><div class="model-part-grid">${list.map(e=>`<a href="${editionURL(base.id,e.id)}"><span class="eyebrow">${esc(modelName(e))}</span><h3>${esc(e.title)}</h3><p>${esc(e.information_cutoff||'时点未登记')} · ${e.review_status==='independent_review'?'已独立审阅 · 待用户阅读':e.review_status==='not_reviewed'?'模型成稿 · 未独立审阅':'历史协作稿'}</p><span>打开完整企业书 →</span></a>`).join('')||'<p>尚无保存的整本版本。</p>'}</div></section><section class="panel"><div class="panel-head"><h2>外部 Agent 研究任务</h2><button class="btn secondary" data-model-action="refresh">刷新进度</button></div>${jobs.map(t=>`<article class="model-task-row"><h3>${esc(t.title)}</h3><p>${esc(modelName(t))} · ${esc(({waiting:'等待 Agent 接入',running:'研究与写作中',failed:'执行中断',completed:'整本已保存'})[t.status])} · 已存 ${t.saved_parts.length} 个部分</p><p class="small muted">资料版本 ${esc(t.source_version)} · ${esc(t.message||'')}</p><button class="text-btn" data-model-action="task-open" data-cid="${base.id}" data-task="${t.id}">打开任务与接入说明 →</button>${t.edition_id?` <a href="${editionURL(base.id,t.edition_id)}">阅读成稿 →</a>`:''}</article>`).join('')||empty('尚无外部任务','创建任务后，把接入指令交给有本机工具访问能力的 Agent；它会直接从系统读写。')}</section>`;}
 const e=await api(`/api/companies/${base.id}/books/${id}`),view=p.get('view')||'overview';let content='';
 const nav=[['overview','企业全景'],['book','八章总论'],['topics','专题研究'],['life','生命周期'],['history','长期财务'],['track','跟踪与复盘'],['judgment','判断'],['valuation','现金与估值'],['research','依据与研究']];
 nav.splice(1,0,['market','市场观察']);
 if(e.source_version)nav.push(['sources','本版资料']);
 if(view==='market'){
  content=marketObservationShell(base,e);
 }else if(view==='sources'&&e.source_version){
  content=await sourceVersionView(base,e.source_version);
 }else if(e.format==='legacy_snapshot'){
  const c=structuredClone(e.snapshot);context.company=c;
  if(view==='overview'){
   context.cover=frozenHTML(dCover(c),c,e);
   content=dOverview(c,{market:frameworkPanel(c,true)});
  }
  else if(view==='book')content=dDeepBook(c);
  else if(view==='topics'){const selected=e.topics.find(x=>x.id===p.get('topic'));content=selected?`<a href="${editionURL(c.id,e.id,'topics')}">← 本版全部专题</a><article class="model-book-prose document"><h2>${esc(selected.title)}</h2>${topicBody(selected.body,c)}</article>`:`<div class="model-part-grid">${e.topics.map(t=>`<a href="${editionURL(c.id,e.id,'topics',{topic:t.id})}"><h3>${esc(t.title)}</h3><p>${esc(t.summary||'')} · r${t.revision}</p></a>`).join('')}</div>`;}
  else if(view==='valuation')content=finance(c);
  else if(view==='judgment'){const j=judgment(c);content=`<article class="model-book-prose"><h2>本版综合判断</h2><p>${esc(j.body)}</p><h3>主要反方</h3><p>${esc(j.rival)}</p><h3>翻转条件</h3><p>${esc(j.triggers)}</p><a href="${editionURL(c.id,e.id,'book',{chapter:6})}">阅读第七章完整判断 →</a></article>`;}
  else if(['business','ownership','regions','products'].includes(view)&&c.dossier?.business_detail)content=({business:bBusiness,ownership:bOwnership,regions:bRegions,products:bProducts})[view](c);
  else if(view==='history')content=dHistory(c);else if(view==='life')content=dLife(c);else if(view==='track')content=track(c);else content=legacyResearch(c,e);
  content=`<div class="legacy-model-view">${frozenHTML(content,c,e)}</div>`;
 }else{
  if(view==='overview')content=modelOverview(base,e,context);
  else if(view==='book'){const ix=Math.max(0,Math.min(7,Number(p.get('chapter'))||0));content=`<div class="model-read-layout"><aside class="model-read-index">${Array.from({length:8},(_,i)=>`<a class="${i===ix?'selected':''}" href="${editionURL(base.id,id,'book',{chapter:i})}">${i+1}. ${esc(e.parts['chapter-'+(i+1)].title)}</a>`).join('')}</aside>${modelPart(base,e,'chapter-'+(ix+1))}</div>`;}
  else if(view==='topics'){
   const keys=Object.keys(e.parts).filter(k=>k.startsWith('topic-'));
   if(p.get('topic'))content=modelPart(base,e,p.get('topic'));
   else{
    const links=keys.length?keys.map(k=>[editionURL(base.id,id,'topics',{topic:k}),e.parts[k].title]):
     [1,2,3].map(i=>[editionURL(base.id,id,'book',{chapter:i}),e.parts['chapter-'+(i+1)].title]);
    content=`<div class="model-part-grid">${links.map(([url,title])=>`<a href="${esc(url)}">${esc(title)}</a>`).join('')}</div>`;
   }
  }
  else if(view==='research')content=['assumptions','calculations','references','gaps'].map(k=>modelPart(base,e,k)).join('')+(e.additional_sources?.length?`<section class="panel"><h3>本模型另行补充的资料</h3>${e.additional_sources.map(x=>`<p>${esc(x.title)} ${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">原始出处 ↗</a>`:srcButton(x.source_id)}</p>`).join('')}</section>`:'');
  else content=modelPart(base,e,['overview','judgment','valuation','life','history','track'].includes(view)?view:'overview');
 }
 return `<div class="edition-meta"><strong>${esc(e.title)}</strong><p>${esc(modelName(e))} · 信息时点 ${esc(e.information_cutoff||'未登记')} · ${e.review_status==='independent_review'?'本版已独立审阅，待用户阅读验收':e.review_status==='not_reviewed'?'模型成稿，尚未独立审阅':'沿用历史稿的实际审阅范围'}</p><p class="small muted">${esc(e.provenance)}${e.source_version?' · 资料版本 '+esc(e.source_version):''}</p></div><nav class="edition-tabs">${nav.map(([k,l])=>`<a class="${view===k?'selected':''}" href="${editionURL(base.id,id,k)}">${l}</a>`).join('')}</nav>${content}`;
}
async function sourceVersionView(c,v=editionParams().get('version')){if(!v)return empty('选择资料版本','从资料档案打开固定版本。');const m=await api(`/api/companies/${c.id}/data/versions/${v}`);return `<section class="panel"><div class="panel-head"><div><h2>共用资料 · ${esc(m.information_cutoff)}</h2><p>${m.documents.length}份原件与全文 · ${m.disclosed_cells}个披露数据 · 原件版本固定</p></div><button class="btn primary" data-model-action="task-new" data-cid="${c.id}" data-version="${esc(v)}">用此版本创建 Agent 任务</button></div><form id="version-search" data-cid="${c.id}" data-version="${esc(v)}" class="button-row"><input name="q" required placeholder="在本版本全文中检索" aria-label="资料全文检索词"><button class="btn secondary">检索</button></form><div id="version-search-results"></div><details><summary>覆盖与缺口</summary>${m.coverage.concat(m.gaps).map(x=>`<p>${esc(x)}</p>`).join('')}</details><div class="model-source-list">${m.documents.map(d=>`<article><h3>${esc(d.title)}</h3><p>${esc(d.issuer)} · ${esc(d.fact_period)} · ${d.page_count}页 · ${esc(sourceNatureLabels[d.nature])}</p><button class="text-btn" data-model-action="source" data-cid="${c.id}" data-version="${esc(v)}" data-doc="${d.id}" data-page="1">按页阅读全文 →</button> <a href="${d.original_url}" target="_blank">打开原件 ↗</a></article>`).join('')}</div></section>`;}
async function modelSource(cid,v,did,page=1){const d=await api(`/api/companies/${cid}/data/versions/${v}/documents/${did}?start_page=${page}`);showDialog(d.document.title,`<p>本资料版本 · 第 ${page} / ${d.document.page_count} 页 · ${esc(d.document.issuer)}</p><div class="button-row">${page>1?`<button class="btn secondary" data-model-action="source" data-cid="${cid}" data-version="${v}" data-doc="${did}" data-page="${page-1}">上一页</button>`:''}${d.next_page?`<button class="btn secondary" data-model-action="source" data-cid="${cid}" data-version="${v}" data-doc="${did}" data-page="${d.next_page}">下一页</button>`:''}<a href="${d.document.original_url}#page=${page}" target="_blank">原件对应页 ↗</a></div><pre class="source-page-text">${esc(d.pages[0].text)}</pre>`,true);}
async function bookTaskForm(cid,selected=''){const versions=await api(`/api/companies/${cid}/data/versions`);showDialog('创建外部 Agent 企业书任务',`<form id="book-task-form" class="editor-form"><p>Agent直接读取系统资料并分批写回整书。创建任务后将接入指令交给外部Agent，本系统不会自动启动外部模型。</p><label>模型名称<input name="name" placeholder="填写实际使用的模型名称" required></label><label>精确模型版本<input name="version" placeholder="未知可留空，由执行方回填"></label><label>企业书名称<input name="title" placeholder="例如：格力 · 某模型独立研究" required></label><label>共用资料版本<select name="source_version" required>${versions.map(v=>`<option value="${esc(v.id)}" ${v.id===selected?'selected':''}>${esc(v.title.replace('独立分析资料包','共用资料'))} · 截至${esc(v.information_cutoff)}</option>`).join('')}</select></label>${versions.length?'':'<p>尚无固定资料版本，请先在资料档案固定所需资料。</p>'}<div role="alert"></div><button class="btn primary" ${versions.length?'':'disabled'}>创建任务</button></form>`,true);$('#book-task-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{const t=await api(`/api/companies/${cid}/book-tasks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:f.get('title'),model:{name:f.get('name'),version:f.get('version')},source_version:f.get('source_version')})});await refresh();await bookTaskDialog(cid,t.id);}catch(err){e.target.querySelector('[role=alert]').textContent=err.message;}};}
async function bookTaskDialog(cid,id){const t=await api(`/api/companies/${cid}/book-tasks/${id}`);const url=location.origin+`/api/companies/${cid}/book-tasks/${id}/instructions`;const brief=`请执行系统中的独立企业书任务：${url}\n用本机HTTP工具读取该接口，先完整读workflow，再按每次角色读取role_instructions的现行标准和任务模板。按完整问题分批研究、写作与独立审阅；保存实际派发指令及审阅覆盖，不能只依据接口摘要执行。随后分批写回正文，提交complete仅表示模型成稿。不要先读其他模型企业书；如实回填实际模型版本，保留来源、假设、计算与缺口。`;
 showDialog(t.title,`<p>${esc(modelName(t))} · ${esc(t.status)} · 已保存${Object.keys(t.parts).length}个部分</p><p>把下面指令交给能访问本机HTTP的外部Agent。它直接读写系统，无须下载或上传资料包。</p><textarea id="agent-connect-brief" class="book-agent-brief" rows="6" readonly>${esc(brief)}</textarea><p class="small muted">127.0.0.1指运行系统的这台电脑；纯云端聊天窗口不能直接访问本机服务。</p><a href="${url}" target="_blank">查看完整任务接口</a>${t.edition_id?` · <a href="${editionURL(cid,t.edition_id)}">打开本模型企业书</a>`:''}`,true);}
function bindModelBooks(){const s=$('#model-book-select');if(s)s.onchange=()=>{location.hash=s.value?editionURL(route.cid,s.value):`#/company/${route.cid}/book${company(route.cid).default_book_edition_id?'?draft=1':''}`;};const f=$('#version-search');if(f)f.onsubmit=async e=>{e.preventDefault();try{const d=await api(`/api/companies/${f.dataset.cid}/data/versions/${f.dataset.version}/search?q=`+encodeURIComponent(new FormData(f).get('q')));$('#version-search-results').innerHTML=d.results.map(x=>`<article><button class="text-btn" data-model-action="source" data-cid="${f.dataset.cid}" data-version="${f.dataset.version}" data-doc="${x.document_id}" data-page="${x.page}">${esc(x.title)} · 第${x.page}页</button><p>${esc(x.excerpt)}</p></article>`).join('')||'<p>本版本未检索到匹配原文。</p>';}catch(err){toast(err.message,true);}};}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-model-action]');if(!b)return;try{const d=b.dataset;if(d.modelAction==='task-new')await bookTaskForm(d.cid,d.version);if(d.modelAction==='task-open')await bookTaskDialog(d.cid,d.task);if(d.modelAction==='source')await modelSource(d.cid,d.version,d.doc,Number(d.page)||1);if(d.modelAction==='refresh')await refresh();}catch(err){toast(err.message,true);}});
