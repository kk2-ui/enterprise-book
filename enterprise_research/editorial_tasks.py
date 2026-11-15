"""Build role instructions from the canonical editorial documents, without a second standard."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = 'research/templates/'
ROLES = {
    'coordinator': ('任务协调', [TEMPLATES+'企业书入库与修订任务.md', 'EDITORIAL_WORKFLOW.md']),
    # Put the role's actual deliverables before the longer reference standards.
    'research': ('问题研究', [TEMPLATES+'企业研究与估值任务.md', 'RESEARCH_VALUATION_WORKFLOW.md', 'SOURCE_DATA.md']),
    'writer': ('单一主笔写作或修订', [TEMPLATES+'企业书编写任务.md', 'WRITING_STANDARD.md']),
    'first_read': ('独立正文首读', [TEMPLATES+'企业书独立审阅任务.md', 'WRITING_STANDARD.md']),
    'fact_review': ('事实机制或投资判断审阅', [TEMPLATES+'企业书独立审阅任务.md', 'RESEARCH_VALUATION_WORKFLOW.md']),
    'recheck': ('独立改后复核', [TEMPLATES+'企业书独立审阅任务.md', 'WRITING_STANDARD.md']),
}
INPUT_LABELS = {
    'manuscript': '本次正文与版本', 'figures': '实际图像',
    'preceding_text': '读者实际可见前文', 'evidence': '原件及完整研究',
    'reviews': '既有意见及处理记录', 'work_map': '工作地图与接续',
}


def instructions(role):
    if role not in ROLES:
        raise ValueError('未知任务角色：'+str(role))
    title, files = ROLES[role]
    return dict(role=role, title=title, documents=[
        dict(path=name, body=(ROOT/name).read_text(encoding='utf-8')) for name in files
    ])


def prepare(spec):
    """Render an actual bounded assignment; first readers receive only reader-visible inputs."""
    role = spec.get('role')
    policy = instructions(role)
    required = ['company', 'question', 'scope', 'output', 'end_condition']
    missing = [key for key in required if not str(spec.get(key, '')).strip()]
    if missing:
        raise ValueError('任务尚缺：'+', '.join(missing))
    inputs = spec.get('inputs', {})
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError('请列出实际输入及版本')
    unknown = set(inputs) - INPUT_LABELS.keys()
    if unknown:
        raise ValueError('未知输入类别：'+', '.join(sorted(unknown)))
    if role == 'first_read':
        if set(inputs) - {'manuscript', 'figures', 'preceding_text'}:
            raise ValueError('首读只交正文、实际图片和读者可见前文；底稿、工作地图及旧意见留到后续核对')
        if not inputs.get('manuscript'):
            raise ValueError('首读须提供实际正文与版本')
    if role == 'recheck' and (not inputs.get('manuscript') or not inputs.get('reviews')):
        raise ValueError('复核须提供实际修订稿及原意见；不能只看作者回复')
    lines = [f'# {policy["title"]}：{spec["company"]}', '',
             f'完整问题：{spec["question"]}', f'本次范围：{spec["scope"]}',
             f'主要产出：{spec["output"]}', f'结束条件：{spec["end_condition"]}',
             '', '## 实际输入（按所列顺序阅读）', '']
    for key, entries in inputs.items():
        if not isinstance(entries, list) or any(not isinstance(x, str) or not x.strip() for x in entries):
            raise ValueError('输入类别须为路径或URL及明确版本的字符串列表：'+key)
        for entry in entries:
            lines.append(f'- {INPUT_LABELS[key]}：{entry}')
    lines += ['', '## 本次随附的现行标准', '',
              '以下为派发时从正式文件直接读取的全文。按本次角色和范围执行；模板中的其他模式留到相应任务。',
              '标准中的历史示例用于解释写法或方法，不作为本公司的事实或估值输入。',
              '保存本指令与实际产出到现有批次记录；收到标准不等于已经执行，程序生成不代表质量通过。', '']
    for doc in policy['documents']:
        lines += [f'### 来源：{doc["path"]}', '', doc['body'], '']
    return '\n'.join(lines)
