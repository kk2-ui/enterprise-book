"""Render figures from the fixed disclosures and book scenarios."""
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)
BG, INK, MUTED = "#f8faf8", "#142c30", "#4c6566"
TEAL, BLUE, RED, RULE = "#117870", "#2b6583", "#a34833", "#cddbd7"


def font(size):
    path = os.environ.get("PETROCHINA_FIGURE_FONT", "/System/Library/Fonts/STHeiti Medium.ttc")
    return ImageFont.truetype(path, size)


def line(draw, xy, label, size, color=INK, anchor="la"):
    draw.text(xy, label, font=font(size), fill=color, anchor=anchor)


def frame(title, subtitle, height=690):
    img = Image.new("RGB", (1500, height), BG)
    draw = ImageDraw.Draw(img)
    line(draw, (65, 34), title, 45)
    line(draw, (65, 102), subtitle, 27, MUTED)
    return img, draw


def box(d, xy, head, sentence, color):
    x, y, x2, y2 = xy
    d.rounded_rectangle(xy, 12, fill="white", outline=color, width=3)
    line(d, (x+22, y+23), head, 29, color)
    for i, s in enumerate(sentence):
        line(d, (x+22, y+67+i*32), s, 24)


def right(d, x, y, to, color):
    d.line((x,y,to,y), fill=color, width=5)
    d.polygon([(to,y),(to-13,y-9),(to-13,y+9)], fill=color)


image, d = frame("天然气购销、管输与股利分开结算", "季节调节要先买气和入库。管输服务、储气服务及股权分配分别发生。", 830)
box(d,(65,189,405,377),"气源",["上市体系的国产气","向其他供应者买气","边境管道或 LNG 接收"],TEAL)
box(d,(569,189,933,377),"上市体系的销售与调度",["选气源，签购销合同","预订管输与储气服务","提前注气，旺季提取"],TEAL)
box(d,(1093,189,1435,377),"买家",["城燃、电厂和工业客户","合同约定交付点及价量","交货后结算或依约预收"],TEAL)
right(d,409,277,560,TEAL)
right(d,937,277,1085,TEAL)
d.line((752,377,752,443),fill=BLUE,width=5)
d.polygon([(752,449),(741,429),(763,429)],fill=BLUE)
box(d,(436,451,1060,590),"为运输与储气服务付费",["干线由管网运营方提供服务。","部分储气库由上市体系合并。"],BLUE)
box(d,(65,644,401,757),"国家管网",["形成可分配收益"],TEAL)
right(d,406,694,1090,TEAL)
line(d,(746,645),"股东按持股及实际分派取得股利",24,TEAL,anchor="ma")
box(d,(1093,644,1435,757),"中国石油股份公司",["持29.9%股权"],TEAL)
line(d,(65,789),"资料：中国石油2025年报、2026年中报及国家发改委保供合同文件。",23,MUTED)
image.save(OUT/"gas.png")

rows = {(r["document"],r["id"]):r["values"] for r in json.loads((HERE/"disclosures.json").read_text())["rows"]}
yrs = [str(n) for n in range(2021,2026)]


def plot(d, key, color, y_floor, height, top, ymax):
    xs = [225+int(1100*i/4) for i in range(len(yrs))]
    vals = [float(rows["annual2025", key][y])/100 for y in yrs]
    coords = [(x,y_floor-int(val/ymax*height)) for x,val in zip(xs, vals)]
    d.line(coords, fill=color, width=6)
    for x,y in coords:
        d.ellipse((x-7,y-7,x+7,y+7), fill=color)
    for v in (0, top):
        line(d,(93, y_floor-int(v/ymax*height)), f"{v:,}", 22,MUTED,anchor="rm")


image,d=frame("资本开支相近，营业现金仍随经营起伏","2021—2025年，人民币亿元。经营现金、管理层资本开支各用原披露口径。",784)
line(d,(115,169),"经营现金",25,TEAL)
line(d,(313,169),"管理层资本开支",25,BLUE)
for value in (0,2500,5000):
    y=443-int(value/5000*225)
    d.line((105,y,1415,y),fill=RULE,width=2)
line(d,(92,331),"2,500",22,MUTED,anchor="rm")
plot(d,"ocf_history",TEAL,443,225,5000,5000)
plot(d,"capex_management",BLUE,443,225,5000,5000)
line(d,(115,476),"归属于母公司股东的净利润",25,INK)
for value in (0,1000,2000):
    y=674-int(value/2000*155)
    d.line((105,y,1415,y),fill=RULE,width=2)
