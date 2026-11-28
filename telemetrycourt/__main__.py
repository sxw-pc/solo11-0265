import argparse
import json
from pathlib import Path
from . import histogram, probe_review
from . import egress
from . import archive
from . import notifications
from . import spool
from .store import connect,run,replay,allrows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['cover','agent','blind','demo','report','replay','spool','notifications','archive','egress','histogram','probe-review','probe-formula'])
    parser.add_argument('--db',default='demo.sqlite')
    parser.add_argument('--fixture')
    parser.add_argument('--certificate')
    parser.add_argument('--reading')
    args=parser.parse_args()
    if args.command=='replay':
        result=replay(args.db)
    elif args.command=='probe-formula':
        if not args.fixture:
            parser.error('--fixture required')
        contract=json.loads(Path(args.fixture).read_text(encoding='utf-8'))
        if args.certificate:
            certificate=json.loads(Path(args.certificate).read_text(encoding='utf-8'))
            if args.reading:
                reading=json.loads(Path(args.reading).read_text(encoding='utf-8'))['reading']
            else:
                reading=contract.pop('reading', None)
                if reading is None:
                    parser.error('--reading required or embed a "reading" in the fixture')
            result=probe_review.run_certified(certificate,reading)
            if result['status']=='held_for_review':
                exit_code=3
            else:
                exit_code=0
        else:
            result=probe_review.issue(contract)
            exit_code=0 if result['status']=='signed' else 2
        print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
        raise SystemExit(exit_code)
    else:
        db=connect(args.db)
        if args.command=='probe-review':
            if not args.fixture:
                parser.error('--fixture required')
            result=probe_review.run(json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='histogram':
            if not args.fixture:
                parser.error('--fixture required')
            result=histogram.run(db,json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='egress':
            if not args.fixture:
                parser.error('--fixture required')
            result=egress.run(db,json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='archive':
            if not args.fixture:
                parser.error('--fixture required')
            result=archive.run(db,json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='notifications':
            if not args.fixture:parser.error('--fixture required')
            result=notifications.run(db,json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='spool':
            if not args.fixture:parser.error('--fixture required')
            result=spool.run(db,json.loads(Path(args.fixture).read_text(encoding='utf-8')))
        elif args.command=='report':result=allrows(db,'SELECT * FROM events ORDER BY seq')
        else:
            if args.command=='demo':
                files=[(sub,f'fixtures/{sub}_{kind}.json') for sub,kind in [('cover','normal'),('agent','normal'),('blind','normal'),('cover','failure'),('agent','failure'),('blind','failure')]]
            elif args.fixture:files=[(args.command,args.fixture)]
            else:parser.error('--fixture required')
            result=[{'fixture':file,'results':[run(db,sub,c) for c in json.loads(Path(file).read_text(encoding='utf-8'))]} for sub,file in files]
        db.close()
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    if args.command=='replay' and not result['verified']:raise SystemExit(2)

if __name__=='__main__':main()
