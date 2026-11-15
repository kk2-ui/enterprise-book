"""Assemble the fixed book parts and a desktop/offline copy for continuous reading."""
import base64
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
FIG = re.compile(r"\[\[figure:FIG_(\w+)\|([^\]]+)\]\]")
DOC = re.compile(r"\[\[doc:([\w-]+)@(\d+)\|([^\]]+)\]\]")


def parts():
    split = re.split(r"^# ([\w-]+) \| (.+)$", (HERE/"企业书.md").read_text(), flags=re.M)
    ordered = {
        split[i]: {"title": split[i+1], "body": split[i+2].strip()}
        for i in range(1, len(split), 3)
    }
    ordered["valuation"] = {"title": "普通股现金与三步估值", "body": ordered["chapter-7"]["body"]}
    return ordered


def write_reader(book, destination):
    docs = {d["id"]: d["url"] for d in json.loads((HERE/"collection.json").read_text())["documents"]}

    def inline(raw):
        val = escape(raw)
        val = DOC.sub(lambda m: f'<a class="ref" href="{escape(docs[m[1]])}#page={m[2]}">{m[3]} · PDF第{m[2]}页</a>', val)
        val = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', val)
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", val)

    def render(body):
        output = []
        for block in body.split("\n\n"):
            if (m := FIG.fullmatch(block.strip())):
                data = base64.b64encode((HERE/"figures"/(m[1].lower()+".png")).read_bytes()).decode()
                output.append(f'<figure><img src="data:image/png;base64,{data}" alt="{escape(m[2])}"><figcaption>{escape(m[2])}</figcaption></figure>')
            elif block.startswith("## "):
                output.append(f"<h3>{inline(block[3:])}</h3>")
            elif block.startswith("|"):
                cells = [[x.strip() for x in row.strip().strip("|").split("|")] for row in block.splitlines()]
                headers = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
                rows = "".join("<tr>"+"".join(f"<td>{inline(c)}</td>" for c in row)+"</tr>" for row in cells[2:])
                output.append(f'<div class="table"><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>')
            else:
                output.append(f"<p>{inline(block)}</p>")
        return "".join(output)

    columns = {key: part for key, part in book.items() if key!="valuation"}
    nav = "".join(f'<a href="#{key}">{escape(part["title"])}</a>' for key,part in columns.items())
    articles = "".join(f'<article id="{key}"><h2>{escape(part["title"])}</h2>{render(part["body"])}</article>'
                       for key,part in columns.items())
    css = """
body{margin:0;background:#f8faf8;color:#142c30;font:17px/1.85 system-ui,"PingFang SC",sans-serif}
main{max-width:960px;margin:auto;padding:35px 34px 80px}
header{margin-bottom:22px} h1{font-size:36px;line-height:1.3;margin-bottom:9px}
h2{font-size:28px;line-height:1.4} h3{font-size:22px;margin:34px 0 10px}
article{border-top:1px solid #cddbd7;margin-top:42px;padding-top:15px}
nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 24px;
    padding:18px 0;border-block:1px solid #cddbd7}
a{color:#086b63;text-underline-offset:3px}.ref{font-size:14px;margin-left:5px}
figure{margin:28px 0}figure img{width:100%;height:auto;display:block}
figcaption{color:#4c6566;font-size:14px;padding-top:9px}
.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px}
td,th{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #cddbd7}
th{background:#e4efea}
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>中国石油企业书修订版</title><style>{css}</style><main>'
        '<header><h1>中国石油企业书修订版</h1><p>601857.SH / 00857.HK · 研究时点 2026年11月13日</p></header>'
        f'<nav aria-label="全文目录">{nav}</nav>{articles}</main></html>'
    )


if __name__ == "__main__":
    book = parts()
    (HERE/"book_parts.json").write_text(json.dumps(book, ensure_ascii=False, indent=2)+"\n")
    write_reader(book, HERE/"exports"/"中国石油企业书_修订版.html")
