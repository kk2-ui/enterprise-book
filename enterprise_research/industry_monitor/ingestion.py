"""Map source observations without inventing disclosure dates or currencies."""
import ast
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .repository import Repository
from .calculation import PROPERTY_PROFILE

ROOT=Path(__file__).resolve().parents[1]
POLY='735523351a5a4486'
CURRENCIES={'人民币':'CNY','人民幣':'CNY','港元':'HKD','港币':'HKD','港幣':'HKD','美元':'USD',
            'CNY':'CNY','RMB':'CNY','HKD':'HKD','USD':'USD'}
INCOME={'营业额':'revenue','毛利':'gross_profit','经营溢利':'operating_profit','股东应占溢利':'parent_profit',
        '除税后溢利':'net_profit','少数股东损益':'minority_profit','每股基本盈利':'basic_eps',
        '融资成本':'finance_cost','税项':'income_tax','利息收入':'interest_income','减值及拨备':'impairment',
        '行政开支':'administration','销售及分销费用':'selling_expense','其他收入':'other_income','其他收益':'other_gains'}
BALANCE={'股东权益':'parent_equity','总权益':'total_equity','少数股东权益':'minority_equity',
         '总资产':'total_assets','总负债':'total_liabilities','现金及等价物':'cash',
         '受限制存款及现金':'restricted_cash','应收帐款':'trade_receivables','预付款按金及其他应收款':'other_receivables',
         '应收关联方款项':'related_receivables','商誉':'goodwill','无形资产':'intangibles',
         '合同资产':'contract_assets','合同负债':'contract_liabilities','物业厂房及设备':'ppe',
         '短期贷款':'short_borrowings','长期贷款':'long_borrowings','融资租赁负债(流动)':'lease_current',
         '融资租赁负债(非流动)':'lease_noncurrent','应付帐款':'trade_payables','短期存款':'short_deposits',
         '中长期存款':'long_deposits','应付关联方款项(流动)':'related_payables','流动负债合计':'current_liabilities',
         '流动资产合计':'current_assets','递延税项资产':'deferred_tax_assets','投资物业':'investment_property'}
CASH={'经营业务现金净额':'operating_cash_flow','购建固定资产':'fixed_capex','购建无形资产及其他资产':'intangible_capex',
      '已付股息(融资)':'dividends_paid','偿还融资租赁':'lease_payments','加:折旧及摊销':'depreciation_amortization',
      '加:减值及拨备':'impairment_cf','已收利息(投资)':'interest_received','已付利息(融资)':'interest_paid_financing',
      '已付利息(经营)':'interest_paid_operating','收购附属公司':'acquisitions','偿还借款':'debt_repaid',
      '新增借款':'new_debt','回购股份':'buybacks','应收帐款减少':'receivables_cash_change',
      '预付款项、按金及其他应收款项减少(增加)':'other_receivables_cash_change',
      '应付帐款及应计费用增加(减少)':'payables_cash_change','已付税项':'tax_paid',
      '营运资金变动前经营溢利':'cash_before_working_capital'}
MAPS={'income':INCOME,'balance':BALANCE,'cashflow':CASH}
PARENT={'parent_profit','parent_equity','basic_eps'}


def subject_id(code):return POLY if code=='06049.HK' else 'issuer-'+code.replace('.','-')


def register_universe(repo):
    u=json.loads((ROOT/'property_universe.json').read_text())
    for m in u['members']:
        sid=subject_id(m['code'])
        repo.register(sid,'issuer',m['name'],POLY if sid==POLY else None,**{k:v for k,v in m.items() if k!='name'})
        repo.security(m['code'],sid,'HKD',listing_status=m['status'],status_source=m.get('status_source'),
                      membership=m.get('membership',{}))
    repo.register('property-basic','sector','基础物业研究样本',scope=u['scope'])
    for index,name in [('HSCI','恒生综合'),('HSSI','恒生综合小型股'),('HSLI','恒生综合大型股')]:
        repo.register(index,'index',name)
    repo.freeze('monitor_universes','property',u['version'],u)
    repo.freeze('monitor_profiles',PROPERTY_PROFILE['id'],PROPERTY_PROFILE['version'],PROPERTY_PROFILE)
    return u


