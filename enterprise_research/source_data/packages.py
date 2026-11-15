"""Portable, fixed-version source inputs; no company dossier or research import."""
import csv
import json
import shutil
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from .repository import identifier, now
from .disclosures import amount_matches, decimal_amount


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


INSTRUCTIONS = '''# 给独立研究模型的任务

先阅读README、资料目录、覆盖与缺口，再结合原件和全文独立研究。数据表只是已抽取的便利索引，不代表已覆盖所有重要事实。按需要阅读附注、续页、经营叙述及相关主体资料。每个重要事实引用资料ID、版本和PDF页码；网页材料引用资料ID及原文段落。

分别交付公司介绍和投资判断。介绍说明业务边界、赚钱方式、行业及竞争、经营变化、治理与资本配置，按本企业特点选择重点因素。判断研究资产再生产价值、正常盈利能力EPV和有资金支持的增长适用性；三者不相加或平均。正常化、维护、税、资金用途、资本成本和普通股归属须自行论证。可以合理估计，注明依据和未知；不得将资料缺失填为零。增长资料不足可暂缓，不强造目标价。

资料包不附本项目的企业书、估值参数、审阅结论或投资判断。公开材料中的管理层说法与媒体转述属于相应主体的陈述，不自动等于核实事实。第三方分析如有列入，单独标识，不能替代独立判断。共用抽取可能共用错误，须回看会改变结论的原件。

若需要额外材料，先提交补采清单：具体问题、所需资料及期间、可能出处、缺口怎样影响判断。新材料形成新资料包版本；在报告里说明本次实际使用的版本和额外来源，勿宣称仍是完全相同信息集的对照。

请返回：①完整研究报告；②事实及来源表；③独立假设表（数值/范围、理由、对结论的影响）；④可复算的估值输入与结果；⑤反方与改变判断的条件；⑥未解决资料缺口。记录模型及版本（可得时）、执行时间、资料包ID、所用方法和自行补充的来源。不得把研究结果当作交易指令。完成独立研究后再读取其他模型的报告进行对照。
'''


