#!/usr/bin/env python3
"""Command entry point; implementation belongs to source_data."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_data.acquisition import *

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('manifest', type=Path)
    p.add_argument('--retrieved-on', help='Date of this retrieval; separate from the facts and publication date')
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text()); directory = args.manifest.resolve().parent
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda x: acquire(x, directory, args.retrieved_on), manifest['sources']))
    out = directory / 'acquired_sources.json'
    out.write_text(json.dumps(dict(as_of=manifest['as_of'], sources=results), ensure_ascii=False, indent=2) + '\n')
    for x in results: print(x['id'], x['page_hits'])
