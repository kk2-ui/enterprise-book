import unittest
from statistics import median
from unittest.mock import patch
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sector_history import compare, build_history
from market_context import peer_daily
from market_data import QuoteCache

class SectorHistoryTests(unittest.TestCase):
    def test_exited_and_suspended_members_are_unknown_not_stale_or_zero(self):
        m=[{'code':c,'name':c,'group':'basic'} for c in ['own','a','exit','late']]
        p={'own':{'2020-12-31':10,'2026-11-06':8},'a':{'2020-12-31':10,'2026-11-06':1},'exit':{'2020-12-31':10,'2021-06-30':7},'late':{'2021-06-30':10,'2026-11-06':12},'HSCI':{'2020-12-31':100,'2026-11-06':80}}
        r=compare(m,p,'2020-12-31','2026-11-06','own',['own','a','exit'])['groups']['basic']
        self.assertEqual((r['selected'],r['valid'],r['unknown']),(2,1,1))
        self.assertEqual(r['median_pct'],-90)
        self.assertEqual(r['below_market_min_pct'],50)
        self.assertEqual((r['own_rank'],r['rank_total']),(1,2))
        exited=next(x for x in r['records'] if x['code']=='exit')
        self.assertIsNone(exited['return_pct']);self.assertEqual(exited['last_date'],'2021-06-30')

    def test_fixed_cohort_does_not_drop_a_member_missing_the_alternative_start(self):
        m=[{'code':c,'name':c,'group':'basic'} for c in ['own','a']]
        p={'own':{'2020-12-31':10,'2026-11-06':8},'a':{'2026-11-06':1},'HSCI':{'2020-12-31':100,'2026-11-06':80}}
        r=compare(m,p,'2020-12-31','2026-11-06','own',['own','a'])['groups']['basic']
        self.assertEqual((r['selected'],r['valid'],r['unknown']),(1,0,1))

    def test_long_history_uses_interval_median_not_rebalanced_daily_returns(self):
        days=['2020-12-31','2021-01-04','2021-12-31','2026-11-06']
        def bars(v):return {'rows':[{'date':d,'close':p} for d,p in zip(days,v)]}
        series={'HSCI':bars([100]*4),'own':bars([10]*4),'a':bars([10,20,10,10]),'b':bars([10,5,10,10])}
        definition={'version':'test','baseline':days[0],'scope':'test','members':[{'code':c,'name':c,'group':'basic'} for c in ['own','a','b']]}
        r=build_history('own',series,definition)
        self.assertEqual(r['main']['groups']['basic']['median_pct'],0)
        self.assertEqual(r['main']['groups']['basic']['initial_equal_mean_pct'],0)

    def test_wide_daily_reference_has_coverage_gate_and_resists_one_outlier(self):
        p={str(i):{'a':10,'b':10.1} for i in range(10)};p['0']['b']=100;p['8']={};p['9']={}
        value,count=peer_daily(p,list(p),'a','b',median,.8)
        self.assertAlmostEqual(value,.01);self.assertEqual(count,8)
        p['7']={};self.assertIsNone(peer_daily(p,list(p),'a','b',median,.8)[0])
        self.assertIsNone(peer_daily({k:p[k] for k in ['1','2']},['1','2'],'a','b',median,.8)[0])

    def test_source_failure_does_not_reclassify_an_existing_member_as_later_ipo(self):
        bars={'rows':[{'date':'2020-12-31','close':10},{'date':'2026-11-06','close':8}]}
        members=[{'code':c,'name':c,'group':'basic','baseline_member':True} for c in ['own','missing']]
        definition={'version':'test','baseline':'2020-12-31','scope':'test','members':members}
        result=build_history('own',{'HSCI':bars,'own':bars},definition)
        self.assertEqual(result['later_listings'],[])
        self.assertEqual(result['main']['groups']['basic']['unknown'],1)

    def test_hk_fallback_requests_adjusted_bars_and_preserves_currency(self):
        raw={'data':{'hk01941':{'day':[['2026-11-06','1','1','1','1','0']]}}}
        adjusted={'data':{'code':'01941','name':'烨星','klines':['2026-11-06,.5,.52,.52,.5,0,0']}}
        with tempfile.TemporaryDirectory() as path,patch('market_data.get_json',side_effect=[raw,adjusted]) as fetch:
            result,error=QuoteCache(path).fetch({'code':'01941.HK'},'2026-11-06')
        self.assertIsNone(error);self.assertEqual(result['currency'],'HKD')
        self.assertEqual(result['rows'][0]['close'],.52)
        self.assertIn('fqt=1',fetch.call_args.args[0]);self.assertEqual(result['source'],'东方财富前复权日线')

if __name__=='__main__':unittest.main()