line(d,(92,597),"1,000",22,MUTED,anchor="rm")
plot(d,"profit_owner",INK,674,155,2000,2000)
for i, yr in enumerate(yrs):
    line(d,(225+int(1100*i/4),697),yr,25,MUTED,anchor="ma")
line(d,(65,751),"资料：中国石油2025年报 IFRS 附表。现金流表的付现资本开支另列于长期财务页。",22,MUTED)
image.save(OUT/"history.png")

cases = json.loads((HERE/"valuation.json").read_text())


def bridge(title, subtitle, footer, steps, fname):
    picture,d=frame(title,subtitle,720)
    left, width, top, bottom = 102, 1348, 175, 555
    scale=(bottom-top)/4700
    for v in (0,1000,2000,3000,4000):
        y=bottom-v*scale
        d.line((left,y,1435,y),fill=RULE,width=2)
        line(d,(92,y),f"{v:,}",21,MUTED,anchor="rm")
    spacing=width/len(steps)
    value=0
    centers=[int(left+spacing*(i+.5)) for i in range(len(steps))]
    for i,(name,delta) in enumerate(steps):
        x=centers[i]
        total=i==0 or delta is None
        high=max(value,value+delta) if not total else (value if delta is None else delta)
        low=min(value,value+delta) if not total else 0
        color=TEAL if total else BLUE if delta>0 else RED
        y1,y2=bottom-high*scale,bottom-low*scale
        d.rectangle((x-51,y1,x+51,y2),fill=color)
        display = f"{high:,.0f}" if total else f"{delta:+,.0f}"
        line(d,(x,y1-35),display,27,color,anchor="ma")
        line(d,(x,583),name,23,MUTED,anchor="ma")
        if delta is not None:
            value+=delta
        if i+1<len(steps):
            end=bottom-value*scale
            d.line((x+51,end,centers[i+1]-51,end),fill=MUTED,width=2)
    line(d,(65,669),footer,22,MUTED)
    picture.save(OUT/fname)


real = cases["observed"]["2025"]
bridge("2025年经营现金至上市股东派息前",
       "合并现金的指定项目实际桥接，人民币亿元。图中取整，正文保留原数。",
       "资料：中国石油2025年报现金流量表。仍有其他投资及融资项目，余量不等于普通股可派现金。",
       [("经营现金",real["ocf"]),("付现开支",real["capex"]),("租赁本金",real["lease_paid"]),
        ("已付利息",real["interest_paid"]),("实收股息",real["div_received"]),("少数股息",real["nci_div"]),
        ("派息前余量",None)], "cash.png")
case=cases["cases"]["base"]
bridge("从合并经营到普通股的正常现金",
       "主情景，人民币亿元/年。最大的支出是油田、炼厂和其他设施的长期维持与替换。",
       "假设有息融资可续接，尚未加可兑现的额外本金；需验证维护开支、租赁及少数股东份额。",
       [("经营现金",case["ocf"]),("维持付现",-case["capex"]),("租赁本金",-case["lease"]),
        ("实付融资息",-case["interest"]),("投资股息",case["received"]),("少数权益",-case["nci"]),
        ("普通股现金",None)], "normal.png")

image,d=frame("四种现金情景，能否满足当时的价格要求？",
              "按2026年11月13日收盘和10%股权回报反算。人民币亿元/年，投资者个人税前。",690)
start, right_edge, top, bottom = 295, 1400, 227, 590
scale=(right_edge-start)/2500
for tick in (0,500,1000,1500,2000,2500):
    x=start+tick*scale
    d.line((x,top,x,bottom),fill=RULE,width=2)
    line(d,(x,bottom+12),str(tick),21,MUTED,anchor="ma")
for i,(label,key) in enumerate([
    ("共同逆风","stress"),("投资全额付现","full_spend"),("主情景","base"),("经营较好","better")
]):
    y=263+83*i
    extent=cases["cases"][key]["cash"]
    x=start+extent*scale
    line(d,(start-22,y+20),label,26,INK,anchor="rm")
    d.rectangle((start,y,x,y+40),fill=TEAL if key=="better" else BLUE)
    line(d,(x+13,y+20),f"{extent:,.0f}",26,INK,anchor="lm")
for name, key, color in [("H股所需 1,618","h_needs_at_10",RED),("A股所需 2,268","a_needs_at_10",INK)]:
    x=start+cases["price"][key]*scale
    line(d,(x,174),name,24,color,anchor="ma")
    for y in range(top,bottom,20):
        d.line((x,y,x,min(y+11,bottom)),fill=color,width=4)
line(d,(65,647),"较好情景仅多约22亿元。门槛假设现金能兑现给普通股，未扣个人税。",24,MUTED)
image.save(OUT/"threshold.png")
