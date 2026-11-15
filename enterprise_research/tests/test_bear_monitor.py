import math, random, sys, unittest
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bear_monitor import regime, volume_state, attribution, peer_portfolio

def calendar(n):
 return [(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(n)]

class BearMonitorTests(unittest.TestCase):
 def test_long_drawdown_survives_a_recent_rally(self):
  dates=calendar(600)
  prices=[100-i*.15 for i in range(450)]+[32.5+i*.10 for i in range(150)]
  rows=[{'date':d,'close':p,'volume':100} for d,p in zip(dates,prices)]
  r=regime(rows,dates)
  self.assertTrue(r['deep_drawdown'])
  self.assertGreater(r['returns']['60'],0)
  self.assertGreater(r['ma200_gap_pct'],0)
  self.assertFalse(r['full_five_years'])
  self.assertNotEqual(r['state'],'上行')
 def test_no_lookahead_and_single_stock_selloff(self):
  rng=random.Random(41);dates=calendar(600);samples=[]
  for d in dates:
   m,s,j=[rng.gauss(0,.01) for _ in range(3)]
   samples.append({'date':d,'market':m,'size':s,'industry':j,'stock':.7*m+.3*s+.9*j+rng.gauss(0,.002)})
  before=attribution(samples,['market','size','industry'],20,dates)
  for row in samples[-20:]:row['stock']-=.04
  after=attribution(samples,['market','size','industry'],20,dates)
  self.assertEqual(before['r2'],after['r2'])
  self.assertEqual(after['driver'],'specific')
  self.assertTrue(after['specific_alert'])
  self.assertLess(after['training_end'],after['observation_start'])
  self.assertAlmostEqual(sum(after['contributions_log_pp'].values()),after['observed_log_pp'],delta=.04)
 def test_widespread_market_selloff_is_not_stock_specific(self):
  rng=random.Random(12);dates=calendar(600);rows=[]
  for i,d in enumerate(dates):
   m,s,j=[rng.gauss(0,.01) for _ in range(3)]
   if i>=580:m-=.035
   rows.append({'date':d,'market':m,'size':s,'industry':j,'stock':m+.3*s+.4*j+rng.gauss(0,.001)})
  result=attribution(rows,['market','size','industry'],20,dates)
  self.assertEqual(result['driver'],'market')
  self.assertFalse(result['specific_alert'])
 def test_missing_history_and_collinearity_remain_unknown(self):
  self.assertEqual(attribution([],['market'],20,calendar(20))['status'],'unavailable')
  rng=random.Random(3);dates=calendar(300)
  rows=[{'date':d,'market':(x:=rng.gauss(0,.02)),'industry':x,'stock':x*.7} for d in dates]
  self.assertEqual(attribution(rows,['market','industry'],20,dates)['status'],'unavailable')
 def test_sector_selloff_is_not_market_selloff(self):
  rng=random.Random(14);dates=calendar(600);rows=[]
  for i,d in enumerate(dates):
   m,s,j=[rng.gauss(0,.01) for _ in range(3)]
   if i>=580:j-=.03
   rows.append({'date':d,'market':m,'size':s,'industry':j,'stock':.8*m+.3*s+j+rng.gauss(0,.001)})
  result=attribution(rows,['market','size','industry'],20,dates)
  self.assertEqual(result['driver'],'industry')
  self.assertFalse(result['specific_alert'])
 def test_volume_is_activity_and_missing_is_not_zero(self):
  dates=calendar(100)
  rows=[{'date':d,'close':200-i,'volume':300 if i>=80 else 100} for i,d in enumerate(dates)]
  r=volume_state(rows,dates)
  self.assertEqual(r['label'],'下跌 · 放量')
  self.assertEqual(r['signed_volume_balance'],-1)
  rows[-1]['volume']=None
  self.assertEqual(volume_state(rows,dates)['status'],'unavailable')
 def test_persistent_weakness_cannot_disappear_into_intercept(self):
  rng=random.Random(42);dates=calendar(600);rows=[]
  for i,d in enumerate(dates):
   m,s,j=[rng.gauss(0,.01) for _ in range(3)] if i<580 else [0,0,0]
   rows.append({'date':d,'market':m,'size':s,'industry':j,'stock':-.002+m+.3*s+.4*j+rng.gauss(0,.0001)})
  result=attribution(rows,['market','size','industry'],20,dates)
  self.assertEqual(result['driver'],'unknown')
  self.assertIn('历史平均弱势',' '.join(result['warnings']))
 def test_peer_history_never_bridges_a_missing_bar(self):
  dates=calendar(8)
  a=[{'date':d,'close':100+i} for i,d in enumerate(dates)]
  b=[r for i,r in enumerate(a) if i!=3]
  rows=peer_portfolio({'a':{'rows':a},'b':{'rows':b}},['a','b'],dates)
  self.assertEqual(rows[0]['date'],dates[4])
  self.assertEqual(len(rows),4)
 def test_small_negative_deviation_is_not_multiple_downside_pressures(self):
  rng=random.Random(51);dates=calendar(600);rows=[]
  for i,d in enumerate(dates):
   if i<580:
    m,s,j=[rng.gauss(0,.015) for _ in range(3)]
    stock=m+.3*s+.4*j+rng.gauss(0,.008)
   else:
    m,s,j=.002,.002,.002
    stock=m+.3*s+.4*j-.0015
   rows.append({'date':d,'market':m,'size':s,'industry':j,'stock':stock})
  result=attribution(rows,['market','size','industry'],20,dates)
  self.assertLess(result['contributions_log_pp']['specific'],0)
  self.assertGreater(result['specific_z'],-2)
  self.assertEqual(result['driver'],'unknown')
  self.assertFalse(result['specific_alert'])

if __name__=='__main__':unittest.main()