def build_package(repo, cid, spec, create_archive=True):
    pid = identifier(spec['id'])
    company={k:spec['company'][k] for k in ['id','name','code','currency'] if k in spec['company']}
    if company.get('id',cid)!=cid or not company.get('name'):
        raise ValueError('资料包企业身份不符')
    if spec.get('mode', 'independent') != 'independent':
        raise ValueError('本入口只创建独立资料包；对照审阅另引用研究输出')
    base = repo.directory / 'packages'
    base.mkdir(exist_ok=True)
    destination, archive = base/pid, base/(pid+'.zip')
    if destination.exists() or archive.exists():
        raise ValueError('资料包版本已存在，请另建版本')
    selected = spec.get('documents', [])
    if not selected:
        raise ValueError('请选择资料及明确版本')
    docs = []
    for ref in selected:
        if not ref.get('revision'):
            raise ValueError('资料包必须固定每份资料的版本')
        d = repo.document(cid, ref['id'], ref['revision'])
        if d['nature'] == 'research_output':
            raise ValueError('独立资料包不接收内部研究结论')
        if d.get('published_on') and d['published_on'] > spec['information_cutoff']:
            raise ValueError(d['id']+'公开日晚于信息截止日')
        if d['id'] in [x['id'] for x in docs]:
            raise ValueError('同一资料只能选择一个版本')
        docs.append(d)
    with tempfile.TemporaryDirectory(prefix='.build-', dir=base) as tmp:
        out = Path(tmp)
        (out/'data').mkdir()
        records, catalog = [], []
        for d in docs:
            folder = out/'documents'/d['id']; folder.mkdir(parents=True)
            original, text = (repo.source(d['representations'][k]) for k in ['original', 'text'])
            original_path = folder/('original'+Path(original['path']).suffix.lower())
            shutil.copyfile(original['path'], original_path)
            shutil.copyfile(text['path'], folder/'fulltext.txt')
            fulltext = (folder/'fulltext.txt').read_text()
            pages = fulltext.split('\f')
            page_count = len(pages)-(1 if pages and not pages[-1].strip() else 0)
            (folder/'read.md').write_text('# '+d['title']+'\n\n'+''.join(f'\n## {"PDF页" if original_path.suffix==".pdf" else "文本段"} {i+1}\n\n```text\n{p}\n```\n' for i,p in enumerate(pages) if p.strip()))
            item = {k:d.get(k, '') for k in ['id', 'revision', 'title', 'nature', 'issuer', 'fact_period', 'published_on', 'acquired_on', 'url', 'description', 'group', 'text_status', 'extraction_status', 'periods']}
            item.update(original=original_path.relative_to(out).as_posix(), text=(folder/'fulltext.txt').relative_to(out).as_posix(), reading=(folder/'read.md').relative_to(out).as_posix(), page_count=page_count,
                        source_ids=d['representations'], row_count=len(d['rows']))
            catalog.append(item)
            for row in d['rows']:
                page = row['pdf_page']
                if page < 1 or page > len(pages) or row['source_excerpt'] not in pages[page-1]:
                    raise ValueError(d['id']+'/'+row['id']+'抽取原行与本版本全文不符')
                for column, value in row['values'].items():
                    key = d['id']+'/'+row['id']+'/'+column
                    if any(r['id']==key for r in records):
                        raise ValueError('同一资料中的数据单元重复：'+key)
                    meaning=d.get('periods', {}).get(column)
                    period=column if meaning and meaning.get('kind')!='category' else d['fact_period']
                    matches=amount_matches(row['source_excerpt'],row);first=matches[0] if matches else None
                    records.append(dict(id=key, document_id=d['id'], document_revision=d['revision'], metric=row['id'],
                                        metric_label=row.get('label') or (row['source_excerpt'][:first.start()].strip() if first else row['id']),
                                        period=period, column=column, column_definition=meaning, value=value, column_index=list(row['values']).index(column),
                                        unit=row['unit'], scope=row['scope'], basis='disclosed', pdf_page=page,
                                        source_excerpt=row['source_excerpt'], source_file=item['original'], text_file=item['text'],
                                        number_format=row.get('number_format','decimal_2'),skip_amounts=row.get('skip_amounts',0)))
        derived = []
        by_id = {r['id']:r for r in records}
        for calculation in spec.get('derived', []):
            if calculation.get('operation') != 'subtract':
                raise ValueError('派生数据仅支持已声明的同口径减法')
            left, right = (by_id[k] for k in calculation['inputs'])
            if left['unit'] != right['unit'] or left['scope'] != right['scope'] or left['metric'] != right['metric']:
                raise ValueError('派生输入的指标、单位或归属不一致')
            lp,rp=left['column_definition'],right['column_definition']
            if not lp or not rp or lp.get('kind') not in {'cumulative_flow','annual_flow'} or rp.get('kind') not in {'cumulative_flow','annual_flow'} or lp.get('start')!=rp.get('start') or lp.get('end','')<=rp.get('end',''):
                raise ValueError('派生减法须为同一起点、正确先后次序的累计流量；不能把存量或不同年度混减')
            derived.append(dict(calculation, value=str(Decimal(left['value'])-Decimal(right['value'])), unit=left['unit'], scope=left['scope'], basis='derived'))
        write_json(out/'data/disclosed.json', records)
        write_json(out/'data/derived.json', derived)
        with (out/'data/disclosed.csv').open('w', newline='') as f:
            keys=['id','document_id','document_revision','metric','metric_label','period','column','value','unit','scope','pdf_page','source_file','source_excerpt']
            writer=csv.DictWriter(f,keys,extrasaction='ignore'); writer.writeheader(); writer.writerows(records)
        manifest = dict(format='enterprise-source-package/v1', id=pid, mode='independent', created_at=now(),
                        company=company, information_cutoff=spec['information_cutoff'], valuation_date=spec.get('valuation_date'),
                        documents=catalog, disclosed_cells=len(records), derived_cells=len(derived),
                        coverage=spec.get('coverage', []), gaps=spec.get('gaps', []),
                        comparison_policy='同一资料版本独立分析；新增来源须单列或另建资料包版本。')
        write_json(out/'manifest.json', manifest)
        write_json(out/'data/dictionary.json',dict(fields={'id':'资料ID/指标ID/原表列名；不是可相加的记录编号','period':'期间或该表所属报告期','column':'原表列；可以是期间、资产类别或增减项目，不一律是日期','column_definition':'期间起止或类别解释','value':'原单位十进制字符串；没有将缺失填零','basis':'disclosed为原披露，derived为显式算术，不含研究假设','share_capital':'股本为会计金额，单位人民币元；不直接冒充实际在外股数','scope':'合并/相应主体范围；归母、少数等由指标原名称识别','source_excerpt':'可在本份全文的PDF页逐字定位的原行'},metrics={r['metric']:r['metric_label'] for r in records}))
        write_json(out/'coverage.json', dict(coverage=manifest['coverage'], gaps=manifest['gaps']))
        write_json(out/'task.json', dict(package_id=pid,company=company,information_cutoff=spec['information_cutoff'],valuation_date=spec.get('valuation_date'),deliverables=['report','facts','assumptions','calculations','counterarguments','data_requests'],pricing=spec.get('pricing',{'status':'not_supplied'})))
        (out/'独立分析任务.md').write_text(INSTRUCTIONS)
        write_json(out/'补采请求模板.json',dict(package_id=pid,requests=[dict(question='',needed_source='',period='',possible_url='',impact='',status='open')]))
        lines=['# 资料目录\n\n按需打开全文和原件。PDF页码从1开始；全文保留分页符。\n']
        for d in catalog:
            lines.append(f"- **{d['id']} r{d['revision']} · {d['title']}**：{d['issuer']}；{d['fact_period']}；公开日{d['published_on'] or '未知'}；性质`{d['nature']}`。\n  [原件]({d['original']}) · [分页阅读]({d['reading']}) · [全文]({d['text']})\n  {d['description']}\n")
        (out/'资料目录.md').write_text('\n'.join(lines))
        coverage=['# 覆盖与缺口\n\n这是一组有范围的资料，不代表穷尽公开信息。尚未结构化的内容仍可在原件全文中研究。\n']
        coverage += ['- '+x for x in manifest['coverage']]
        coverage += ['\n## 待补或不确定\n']+['- '+x for x in manifest['gaps']]
        (out/'覆盖与缺口.md').write_text('\n'.join(coverage)+'\n')
        (out/'README.md').write_text(f'''# {spec['company']['name']}独立分析资料包

资料包 `{pid}`；信息截止日 {spec['information_cutoff']}；估值比较日期 {spec.get('valuation_date') or '由研究者明确'}。

先读[独立分析任务](独立分析任务.md)和[覆盖与缺口](覆盖与缺口.md)，再按[资料目录](资料目录.md)阅读原件、全文及附注。`manifest.json`固定每份资料的版本、出处、期间与文件位置。

本包包含{len(docs)}份资料、{len(records)}个披露数据单元、{len(derived)}个明确公式的派生数据单元。`data/disclosed.json`和CSV保留原行及PDF页码；值以各行单位为准。`data/derived.json`只列明算术及输入，不把经营假设混为披露。公开日期未知的历史资料不能用于严格的事前信息回测。

原件在`documents/`内；全文TXT保留原分页符，`read.md`提供分页标识。解析文本可能存在OCR或排版误差，重要数字回看原PDF。媒体报道中的引语、公司解释和第三方判断按原主体归属。

本包不含本项目的企业书正文、估值结论、假设参数和审阅意见；研究者应独立形成报告。文件均使用包内相对路径，解压后不依赖原工作区或本地网站。无需一次把全部文件塞入上下文，可先读完整目录，再分题取用；至少完整阅读最近两份年报及最新中报、季报的相关正文和附注。

提交结果时标注资料包ID、模型及版本、研究日期、补充资料；补采可使用`补采请求模板.json`。本包及公开原文用于研究，保留原作者与发布主体。
''')
        validate_package(out)
        shutil.move(str(out), destination)
    if create_archive:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(destination.rglob('*')):
                if p.is_file():
                    z.write(p, pid+'/'+p.relative_to(destination).as_posix())
    summary=dict(id=pid,company_id=cid,title=spec.get('title',spec['company']['name']+'独立分析资料包'),
                 information_cutoff=manifest['information_cutoff'],created_at=manifest['created_at'],
                 document_count=len(docs),disclosed_cells=len(records),derived_cells=len(derived),
                 mode='independent',path=str(destination),zip_path=str(archive) if create_archive else None,
                 documents=[dict(id=d['id'],revision=d['revision']) for d in docs],gaps=manifest['gaps'])
    return repo.save_package(cid,summary)


