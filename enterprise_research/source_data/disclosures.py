#!/usr/bin/env python3
"""Extract declared rows from layout-preserved disclosures, retaining page evidence.

The manifest chooses the statement, columns and row, never an accounting meaning.
Missing/ambiguous rows fail rather than silently becoming zero or another period.
Wrapped labels can include a declared number of following lines.
"""
import argparse
import json
import re
from decimal import Decimal
from pathlib import Path

AMOUNT = re.compile(r"(?<![\d.])-?\d[\d,]*\.\d{2}(?!\d)")
FINANCIAL_AMOUNT = re.compile(r"(?<![\w.])(?:\(-?\d[\d,]*(?:\.\d+)?\)|-?\d[\d,]*(?:\.\d+)?)(?![\w.])")


def amount_matches(excerpt, spec):
    """Read the declared table format; a dash is never silently converted to zero."""
    fmt = spec.get('number_format', 'decimal_2')
    if fmt not in {'decimal_2', 'financial'}:
        raise ValueError('未知数字格式：'+fmt)
    matches = list((FINANCIAL_AMOUNT if fmt == 'financial' else AMOUNT).finditer(excerpt))
    return matches[spec.get('skip_amounts', 0):]


def decimal_amount(value):
    value = value.replace(',', '')
    if value.startswith('(') and value.endswith(')'):
        value = '-'+value[1:-1]
    return Decimal(value)


def extract_row(pages, spec):
    matches = []
    for number in spec['pages']:
        lines = pages[number - 1].splitlines()
        for i, line in enumerate(lines):
            if re.search(spec['pattern'], line.strip()):
                excerpt = '\n'.join(lines[i:i + 1 + spec.get('following_lines', 0)])
                matches.append((number, excerpt))
    if 'occurrence' in spec:
        matches = matches[spec['occurrence']:spec['occurrence'] + 1]
    if len(matches) != 1:
        raise ValueError(f"{spec['id']}: expected one row, found {len(matches)}")
    number, excerpt = matches[0]
    values = [m.group() for m in amount_matches(excerpt, spec)]
    if len(values) != len(spec['columns']):
        raise ValueError(f"{spec['id']}: {len(values)} amounts for {len(spec['columns'])} columns: {excerpt}")
    return dict(spec, pdf_page=number, source_excerpt=excerpt,
                values={key: str(decimal_amount(value)) for key, value in zip(spec['columns'], values)})


def extract_manifest(manifest, directory):
    rows = []
    for source in manifest['sources']:
        path = (directory / source['text_path']).resolve()
        pages = path.read_text().split('\f')
        for spec in source['rows']:
            row = extract_row(pages, spec)
            row.update(document=source['id'], text_path=str(path),
                       unit=spec.get('unit', source['unit']), scope=spec.get('scope', source['scope']))
            rows.append(row)
    return dict(as_of=manifest['as_of'], rows=rows)


