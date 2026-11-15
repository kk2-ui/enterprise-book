import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from industry_monitor.repository import Repository
from industry_monitor.calculation import aggregate,asset_bridge,metric,percentile,ttm,valuation
from industry_monitor.capital import monthly_shares
from industry_monitor.returns import total_return,cash_events
from industry_monitor.snapshot import checked_market
from industry_monitor.service import MonitorService


def fact(fid,start,end,value,available,currency='CNY',metric_name='parent_profit',vintage='original'):
    return dict(id=fid,subject_id='x',metric=metric_name,period_start=start,period_end=end,value=value,
                available_on=available,currency=currency,unit='currency',scope='parent',source_key=fid,vintage=vintage)


class MonitorTests(unittest.TestCase):
    def test_failed_capital_document_cannot_clear_its_own_gap(self):
        from industry_monitor.snapshot import reported
        member=dict(code='02869.HK',name='绿城',group='basic',status='active')
        shares=dict(as_of='2020-10-31',available_on='2020-11-06',document_id='hkex-9502157',value=100,kind='total_common_shares')
        inputs=dict(facts=[],shares=[shares],series=dict(id='raw',rows=[dict(date='2020-11-06',close=10)]),
                    capital_gaps=[dict(document_id='9502157',available_on='2020-11-06')])
        row=reported(None,member,'2020-11-06','2020-11-06',[],inputs=inputs)
        self.assertIsNone(row['shares_date']);self.assertIsNone(row['market_cap'])
        self.assertTrue(any('9502157' in x for x in row['issues']))
        inputs['shares'].append(dict(shares,as_of='2020-11-30',available_on='2020-12-02',document_id='hkex-next'))
        inputs['series']['rows'].append(dict(date='2020-12-02',close=10))
        row=reported(None,member,'2020-12-02','2020-12-02',[],inputs=inputs)
        self.assertEqual(row['shares_date'],'2020-11-30')

    def test_new_adoption_must_cover_changed_financials_and_events(self):
        from industry_monitor.service import research_covers_change,catchup_records
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repository(tmp);sig={'parent_profit':100}
            old=repo.observe('x','research_basis','2026-11-01','old',dict(financial_signature=sig,event_ids=['a']))
            row=dict(subject_id='x',research=dict(adoption=dict(id=old)))
            self.assertFalse(research_covers_change(repo,row,sig,[],'2026-11-09'))
            repo.observe('x','research_basis','2026-11-09','new',dict(financial_signature=sig,event_ids=['a','b']))
            self.assertTrue(research_covers_change(repo,row,sig,[dict(document_id='b')],'2026-11-09'))
            self.assertFalse(research_covers_change(repo,row,{'parent_profit':99},[],'2026-11-09'))
            self.assertFalse(research_covers_change(repo,row,sig,[dict(document_id='c')],'2026-11-09'))
            self.assertFalse(research_covers_change(repo,row,sig,[],'2026-11-08'))
        records=[dict(kind='interim_report',published_on=d) for d in ['2024-09-01','2026-09-01','2025-09-01']]
        self.assertEqual([r['published_on'] for r in catchup_records(dict(records=records),'interim_report','2025-01-01')],['2026-09-01','2025-09-01'])

    def test_curated_original_requires_review_and_preserves_publication(self):
        import json
        from unittest.mock import patch
        from industry_monitor.reviewed_statements import ingest
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repository(tmp);path=Path(tmp)/'reviewed_statements.json'
            item=dict(status='pending_review',record=dict(code='06049.HK',id='r',url='https://example.org/r',published_on='2021-03-30',published_at='2021-03-30T18:00:00+08:00'),rows=[dict(metric='parent_profit',period_start='2020-01-01',period_end='2020-12-31',scope='parent',currency='CNY',value=439020000,vintage='original',pdf_page=92,excerpt='归母利润439020千元',scope_evidence='EPS归母核对')])
            path.write_text(json.dumps([item]));self.assertEqual(ingest(repo,tmp)['facts'],0)
            item.update(status='reviewed',review_reference='review.md');path.write_text(json.dumps([item]))
            with patch('industry_monitor.reviewed_statements.register_report',return_value=dict(id='r',revision=1,representations={'original':'source'})):
                self.assertEqual(ingest(repo,tmp)['facts'],1)
            f=repo.facts('735523351a5a4486')[0]
            self.assertEqual(f['value'],439020000);self.assertEqual(f['available_on'],'2021-03-31')
            self.assertIsNone(ttm([f],'parent_profit','2021-03-30',True)['value'])

    def test_original_wrapped_statements_and_unlabelled_parent_subtotal(self):
        from industry_monitor.statements import extract
        text='''綜合損益及
其他全面收益表 24
人民幣千元 人民幣千元
收入 400 300
以下人士應佔：
本公司權益股東 Equity shareholders of the
 Company 32 23
非控股權益 4 5
\f綜合財務狀况表
人民幣千元 人民幣千元
本公司擁有人應佔（權益虧絀）╱權益
股本 5 5
儲備 (62) 601

 (57) 606
非控股權益 23 20
（權益虧絀總額）╱權益總額 (34) 626
\f綜合現金流量表
人民幣千元
人民幣千元
經營活動
經營所得現金 25 30
\f附註 2025年 2024年
人民幣千元 人民幣千元
已付所得稅 (5) (4)
經營活動（所用）
╱所得現金淨額 20 26
投資活動
購買物業、廠房及設備 (3) (2)
融資活動
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.txt';p.write_text(text)
            result=extract(dict(code='06049.HK',id='original',title='2025年報',kind='annual_report',text_path=str(p),published_on='2026-04-01',url='https://example.test/report.pdf'))
            rows={f['metric']:f for f in result['facts'] if f['period_end']=='2025-12-31'}
            self.assertEqual(rows['parent_profit']['value'],32000)
            self.assertEqual(rows['parent_equity']['value'],-57000)
            self.assertEqual(rows['operating_cash_flow']['value'],20000)
            self.assertEqual(rows['capital_expenditure']['value'],3000)
            self.assertEqual(rows['operating_cash_flow']['source']['pdf_page'],4)

    def test_unadopted_revision_does_not_replace_adjustment_evidence(self):
        from industry_monitor.economic import adopted_adjustments
        old=dict(key='credit',as_of='2026-11-09',range=[-10,0],research_reference=dict(project_id='study',research_revision=1))
        new=dict(old,range=[-90,0],research_reference=dict(project_id='study',research_revision=2))
        self.assertEqual(adopted_adjustments([old,new],dict(id='study',revision=1),'2026-11-09'),[old])
        self.assertEqual(adopted_adjustments([old,new],None,'2026-11-09'),[])

    def test_component_conflict_blocks_even_positive_total_capex(self):
        rows=[fact('fy','2025-01-01','2025-12-31',57.516,'2026-04-20',metric_name='capital_expenditure'),
              fact('prior','2025-01-01','2025-06-30',9.375,'2026-09-24',metric_name='capital_expenditure'),
              fact('now','2026-01-01','2026-06-30',34.354,'2026-09-24',metric_name='capital_expenditure')]
        rows[0]['source']={'document_id':'annual'}
        check=dict(annual_document_id='annual',metrics=['capital_expenditure'],status='unresolved',available_on='2026-09-24',reason='全年设备付款小于上半年，无重分类桥')
        rows[-1]['ttm_scope_checks']=[check]
        self.assertIsNone(ttm(rows,'capital_expenditure','2026-11-09')['value'])
        rows[-1]['ttm_scope_checks'].append(dict(check,status='confirmed',available_on='2026-11-10'))
        self.assertIsNone(ttm(rows,'capital_expenditure','2026-11-09')['value'])
        self.assertAlmostEqual(ttm(rows,'capital_expenditure','2026-11-10')['value'],82.495)

    def test_company_events_do_not_leak_or_turn_titles_into_facts(self):
        from industry_monitor.events import topics,selected,visible,newly_disclosed
        offer=dict(id='offer',title='潛在無條件強制性現金要約',category='收購守則',kind='other',
                   published_on='2026-10-30',published_at='2026-10-30T07:00:00+08:00')
        self.assertEqual(topics(offer),['control'])
        self.assertEqual(selected(dict(records=[offer]),'2026-10-29'),[])
        annual=dict(offer,kind='annual_report',title='年報內幕消息')
        self.assertEqual(topics(annual),[])
        row=dict(offer,document_id='offer',as_of=offer['published_on'],available_on=offer['published_on'])
        self.assertEqual(visible([row],'2026-10-29'),[])
        self.assertEqual(newly_disclosed([], [row],'2026-10-30','2026-10-30'),[row])
        self.assertEqual(newly_disclosed([row],[row],'2026-10-30','2026-11-09'),[])
        self.assertEqual(newly_disclosed([row],[row],'2026-10-30','2027-11-09'),[])

    def test_cash_unknown_and_equivalence_do_not_become_owner_cash(self):
        from owner_cash_bridge import calculate
        data=dict(currency='CNY',amount_unit='yuan',basis_type='normal_condition',claim_scope='ordinary_common_equity',basis='原件与研究',starting_cash=100,
                  adjustments=[dict(name='下层权益',value=None,basis='利润不是现金归属')])
        r=calculate(data)
        self.assertIsNone(r['owner_cash']);self.assertEqual(r['known_cash'],100)
        data.update(basis_type='capitalization_equivalent',adjustments=[dict(name='固定资本扣减的年流等价',value=-3.5,basis='35资本额×10%')])
        r=calculate(data)
        self.assertIsNone(r['owner_cash']);self.assertEqual(r['equivalent_cash'],96.5)

    def test_nextday_treasury_and_partial_h_share(self):
        from industry_monitor.capital import nextday_shares
        record=dict(id='x',url='https://example.org',published_on='2026-11-06',published_at='2026-11-06T18:00:00+08:00')
        text='FF305\n第一章節\n股份分類 普通股 股份類別 H股\n於下列日期開始時的結存(註1) 2026年11月5日 300,000,000 10,000,000 310,000,000\n於下列日期結束時的結存(註5) 2026年11月6日 299,000,000 11,000,000 310,000,000'
        with self.assertRaises(ValueError):nextday_shares(text,record)
        prior=dict(id='prior',classes=[dict(outstanding=300000000),dict(outstanding=200000000)])
        r=nextday_shares(text,record,prior)
        self.assertEqual(r['value'],499000000);self.assertEqual(r['available_on'],'2026-11-07')

    def test_official_index_valuation_date_is_not_quote_date(self):
        from industry_monitor.indices import factsheet_values
        text='All data as at 30 Sep 2026\nPE Ratio Yield (%)\nHSCI 3,630.08 -3.75 +5.88 -2.45 -12.70 +35.35 -4.87 -7.10 2.88 15.15 19.04\nHSLI 2264.40 -3.67 7.71 -0.90 -11.11 38.97 -0.14 -5.96 2.82 14.43 19.45\nHSSI 1289.46 -3.02 -1.82 -19.09 -27.37 -0.37 -42.93 -17.89 3.07 38.13 21.56'
        rows=factsheet_values(text,'https://example.org','2026-11-09T10:00:00Z')
        self.assertEqual(rows[0]['as_of'],'2026-09-30');self.assertEqual(rows[0]['available_on'],'2026-11-09')
        self.assertEqual(rows[0]['pe'],15.15);self.assertIsNone(rows[0]['pb'])

    def test_ttm_publication_and_restatement(self):
        f=[fact('fy','2024-01-01','2024-12-31',100,'2025-03-20'),
           fact('prior','2024-01-01','2024-06-30',40,'2024-08-20'),
           fact('now','2025-01-01','2025-06-30',50,'2025-08-20')]
        self.assertEqual(ttm(f,'parent_profit','2025-08-19',True)['value'],100)
        self.assertEqual(ttm(f,'parent_profit','2025-08-21',True)['value'],110)
        revised=fact('revised','2024-01-01','2024-12-31',60,'2026-03-20',vintage='dated_restatement')
        self.assertEqual(ttm(f+[revised],'parent_profit','2025-08-21',True)['value'],110)
        self.assertEqual(ttm(f+[revised],'parent_profit','2026-03-21',True)['value'],70)

    def test_restatement_needs_comparable_annual_basis(self):
        f=[fact('fy','2024-01-01','2024-12-31',100,'2025-03-20'),
           fact('oldh','2024-01-01','2024-06-30',40,'2024-08-20'),
           dict(fact('newh','2024-01-01','2024-06-30',45,'2025-08-20',vintage='dated_restatement'),comparative_restated=True),
           fact('now','2025-01-01','2025-06-30',60,'2025-08-20')]
        f[0]['source']={'document_id':'annual-old'}
        self.assertEqual(ttm(f,'parent_profit','2025-09-01')['status'],'scope_unresolved')
        f[-1]['ttm_scope_checks']=[dict(annual_document_id='annual-old',status='confirmed',available_on='2025-08-20',reason='原件证明同一并表范围')]
        self.assertEqual(ttm(f,'parent_profit','2025-09-01')['value'],115)

    def test_provider_revision_not_pit(self):
        f=[fact('p','2024-01-01','2024-12-31',100,'2025-03-20',vintage='unknown')]
        self.assertIsNone(ttm(f,'parent_profit','2025-12-31',True)['value'])
        self.assertEqual(ttm(f,'parent_profit','2025-12-31',False)['value'],100)

    def test_incompatible_ttm_not_added(self):
        f=[fact('fy','2024-01-01','2024-12-31',100,'2025-03-20','HKD'),
           fact('prior','2024-01-01','2024-06-30',40,'2024-08-20'),
           fact('now','2025-01-01','2025-06-30',50,'2025-08-20')]
        self.assertEqual(ttm(f,'parent_profit','2025-09-01')['status'],'missing_bridge')

    def test_currency_and_price_rights(self):
        f=[fact('fy','2024-01-01','2024-12-31',100,'2025-03-20')]
        p=dict(as_of='2025-04-01',adjustment='NONE',currency='HKD',close=10)
        shares=dict(as_of='2025-03-31',kind='total_common_shares',value=100)
        r=valuation(f,p,shares,'2025-04-01',{'CNY/HKD':1.1})
        self.assertAlmostEqual(r['pe_ttm']['value'],1000/110)
        with self.assertRaises(ValueError):valuation(f,dict(p,adjustment='QFQ'),shares,'2025-04-01',{})
        with self.assertRaises(ValueError):valuation(f,p,dict(shares,kind='H_shares'),'2025-04-01',{})

    def test_losses_and_matched_aggregation(self):
        rows=[dict(code='a',market_cap=100,earnings=10,pe=metric(100,10)),
              dict(code='b',market_cap=100,earnings=-5,pe=metric(100,-5)),
              dict(code='c',market_cap=900,earnings=None,pe=metric(900,None))]
        r=aggregate(rows,'pe','earnings')
        self.assertEqual(r['overall']['value'],40)
        self.assertEqual(r['median'],10)
        self.assertEqual(r['nonpositive'],1)
        self.assertEqual(r['missing_codes'],['c'])

    def test_inflation_and_debt(self):
        a=[dict(book_value=100,factor=1.3,basis='同等功能建造成本证据')]
        self.assertAlmostEqual(100/asset_bridge(a),1/1.3)
        self.assertAlmostEqual(100/asset_bridge([dict(a[0],book_value=200)],100),.625)
        self.assertEqual(asset_bridge([dict(book_value=100,monetary=True)]),100)
        with self.assertRaises(ValueError):asset_bridge([dict(book_value=100,monetary=True,factor=1.3)])

    def test_history_coverage(self):
        self.assertIsNone(percentile(5,[10]*35)['value'])
        self.assertEqual(percentile(5,[10]*36)['value'],0)

    def test_append_only_and_failed_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Repository(tmp);f=fact('one','2024-01-01','2024-12-31',100,'2025-03-20')
            first=r.add_fact(f);self.assertEqual(first,r.add_fact(f))
            second=r.add_fact(dict(f,value=90));self.assertNotEqual(first,second)
            self.assertEqual(len(r.facts('x')),2)
            rid=r.publish('x','2025-03-20',dict(value=100))
            with self.assertRaises(ValueError):r.publish('x','2025-03-21',dict(value=None),status='failed')
            self.assertEqual(r.current('x')['run_id'],rid)
            r.freeze('monitor_profiles','p','v1',dict(metric='PE'))
            with self.assertRaises(ValueError):r.freeze('monitor_profiles','p','v1',dict(metric='PB'))

    def test_conflicted_revision_cannot_resurrect_old_value(self):
        a=fact('original','2024-01-01','2024-12-31',100,'2025-03-20')
        a['revision']=1
        b=dict(a,id='quarantined',revision=2,quality='conflict',available_on='2025-04-01')
        self.assertEqual(ttm([a,b],'parent_profit','2025-03-31')['value'],100)
        self.assertIsNone(ttm([a,b],'parent_profit','2025-04-02')['value'])

    def test_monthly_return_excludes_authorised_and_treasury(self):
        text='''截至月份: 2026年10月31日
