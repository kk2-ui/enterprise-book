"""Install the published PetroChina edition into a local development database."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1]
sys.path.insert(0, str(APP))
from app import Store
from source_data.acquisition import collect_document
from source_data.packages import build_package
from source_data.repository import encode
import model_books
from build_reader import parts as read_parts

NAME = "中国石油"
CODE = "601857.SH"
TITLE = "中国石油企业书 · 修订版 v1"
VERSION = "petrochina-sources-20261115-v1"
CUTOFF = "2026-11-13"
PUBLISHED = "2026-11-15"
MODEL = {"name": "Codex", "version": "gpt-6.1-sol"}
FIG = re.compile(r"\[\[figure:FIG_(\w+)\|")
REVIEWS = ["独立首读.md","独立经济审阅.md","阅读改后复核.md","经济改后复核.md"]


def load(name):
    return json.loads((HERE/name).read_text())


def company_id(store):
    with store.connect() as db:
        rows = db.execute(
            "SELECT id FROM companies WHERE json_extract(data, '$.name') IN (?,?) OR json_extract(data, '$.code') IN (?,?)",
            (NAME, "中国石油天然气股份有限公司", CODE, "00857.HK"),
        ).fetchall()
    if len(rows)>1:
        raise SystemExit("公司档案存在重复，请核实读取入口。")
    if not rows:
        return store.add_company({"name": NAME, "code": CODE, "industry": "石油与天然气", "currency":"CNY"})
    cid = rows[0]["id"]
    c = store.company(cid)
    if c.get("default_book_edition_id") and not any(x["title"]==TITLE for x in c["book_editions"]):
        raise SystemExit("已有中国石油默认版本，先核实承接范围。")
    return cid


def fixed_sources(store, cid, collection):
    from extract import MANIFEST

    repo = store.source_data
    docs = {d["id"]:d for d in repo.documents(cid)}
    rows = load("disclosures.json")["rows"]
    local = [d for d in collection["documents"] if (HERE/"sources"/d["file"]).is_file()]
    needed = {k for part in read_parts().values() for k in re.findall(r"\[\[doc:([\w-]+)@",part["body"])}
    if needed-{d["id"] for d in local}:
        raise SystemExit("缺少正文引用的本地原件。")
    for doc in local:
        if doc["id"] in docs:
            continue
        path = HERE/"sources"/doc["file"]
        extraction = next((spec for spec in MANIFEST["sources"] if spec["id"]==doc["id"]),{})
        spec = doc | {
            "local_path": str(path), "text_path": str(path.with_suffix(".txt")),
            "rows": [r for r in rows if r["document"]==doc["id"]], "periods": extraction.get("periods",{})
        }
        result = collect_document(repo, cid, spec, collection["acquired_on"])
        if result["document"] is None:
            raise RuntimeError(doc["id"]+": "+result["acquisition"]["error"])
        docs[doc["id"]]=result["document"]

    if not any(x["id"]==VERSION for x in repo.packages(cid)):
        spec = {
            "id":VERSION, "title":"中国石油2026年11月修订企业书固定资料",
            "company":{"id":cid,"name":NAME,"code":CODE,"currency":"CNY"},
            "information_cutoff":CUTOFF, "valuation_date":CUTOFF,
            "documents":[{"id":d["id"],"revision":docs[d["id"]]["revision"]} for d in local],
            "coverage":["年度2020、2024、2025，公司2026中报、三季报及储气库、关联交易、分红公告。",
                        "中国石化2025年报摘要、中国海油2025年报用于经营对比。",
                        "现金、周转、资本开支、负债、储量等明确披露行保留页码。"],
            "gaps":["监管政策、2016年20-F及同日行情汇率按正文所列线上原文另行引用。",
                    "单井和项目维持性现金开支、气源逐单价量、子公司可分现金及未来余资兑现未完整披露。"]
        }
        build_package(repo,cid,spec,create_archive=False)
    return repo.package(cid, VERSION)


def add_figures(store, cid, book):
    repo = store.source_data
    existing = {r["title"]:r["id"] for r in repo.list_sources(cid)}
    ids = {}
    for key in sorted({m for part in book.values() for m in FIG.findall(part["body"])}):
        title = {
            "GAS":"中国石油天然气交付与供气合同",
            "HISTORY":"中国石油经营现金和归母净利",
            "CASH":"中国石油2025年实际现金桥",
            "NORMAL":"中国石油正常普通股现金主例",
            "THRESHOLD":"中国石油A/H价格的年度现金要求",
        }[key]
        file = HERE/"figures"/(key.lower()+".png")
        ids[key] = existing.get(title) or repo.add_source(cid,{
            "title":title, "kind":"研究图", "fact_period":"截至"+CUTOFF, "published_on":PUBLISHED,
            "notes":"本版企业书配图，由披露数据与正文所列假设绘制。"
        },file.read_bytes(),file.name)
    for part in book.values():
        part["body"] = FIG.sub(lambda m: "[[figure:"+ids[m[1]]+"|",part["body"])
    return ids


def other_sources(collection, spec):
    fixed = {m["id"] for m in spec["documents"]}
    extra = [{"title":m["title"],"url":m["url"]} for m in collection["documents"]
             if m["id"] not in fixed and m["id"]!="annual2017summary"]
    extra += load("market.json")["sources"]
    extra += [
        {"title":"发改委关于风险准备金的说明", "url":"https://www.ndrc.gov.cn/fggz/fgzy/shgqhy/202003/t20200321_1223854.html"},
        {"title":"发改委2026年11月12日成品油调价", "url":"https://www.ndrc.gov.cn/xwdt/xwfb/202611/t20261112_1408795.html"},
        {"title":"中国石油昆仑资本增资公告", "url":"https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0830/2026083000003.pdf"},
        {"title":"财政部股息红利差别化税率", "url":"https://www.chinatax.gov.cn/chinatax/n810341/n810755/c1797427/content.html"}
    ]
    return extra


def install(directory):
    for file in REVIEWS:
        if not (HERE/file).read_text().strip():
            raise SystemExit("缺实际审阅材料："+file)
    store = Store(directory)
    cid = company_id(store)
    current = store.company(cid)
    existing = next((e for e in current["book_editions"] if e["title"]==TITLE), None)
    if existing:
        return {"company": cid, "edition": existing["id"], "already_installed": True}
    collection = load("collection.json")
    spec = fixed_sources(store,cid,collection)
    parts = read_parts()
    missing = set(model_books.REQUIRED)-parts.keys()
    if missing:
        raise ValueError("缺少整书部分："+",".join(sorted(missing)))
    figures = add_figures(store,cid,parts)
    tasks = [t for t in model_books.tasks(store,cid) if t["title"]==TITLE]
    task = tasks[0] if tasks else model_books.create_task(store,cid,{
        "title":TITLE, "model":MODEL, "source_version":VERSION
    })
    for key,value in parts.items():
        model_books.save_part(store,cid,task["id"],key,value)
    edition = model_books.complete(store,cid,task["id"],{
        "model":MODEL,"additional_sources":other_sources(collection,spec)
    })
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        company = json.loads(conn.execute("SELECT data FROM companies WHERE id=?",(cid,)).fetchone()[0])
        stored = json.loads(conn.execute("SELECT data FROM book_editions WHERE id=? AND company_id=?",
                                         (edition["id"],cid)).fetchone()[0])
        stored.update(review_status="independent_review",
                      provenance="2026年11月15日正式发布的修订版，附独立首读、经济核源及改后复核。",
                      review_artifacts=[(HERE/p).relative_to(APP.parent).as_posix() for p in REVIEWS])
        conn.execute("UPDATE book_editions SET data=? WHERE id=? AND company_id=?",
                     (encode(stored),edition["id"],cid))
        company.update(
            default_book_edition_id=edition["id"], stage="重资产成熟经营",
            summary="601857.SH／00857.HK。经营、股东现金与A/H定价研究，资料截至2026年11月13日。",
            thesis="H股价格低于A股，按现有普通股现金证据，暂未确认安全边际。",
            rival="稳产、炼化更新及保供投入持续，油气毛差回落时可分现金明显下降。",
            triggers="完整2026年报披露后复算全年度付现、储量接替、气销毛差和到账投资股息。",
            cash="约1,150亿元/年", cash_label="普通股正常现金 · 主情景",
            value="6.28元/股", value_label="10%股权回报率 · 主情景",
            next="跟踪2026年报与实际分配", organization={
                "market":"沪港两地", "sector":"石油与天然气","research_status":"持续跟踪",
                "tags":["00857.HK","油气","A/H"],"pinned":False
            }
        )
        conn.execute("UPDATE companies SET data=? WHERE id=?",(encode(company),cid))
    return dict(company=cid, edition=edition["id"], source_version=VERSION, task=task["id"],
                figures=figures, documents=spec["document_count"], cells=spec["disclosed_cells"],
                parts=list(parts))

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=APP/"data")
    args = parser.parse_args()
    print(json.dumps(install(args.data_dir.resolve()),ensure_ascii=False,indent=2))
