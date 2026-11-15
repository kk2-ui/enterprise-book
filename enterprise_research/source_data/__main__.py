"""python -m source_data --data-dir DIR collect|extract|package|list|validate ..."""
import argparse
import json
from pathlib import Path
from .repository import SourceRepository
from .acquisition import collect_document
from .disclosures import extract_manifest
from .packages import build_package, validate_package


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ['collect','extract','package']:
        p=sub.add_parser(command);p.add_argument('company_id');p.add_argument('manifest',type=Path)
    p=sub.add_parser('list');p.add_argument('company_id')
    p=sub.add_parser('validate');p.add_argument('directory',type=Path)
    args=parser.parse_args()
    if args.command=='validate':
        result=validate_package(args.directory)
    else:
        repo=SourceRepository(args.data_dir)
        if args.command=='list':result=repo.overview(args.company_id)
        else:
            spec=json.loads(args.manifest.read_text())
            if args.command=='collect':
                result=[]
                for entry in spec['documents']:
                    for key in ['local_path','text_path']:
                        if entry.get(key):entry[key]=str((args.manifest.resolve().parent/entry[key]).resolve())
                    r=collect_document(repo,args.company_id,entry,spec.get('acquired_on'))
                    result.append(dict(id=entry['id'],status=r['acquisition']['status'],error=r['acquisition'].get('error'),revision=(r['document'] or {}).get('revision')))
            elif args.command=='extract':
                # Resolve full text through the data registry, not through a report directory.
                sources=[]
                for source in spec['sources']:
                    doc=repo.document(args.company_id,source['id'],source.get('revision'))
                    source=dict(source,text_path=repo.source(doc['representations']['text'])['path'])
                    sources.append(source)
                extracted=extract_manifest(dict(spec,sources=sources),Path('/'))
                result=[]
                for source in sources:
                    doc=repo.document(args.company_id,source['id'],source.get('revision'))
                    rows=[{k:v for k,v in r.items() if k!='text_path'} for r in extracted['rows'] if r['document']==source['id']]
                    doc.update(rows=rows,periods=source.get('periods',{}),extraction_status='declared_rows')
                    saved=repo.save_document(args.company_id,doc)
                    result.append(dict(id=saved['id'],revision=saved['revision'],rows=len(rows)))
            else:
                result=build_package(repo,args.company_id,spec)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
