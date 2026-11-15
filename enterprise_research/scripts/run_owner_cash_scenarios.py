#!/usr/bin/env python3
"""Run an explicit research scenario file without writing company records."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from owner_cash_scenarios import calculate, render_markdown
import layered_owner_cash

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--markdown', required=True, type=Path)
    args = p.parse_args()
    inputs = json.loads(args.input.read_text())
    if inputs.get('method') == layered_owner_cash.METHOD:
        calculate, render_markdown = layered_owner_cash.calculate, layered_owner_cash.render_markdown
    result = calculate(inputs)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    args.markdown.write_text(render_markdown(result))
    print(json.dumps({'result':str(args.output), 'method':result['kind'], 'status':result['assumption_status']},ensure_ascii=False))