I. 法定股本
本月底結存 38,000,000,000
II. 已發行股份及/或庫存股份變動
1. 股份分類 普通股
本月底結存 3,107,891,487 48,840,000 3,156,731,487
III. 股份詳情'''
        r=monthly_shares(text,dict(published_on='2026-11-04',published_at='2026-11-04T09:00:00+08:00',url='https://example.test/report.pdf',id='monthly'))
        self.assertEqual(r['value'],3107891487)
        self.assertEqual(r['available_on'],'2026-11-04')
        with self.assertRaises(ValueError):monthly_shares(text.split('II.')[0],{})

    def test_after_close_disclosure_and_unknown_time(self):
        from industry_monitor.disclosures import available_close_day
        self.assertEqual(available_close_day(dict(published_on='2026-11-06',published_at='2026-11-06T17:30:00+08:00')),'2026-11-07')
        self.assertEqual(available_close_day(dict(published_on='2026-11-06')),'2026-11-07')

    def test_legacy_h_and_domestic_share_columns(self):
        text='''截至月份（日／月／年）： 31/12/2020
II. 已發行股本變動
                普通股數目
             H股        內資股       優先股數目        其他類別股份數目
本月底結存   153,333,400 400,000,000   不適用           不適用
III. 已發行股本變動詳情'''
        r=monthly_shares(text,dict(published_on='2021-01-05',url='https://example.test',id='m'))
        self.assertEqual(r['value'],553333400)

    def test_three_column_statement_and_comprehensive_income(self):
        from industry_monitor.statements import extract
        text='''簡明綜合損益表
