"""Rebuild observed cash and the explicit ordinary-equity cases for PetroChina."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARES_YI = 183_020_977_818 / 100_000_000


def read_json(name):
    return json.loads((HERE / name).read_text())


def irr(cashflows):
    lo, hi = -.8, 1.
    for _ in range(75):
        rate = (hi+lo)/2
        if sum(amount/(1+rate)**year for year, amount in enumerate(cashflows)) > 0:
            lo = rate
        else:
            hi = rate
    return (hi+lo)/2


def calculate():
    market = read_json("market.json")
    holdings = market["h_hkd"]*market["hkd_cny"]
    facts = {(r["document"], r["id"]): r["values"] for r in read_json("disclosures.json")["rows"]}

    def get(doc, key, period):
        # Source financial tables are RMB millions. The book uses RMB 100m.
        return float(facts[doc, key][str(period)])/100

    observed = {}
    for label, doc, period in [
        ("2023", "annual2024", 2023), ("2024", "annual2025", 2024), ("2025", "annual2025", 2025),
        ("2025Q3-recast", "q32026", 2025), ("2026Q3", "q32026", 2026)
    ]:
        ids = ["ocf", "capex", "lease_paid", "interest_paid", "div_received", "nci_div", "owner_div"]
        values = {key: get(doc, key, period) for key in ids}
        wc = sum(get(doc, key, period) for key in ["wc_receivables","wc_inventory","wc_payables","wc_contract"])
        scope = sum(values[key] for key in ids if key!="owner_div")
        special = get(doc, "storage_paid", period) if label=="2026Q3" else None
        observed[label] = values | {
            "wc_contribution": wc, "ocf_ex_wc": values["ocf"]-wc, "after_paid_capex": values["ocf"]+values["capex"],
            "before_listed_payout": scope, "after_listed_payout": scope+values["owner_div"],
            "storage_paid": special, "after_listed_payout_and_storage":
            scope+values["owner_div"]+special if special is not None else None
        }

    # All three operating shocks are defined in cash-scenario terms. The oil
    # sensitivity is an exposure illustration, with no inferred exact hedge/tax offset.
    oil_million_bbl = -float(facts["annual2025","production"]["oil_reserves"])
    oil_loss = oil_million_bbl*12*market["usd_cny"]/100
    gas_loss = 247.528*.06*10
    downstream_loss = 100
    after_tax_loss = (oil_loss+gas_loss+downstream_loss)*.76
    stress_ocf = 4200-after_tax_loss
    rates = [.08, .10, .12]
    cases = {}
    inputs = {
        "base": [4200,2700,140,160,120,170],
        "full_spend": [4200,2925,140,160,120,170],
        "better": [4400,2500,120,140,150,150],
        "stress": [stress_ocf,2700,150,175,90,140]
    }
    for label, (ocf, capex, lease, interest, received, nci) in inputs.items():
        cash = ocf-capex-lease-interest+received-nci
        result = {f"{r:.2f}": (cash/SHARES_YI)/r for r in rates}
        cases[label] = dict(ocf=ocf, capex=capex, lease=lease, interest=interest, received=received, nci=nci,
                            cash=cash, per_share=cash/SHARES_YI, epv_cny=result,
                            epv_hkd={k:v/market["hkd_cny"] for k,v in result.items()})

    pos = "2026-BS"
    bal = {key: get("q32026", key, pos) for key in [
        "noncurrent_assets","current_assets","current_liab","noncurrent_liab","owner_equity","nci_equity",
        "cash","short_deposit","long_deposit","short_debt","long_debt","lease_current","lease_noncurrent","end_retirement"
    ]}
    cashlike = sum(bal[key] for key in ["cash", "short_deposit", "long_deposit"])
    contractual = sum(bal[key] for key in ["short_debt", "long_debt", "lease_current", "lease_noncurrent"])
    price = dict(market, h_cny=holdings, h_discount=1-holdings/market["a_cny"],
                 h_needs_at_10=.10*holdings*SHARES_YI, a_needs_at_10=.10*market["a_cny"]*SHARES_YI,
                 h_needs_at_8=.08*holdings*SHARES_YI)
    required = price["h_needs_at_10"]
    base = cases["base"]
    h_investor = dict(required_with_full_payout_and_20pct_tax=required/.8,
                      favorable_hkd_after_20pct_tax=cases["better"]["epv_hkd"]["0.10"]*.8,
                      gross_cash_headroom=cases["better"]["cash"]-required,
                      max_base_capex_for_gross_threshold=base["capex"]+base["cash"]-required,
                      min_base_ocf_for_gross_threshold=base["ocf"]-base["cash"]+required)
    stress = cases["stress"]["cash"]
    recovery_cny = (stress/1.1+stress/1.1**2+base["cash"]/.10/1.1**2)/SHARES_YI
    shareholder = {}
    for div in [.47, .18]:
        for terminal_fraction in [1, .75]:
            paid = div*.8
            key = f"{div:.2f}-{terminal_fraction}"
            shareholder[key] = irr([-holdings]+[paid]*4+[paid+holdings*terminal_fraction])

    return {"units":"RMB 100m except shares in 100m, and per-share and market price", "shares_yi":SHARES_YI,
            "price":price,"observed":observed,"balances":bal,"cash_including_term":cashlike,"debt_including_leases":contractual,
            "balance_difference":cashlike-contractual,"book_per_share":bal["owner_equity"]/SHARES_YI,
            "pressure":dict(oil_loss=oil_loss, gas_loss=gas_loss, downstream_loss=downstream_loss, after_tax_loss=after_tax_loss),
            "cases":cases,"h_investor":h_investor,"two_stress_years_then_base_at_10":recovery_cny,
            "h_5y_net_irr":shareholder}


if __name__ == "__main__":
    output = calculate()
    (HERE/"valuation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: output[k] for k in ["price","cases","balance_difference","book_per_share","h_5y_net_irr"]},
                     ensure_ascii=False, indent=2))
