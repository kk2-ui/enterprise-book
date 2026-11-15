#!/usr/bin/env python3
"""Command entry point; implementation belongs to source_data."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_data.disclosures import *

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = extract_manifest(json.loads(args.manifest.read_text()), args.manifest.resolve().parent)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f"Extracted {len(result['rows'])} declared rows to {args.output}")