def validate_package(directory):
    """Checks portability, actual original-row matches, and resolvable derivations."""
    root=Path(directory)
    manifest=json.loads((root/'manifest.json').read_text())
    for d in manifest['documents']:
        if d['nature']=='research_output':
            raise ValueError('包中含内部研究输出')
        for key in ['original','text','reading']:
            p=Path(d[key])
            if p.is_absolute() or '..' in p.parts or not (root/p).is_file():
                raise ValueError('包内资料不可移交：'+str(p))
    facts=json.loads((root/'data/disclosed.json').read_text())
    seen={r['id']:r for r in facts}
    texts={d['id']:(root/d['text']).read_text().split('\f') for d in manifest['documents']}
    for r in facts:
        if r['source_excerpt'] not in texts[r['document_id']][r['pdf_page']-1]:
            raise ValueError('原行无法定位：'+r['id'])
        original=amount_matches(r['source_excerpt'],r)[r['column_index']].group()
        if decimal_amount(original)!=Decimal(r['value']):
            raise ValueError('披露值与原行不符：'+r['id'])
    for r in json.loads((root/'data/derived.json').read_text()):
        a,b=(seen[k] for k in r['inputs'])
        if Decimal(r['value'])!=Decimal(a['value'])-Decimal(b['value']):
            raise ValueError('派生值不符')
    return dict(status='passed',documents=len(manifest['documents']),disclosed_cells=len(facts))
