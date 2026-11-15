#!/usr/bin/env python3
"""Prepare one role's assignment with current canonical standards; never overwrite a dispatch."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editorial_tasks import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path, help='本次任务 JSON，格式见 MODEL_BOOKS.md')
    parser.add_argument('--output', type=Path, required=True, help='保存到已有研究批次内的新文件')
    args = parser.parse_args()
    body = prepare(json.loads(args.spec.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as target:
        target.write(body)
    print(args.output.resolve())


if __name__ == '__main__':
    main()
