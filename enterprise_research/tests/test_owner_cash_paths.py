import sys
import unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from owner_cash_paths import calculate


class CashPathsTest(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(currency='CNY', amount_unit='yuan', share_unit='share',
            claim_scope='ordinary_common_equity_after_tax_interest_and_minority',
            shares=10, reference_price=100, rates=[0.1], comparison_rate=0.1, base_scenario='base',
            scenarios=[dict(name='base',basis='test',years=[dict(year=1,cash_before_transition=100,working_capital_use=0,other_cash_use=0)],terminal_cash=100,terminal_growth=0)])

    def test_flat_path_equals_perpetuity_and_reverse_price(self):
        result=calculate(self.inputs)
        self.assertAlmostEqual(result['scenarios'][0]['values']['0.1']['value_per_share'],100)
        self.assertAlmostEqual(result['required_terminal_cash_at_reference_price'],100)

    def test_transition_is_finite_and_first_cash_is_discounted(self):
        self.inputs['scenarios'][0]['years'][0]['working_capital_use']=20
        result=calculate(self.inputs)
        self.assertAlmostEqual(result['scenarios'][0]['values']['0.1']['total_value'],1000-20/1.1)
        self.assertAlmostEqual(result['required_terminal_cash_at_reference_price'],102)

    def test_release_removes_foregone_interest_and_preserves_input(self):
        self.inputs['asset_release_sensitivities']=[dict(amount=100,year=2,after_tax_yield_lost=0.02)]
        saved=deepcopy(self.inputs);r=calculate(self.inputs)
        self.assertAlmostEqual(r['asset_release_sensitivities'][0]['incremental_value'],80/1.1**2)
        self.assertEqual(self.inputs,saved)

    def test_decline_begins_after_explicit_path(self):
        self.inputs['scenarios'][0].update(terminal_cash=98,terminal_growth=-0.02)
        r=calculate(self.inputs)['scenarios'][0]['values']['0.1']['total_value']
        self.assertAlmostEqual(r,100/1.1+98/0.12/1.1)

    def test_missing_year_and_nonfinite_amount_rejected(self):
        self.inputs['scenarios'][0]['years'][0]['year']=2
        with self.assertRaises(ValueError):calculate(self.inputs)
        self.inputs['scenarios'][0]['years'][0]['year']=1
        self.inputs['scenarios'][0]['terminal_cash']=float('nan')
        with self.assertRaises(ValueError):calculate(self.inputs)