def import_eastmoney(repo, directory, members,documents=None):
    directory=Path(directory);summary=[];pending=[]
    for member in members:
        code=member['code'];sid=subject_id(code);currencies={};starts={};count=0;errors=[]
        pf=directory/(code+'-periods.json')
        if pf.exists():
            p=json.loads(pf.read_text())
            for row in p['rows']:
                end=row['REPORT_DATE'][:10]
                currencies[end]=CURRENCIES.get(row.get('CURRENCY'))
                starts[end]=(row.get('START_DATE') or '')[:10]
        for kind,mapping in MAPS.items():
            path=directory/(code+'-'+kind+'.json')
            if not path.exists():errors.append(kind+'数据未取得');continue
            raw=json.loads(path.read_text())
            for i,row in enumerate(raw['rows']):
                end=row['REPORT_DATE'][:10]
                if end<'2019-01-01':continue
                name=row.get('ITEM_NAME',row.get('STD_ITEM_NAME'))
                if row.get('AMOUNT') is None:continue
                currency=CURRENCIES.get(row.get('CURRENCY_CODE')) or CURRENCIES.get(row.get('CURRENCY')) or currencies.get(end)
                if not currency:errors.append(end+'币种未核定');continue
                metric=mapping.get(name,'reported:'+kind+':'+row['STD_ITEM_CODE'])
                fact=dict(subject_id=sid,metric=metric,label=name,period_end=end,
                          period_start='' if kind=='balance' else (row.get('START_DATE') or starts.get(end) or '')[:10],
                          scope='parent' if metric in PARENT else 'consolidated',currency=currency,
                          unit='currency_per_share' if metric=='basic_eps' else 'currency',value=row['AMOUNT'],
                          available_on=raw['retrieved_at'][:10],vintage='unknown',priority=20,
                          source_key=f'eastmoney:{code}:{kind}:{end}:{row["STD_ITEM_CODE"]}',
                          source=dict(provider='东方财富',url=raw['urls'][0],path=str(path.resolve()),row=i,
                                      field='AMOUNT',original_currency=row.get('CURRENCY'),retrieved_at=raw['retrieved_at']),
                          limitations=['供应商当前历史值；取得日不等于首次公告日，尚不能用于严格历史时点计算'])
                doc=(documents or {}).get(path.name)
                if doc:fact['source'].update(document_id=doc['id'],document_revision=doc['revision'],source_id=doc['representations']['original'])
                pending.append(fact);count+=1
        indicator=directory/(code+'-indicators.json')
        if indicator.exists():
            raw=json.loads(indicator.read_text())
            for row in raw['rows']:
                # The endpoint repeats current share counts in historical rows.
                # Store as retrieval-time candidates, never historical shares.
                if row.get('ISSUED_COMMON_SHARES') is not None:
                    repo.observe(sid,'share_candidate',raw['retrieved_at'][:10],f'eastmoney-current-shares:{code}',
                                 dict(value=row['ISSUED_COMMON_SHARES'],h_shares=row.get('HK_COMMON_SHARES'),
                                      kind='total_common_shares',source_url=raw['urls'][0],
                                      status='needs_monthly_return_verification',warning='供应商当前股数，不按报告期回填历史'))
                    break
        summary.append(dict(code=code,facts=count,errors=sorted(set(errors))))
    with repo.connect() as conn:
        for fact in pending:repo.add_fact(fact,conn)
    return summary


CSMAR_METRICS={
    'n_income_attr_p':'parent_profit','n_cashflow_act':'operating_cash_flow',
    'total_hldr_eqy_exc_min_int':'parent_equity','minority_int':'minority_equity',
    'total_liab':'total_liabilities','money_cap':'cash','accounts_receiv':'trade_receivables',
    'other_receiv':'other_receivables','fix_assets':'ppe','intang_assets':'intangibles',
    'st_borr':'short_borrowings','lt_borr':'long_borrowings','acct_payable':'trade_payables',
    'c_pay_acq_const_fiolta':'capital_expenditure','base_share':'total_common_shares',
    'd_a':'depreciation_amortization','dps':'dividend_per_share','eps':'basic_eps',
    'minority_profit':'minority_profit','operate_profit':'operating_profit',
}


def import_csmar(repo, database, mapping_script, members):
    """Read raw tables, not the mutable merged/normalised annual table."""
    tree=ast.parse(Path(mapping_script).read_text())
    maps={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('INCOME_FIELDS','BS_FIELDS','CF_FIELDS','DISC_FIELDS'):
            maps[node.targets[0].id]=ast.literal_eval(node.value)
    specs=[('source_csmar_hk_income_non_financial','INCOME_FIELDS','income'),
           ('source_csmar_hk_balance_non_financial','BS_FIELDS','balance'),
           ('source_csmar_hk_cashflow','CF_FIELDS','cashflow'),('source_csmar_hk_disclosure','DISC_FIELDS','disclosure')]
    codes=[m['code'].split('.')[0] for m in members];lookup=set(codes)
    c=sqlite3.connect('file:'+str(Path(database).resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    summary={code:0 for code in codes};pending=[]
    try:
        for table,mapping,kind in specs:
            for row in c.execute(f'SELECT rowid,* FROM {table} WHERE EndDate>=?',('2019-01-01',)):
                code=str(row['Symbol']).zfill(5)
                if code not in lookup:continue
                if 'StateTypeCode' in row.keys() and row['StateTypeCode']!='A':continue
                if str(row['CoverPeriod']) not in ('6','12'):continue
                currency=CURRENCIES.get(row['Currency'])
                if not currency:continue
                end=row['EndDate'][:10]
                for column,target in maps[mapping].items():
                    if column not in row.keys() or row[column] in (None,'','--'):continue
                    try:value=float(row[column])
                    except (TypeError,ValueError):continue
                    metric=CSMAR_METRICS.get(target,target)
                    start=row['StartDate'][:10] if 'StartDate' in row.keys() and row['StartDate'] else ''
                    pending.append(dict(subject_id=subject_id(code+'.HK'),metric=metric,label=column,
                        period_start=start,period_end=end,scope='parent' if metric in PARENT else 'consolidated',
                        currency='SHARES' if metric=='total_common_shares' else currency,
                        unit='shares' if metric=='total_common_shares' else 'currency_per_share' if target in ('eps','eps_diluted','dps') else 'percent' if target.endswith('_pct') else 'currency',
                        value=value,available_on=None,vintage='unknown',priority=10,
                        source_key=f'csmar:{table}:{row["rowid"]}:{column}',
                        source=dict(provider='CSMAR已有原始数据',database=str(Path(database).resolve()),table=table,rowid=row['rowid'],field=column,source_flag=row['Source']),
                        limitations=['原始库缺少公开日及修订时点，须核对原件后才用于历史估值']))
                    summary[code]+=1
    finally:c.close()
    with repo.connect() as conn:
        for fact in pending:repo.add_fact(fact,conn)
    return summary
