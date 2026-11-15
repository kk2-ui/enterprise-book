"""Use the shared source parser for the book's cash, reserves and liability rows."""
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from source_data.disclosures import extract_manifest


def annual(year):
    return {str(n): {"label": f"{n}年度", "start": f"{n}-01-01", "end": f"{n}-12-31"} for n in year}


def interim():
    return {str(n): {"label": f"{n}年前三季（比较列已追溯）", "start": f"{n}-01-01", "end": f"{n}-09-30"} for n in (2026, 2025)}


def dates():
    return {str(n): {"label": str(d), "end": str(d)} for n, d in ((2026, "2026-09-30"), (2025, "2025-12-31"))}


def row(key, label, page, columns, *, occurrence=None, following=0, unit=None, pattern=None, skip_amounts=0):
    value = {"id": key, "label": label, "pages": [page], "pattern": pattern or "^"+re.escape(label)+r"(?:\s+|$)",
             "columns": list(columns), "number_format": "financial"}
    if occurrence is not None:
        value["occurrence"] = occurrence
    if following:
        value["following_lines"] = following
    if unit:
        value["unit"] = unit
    if skip_amounts:
        value["skip_amounts"] = skip_amounts
    return value


def source(doc, periods, rows):
    return {"id": doc, "text_path": "sources/"+doc+".txt", "unit": "人民币百万元",
            "scope": "中国石油合并IFRS", "periods": periods, "rows": rows}


fin_en_1 = [
    ("wc_receivables", "Accounts receivable, prepayments and other current assets"),
    ("wc_inventory", "Inventories"), ("wc_payables", "Accounts payable and accrued liabilities"),
    ("wc_contract", "Contract liabilities"), ("ocf", "NET CASH FLOWS FROM OPERATING ACTIVITIES")
]
fin_en_2 = [
    ("capex", "Capital expenditures"), ("lease_paid", "Repayments of lease liabilities"),
    ("interest_paid", "Interest paid"), ("div_received", "Dividends received"),
    ("nci_div", "Dividends paid to non-controlling interests"), ("owner_div", "Dividends paid to owners of the Company")
]
fin_zh_1 = [
    ("wc_receivables", "应收账款、预付款和其他流动资产"), ("wc_inventory", "存货"),
    ("wc_payables", "应付账款和应计负债"), ("wc_contract", "合同负债"), ("ocf", "经营活动产生的现金流量净额")
]
fin_zh_2 = [
    ("capex", "资本性支出"), ("lease_paid", "偿还租赁负债"), ("interest_paid", "已付利息"),
    ("div_received", "已收股息"), ("nci_div", "支付非控制性权益股息"), ("owner_div", "支付母公司股东股息"),
    ("storage_paid", "同一控制下企业合并支付的对价")
]
stocks = [
    ("ppe", "物业、厂房及机器设备"), ("equity_investments", "联营公司及合营公司的投资"), ("rou", "使用权资产"),
    ("cash", "现金及现金等价物"), ("short_deposit", "到期日为三个月以上一年以内的定期存款"),
    ("long_deposit", "到期日为一年以上的定期存款"), ("short_debt", "短期借款"), ("long_debt", "长期借款"),
    ("nci_equity", "非控制性权益"), ("owner_equity", "归属于母公司股东权益总额"),
    ("end_retirement", "资产弃置义务"), ("current_assets", "流动资产总额"), ("current_liab", "流动负债总额"),
    ("noncurrent_liab", "非流动负债总额"), ("noncurrent_assets", "非流动资产总额")
]
y25, y24, q26 = annual([2025, 2024]), annual([2024, 2023]), interim()
hist = annual([2025, 2024, 2023, 2022, 2021])
qstock = {str(year)+"-BS": spec for year, spec in dates().items()}
reserve = {
    "oil_reserves": {"label": "石油，百万桶"},
    "gas_reserves": {"label": "天然气，十亿立方英尺"},
    "boe_reserves": {"label": "百万桶油当量"}
}
periods_2025 = hist | reserve | {
    "pipe_2025": {"label": "国家管网2025"}, "pipe_2024": {"label": "国家管网2024"},
    "finance_2025": {"label": "中油财务2025"}, "finance_2024": {"label": "中油财务2024"}
}
qprog = [
    ("oil_profit", "油气和新能源"), ("refining_profit", "炼油化工和新材料"),
    ("marketing_profit", "销售"), ("gas_profit", "天然气销售"), ("hq_profit", "总部及其他")
]

MANIFEST = {
    "as_of": "2026-11-13",
    "sources": [
        source("annual2025", periods_2025,
               [row(key, label, 220, y25) for key, label in fin_en_1]
               + [row(key, label, 221, y25) for key, label in fin_en_2]
               + [row("profit_ops", "Profit from operations", 8, hist),
                  row("profit_owner", "Owners of the Company", 8, hist, occurrence=0),
                  row("profit_nci", "Non-controlling interest", 8, hist, occurrence=0),
                  row("capex_management", "Capital expenditures", 8, hist),
                  row("ocf_history", "Net cash flows from operating", 8, hist, following=1),
                  row("retirement_settled", "Liabilities settled", 277, y25),
                  row("depletion", "Depreciation, depletion and amortisation", 220, y25),
                  row("reserves", "Reserves as of December 31, 2025 (the basis date)", 106, reserve,
                      unit="按三项列定义", skip_amounts=2),
                  row("production", "Production for the year", 106, reserve, occurrence=1, unit="按三项列定义"),
                  row("pipe_carry", "Carrying amount of interest in associates", 163,
                      ["pipe_2025", "pipe_2024", "finance_2025", "finance_2024", "2025"]),
                  row("pipe_div", "Dividends received by the Group", 163,
                      ["pipe_2025", "pipe_2024", "finance_2025", "finance_2024"])]),
        source("annual2024", y24,
               [row(key, label, 229, y24) for key, label in fin_en_1]
               + [row(key, label, 230, y24) for key, label in fin_en_2]),
        source("q32026", q26 | qstock,
               [row(key, label, 21, q26) for key, label in fin_zh_1]
               + [row(key, label, 22, q26) for key, label in fin_zh_2 if key!="storage_paid"]
               + [row("storage_paid", "同一控制下企业合并支付的对价", 22, ["2026"])]
               + [row(key, label, 20, qstock) for key, label in stocks]
               + [row("lease_current", "租赁负债", 20, qstock, occurrence=0),
                  row("lease_noncurrent", "租赁负债", 20, qstock, occurrence=1),
                  row("profit_ops", "经营利润", 19, q26),
                  row("associate_profit", "应占联营公司及合营公司的利润", 19, q26)]
               + [row(key, label, 23, q26, pattern="^"+label+r"\s+\(?[\d,]+\)?\s+")
                  for key, label in qprog])
    ]
}

if __name__ == "__main__":
    out = extract_manifest(MANIFEST, HERE)
    # Keep the receipt portable; source document IDs own the original-page locators.
    for item in out["rows"]:
        item["text_path"] = "sources/"+item["document"]+".txt"
    (HERE / "disclosures.json").write_text(json.dumps(out, ensure_ascii=False, indent=2)+"\n")
    print(f'{len(out["rows"])} disclosure rows extracted')
