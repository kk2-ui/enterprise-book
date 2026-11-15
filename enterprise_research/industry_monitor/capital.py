"""Original monthly share returns, excluding treasury and unissued authorisation."""
import re
from datetime import date
from .disclosures import available_close_day


def monthly_shares(text, record):
    date_match=re.search(r'截至月份[^\n]*?[:：]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',text)
    if date_match:as_of=date(*map(int,date_match.groups())).isoformat()
    else:
        date_match=re.search(r'截至月份[^\n]*?\s*[:：]\s*(\d{1,2})[／/](\d{1,2})[／/](\d{4})',text)
        if not date_match:raise ValueError('月报期间不能识别，须核对原件')
        d,m,y=map(int,date_match.groups());as_of=date(y,m,d).isoformat()
    match=re.search(r'II\.\s*已發行(.*?)(?=III\.)',text,re.S)
    if not match:raise ValueError('已发行股本表未识别；不得以法定股本替代')
    section=match.group(1)
    if '不同投票權' in section:raise ValueError('多重股份权利须研究确认')
    rows=[]
    ordinary_pattern=r'股份(?:分類|類別)\s*普通股'
    modern=bool(re.search(ordinary_pattern,section))
    if not modern:
        # Historical forms place ordinary classes horizontally before the
        # preferred/other columns. Printed blank template columns are not shares.
        header=next((s for s in section.splitlines() if '優先股數目' in s),None)
        if not header:raise ValueError('旧月报未识别普通股与其他类别分界')
        boundary=header.index('優先股數目')
        for line in section.splitlines():
            if not re.match(r'\s*本月底結存',line):continue
            tokens=list(re.finditer(r'(?<!\w)\d[\d,]*(?:\.\d+)?',line))
            ordinary=[t for t in tokens if t.start()<boundary]
            if any(float(t.group().replace(',',''))!=0 for t in tokens if t.start()>=boundary):
                raise ValueError('非普通股有实际发行数量，须确认权利和归属')
            rows.extend(dict(outstanding=float(t.group().replace(',','')),excerpt=line.strip()) for t in ordinary)
        if not rows:raise ValueError('旧月报未找到已发行普通股')
    for line in section.splitlines():
        if not modern:break
        if re.match(r'\s*本月底結存',line):
            numbers=re.findall(r'(?<!\w)\d[\d,]*(?:\.\d+)?',line)
            if len(numbers) not in (1,2,3):raise ValueError('月报股份列含义未识别')
            # FF301 first column is issued excluding treasury. Older forms
            # without a treasury column have the single issued-share value.
            rows.append(dict(outstanding=float(numbers[0].replace(',','')),excerpt=line.strip()))
    if not rows:raise ValueError('月报未找到已发行股份结存')
    if modern and len(rows)!=len(re.findall(ordinary_pattern,section)):
        raise ValueError('股份类别与结存行数不符，不能推断全部普通股')
    return dict(value=sum(r['outstanding'] for r in rows),kind='total_common_shares',as_of=as_of,
                available_on=available_close_day(record),vintage='original',currency='SHARES',
                treasury_excluded=True,classes=rows,source_url=record['url'],document_id='hkex-'+record['id'],
                valuation_basis='上市普通股收盘价推算全部同权普通股（不含库存股）；有内资股时亦计入，非仅上市股份市值',
                limitation='截至最后可得股本月报；月内资本事件须与公告交叉核对')


def nextday_shares(text,record,previous=None):
    """Read the issued-share roll-forward, never the repurchase-volume table."""
    section=re.split(r'第二章節|第二部分',text)[0]
    ordinary=bool(re.search(r'股份(?:分類|類別)\s*普通股|證券詳情[^\n]*普通股',section))
    modern='FF305' in section and ordinary
    if not ordinary:raise ValueError('翌日披露的普通股类别未确认')
    if re.search(r'股份分類\s*H股|股份類別\s*H股',section) and previous is None:
        raise ValueError('只有H股变动，缺少全部同权普通股的上期基准')
    date_pattern=r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    def parse_balances(word):
        found=[];lines=section.splitlines()
        for index,line in enumerate(lines):
            if not re.search('於下列日期'+word+'時的結存',line):continue
            context='\n'.join(lines[index:index+4]);dt=re.search(date_pattern,context)
            if not dt:raise ValueError('翌日披露结存日期未识别')
            # Older forms print the single balance immediately above the label.
            candidates=re.findall(r'(?<![\w,])\d{1,3}(?:,\d{3})+(?![\w,])',context)
            if not candidates and index and re.fullmatch(r'\s*\d[\d,]*\s*',lines[index-1]):
                candidates=[lines[index-1].strip()]
            nums=[float(x.replace(',','')) for x in candidates]
            if modern:
                # Treasury can be printed as ungrouped 0. Use the same dated row.
                same_dt=re.search(date_pattern,line)
                if same_dt:nums=[float(x.replace(',','')) for x in re.findall(r'\d[\d,]*',line[same_dt.end():])]
                if len(nums)!=3 or abs(nums[0]+nums[1]-nums[2])>.5:raise ValueError('翌日已发行/库存/总股数不能勾稽')
            elif len(nums)!=1:raise ValueError('旧翌日披露结存金额无法唯一识别')
            found.append(dict(as_of=date(*map(int,dt.groups())).isoformat(),outstanding=nums[0],
                              treasury=nums[1] if modern else 0,total=nums[2] if modern else nums[0],excerpt=context))
        return found
    balances=parse_balances('結束')
    if not balances:raise ValueError('翌日披露没有已发行普通股的期终结存')
    if len(set(r['as_of'] for r in balances))!=1:raise ValueError('多个股份类别期终日不同，须核读')
    classes=balances
    if previous and len(previous['classes'])>len(balances):
        starts=[r['outstanding'] for r in parse_balances('開始')]
        if len(starts)!=len(balances):raise ValueError('股份类别不全且缺少可核对的期初股数')
        classes=[dict(r) for r in previous['classes']]
        for start,balance in zip(starts,balances):
            hits=[i for i,r in enumerate(classes) if r['outstanding']==start]
            if len(hits)!=1:raise ValueError('翌日股份类别无法与已知全部普通股衔接')
            classes[hits[0]]=balance
    return dict(value=sum(r['outstanding'] for r in classes),kind='total_common_shares',as_of=balances[0]['as_of'],
                available_on=available_close_day(record),vintage='original',currency='SHARES',treasury_excluded=True,
                classes=classes,source_url=record['url'],document_id='hkex-'+record['id'],
                previous_observation_id=previous.get('id') if previous else None,
                valuation_basis='上市普通股价格推算全部同权普通股，库存股不计入；股份类别由月报及翌日变动衔接',
                limitation='最后已公开股本观测；无当日发行资料时不推测未披露变化')