2026年 2025年
人民幣千元  人民幣千元
收入                 5   1,000   900
本公司股東                 100    90
以下各方應佔全面收益：
本公司股東                 150   120
\f中期簡要綜合資產負債表
於2026年6月30日 於2025年12月31日 於2025年1月1日
人民幣千元  人民幣千元  人民幣千元
權益總額                 1,000   900   800
非控股權益                 200   150   100
'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.txt';path.write_text(text)
            r=extract(dict(code='06049.HK',title='2026年中期報告',kind='interim_report',text_path=str(path),
                           published_on='2026-09-20',published_at='2026-09-20T19:00:00+08:00',id='report',url='https://example.test'))
        facts={(f['metric'],f['period_end']):f for f in r['facts']}
        self.assertEqual(facts['parent_profit','2026-06-30']['value'],100000)
        self.assertEqual(facts['parent_equity','2026-06-30']['value'],800000)
        self.assertEqual(facts['parent_equity','2025-12-31']['value'],750000)
        self.assertEqual(facts['parent_equity','2026-06-30']['available_on'],'2026-09-21')

    def test_dividend_and_split_return_and_missing_event(self):
        prices=dict(adjustment='NONE',source_url='https://example.test',rows=[
            dict(date='2025-01-02',close=10),dict(date='2025-01-03',close=9),dict(date='2025-01-06',close=4.5)])
        events=[dict(date='2025-01-03',cash_hkd=1)]
        r=total_return(prices,events,[dict(date='2025-01-06',kind='split',verified=True,new_shares_per_old=2)])
        self.assertEqual([x['close'] for x in r['rows']],[100,100,100])
        with self.assertRaises(ValueError):total_return(prices,events,unresolved=[dict(reason='未知分派')])
        with self.assertRaises(ValueError):total_return(prices,[dict(date='2025-01-04',cash_hkd=1)])

    def test_mismatched_return_bases_pause_driver_without_mutation(self):
        raw=dict(sources=[dict(adjustment='QFQ'),dict(adjustment='PRICE_INDEX')],
                 windows={'20':dict(status='ok',dominant='industry')})
        out=checked_market(raw)
        self.assertEqual(out['windows']['20']['status'],'insufficient')
        self.assertEqual(raw['windows']['20']['status'],'ok')

    def test_restart_retains_snapshot_and_exposes_interrupted_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Repository(tmp);rid=repo.publish('property','2025-01-02',dict(companies=[]))
            jid=repo.new_job('property');repo.update_job(jid,'running')
            service=MonitorService(tmp,start_scheduler=False)
            try:
                self.assertEqual(repo.job(jid)['status'],'interrupted')
                self.assertEqual(repo.current('property')['run_id'],rid)
            finally:service.close()

    def test_official_index_ingestion_keeps_original_and_readable_text(self):
        from industry_monitor.pipeline import ingest
        from source_data import SourceRepository
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'inputs';indices=root/'indices';indices.mkdir(parents=True)
            pdf=indices/'factsheet.pdf';pdf.write_bytes(b'%PDF-1.4 test original')
            txt=indices/'factsheet.txt';txt.write_text('HSCI PE 14.14 as at 30 October 2026')
            quote=dict(index='HSCI',as_of='2026-10-30',pe=14.14,available_on='2026-11-09',limitation='published day unknown')
            (indices/'official-valuations.json').write_text(json.dumps(dict(values=[quote],pdf_path=str(pdf),text_path=str(txt),source_url='https://example.test/factsheet.pdf')))
            repo=Repository(Path(tmp)/'data');ingest(repo,root,[],'2026-11-06')
            obs=repo.observations('HSCI','official_valuation')[0]
            library=SourceRepository(repo.directory);doc=library.document('HSCI',obs['document_id'])
            self.assertEqual(Path(library.source(doc['representations']['text'])['path']).read_text(),txt.read_text())
            self.assertEqual(obs['available_on'],'2026-11-09')
            self.assertEqual(obs['as_of'],'2026-10-30')


if __name__=='__main__':unittest.main()
