import argparse
import json
from pathlib import Path
from . import notifications
from . import spool
from .store import connect,run,replay,allrows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['cover','agent','blind','demo','report','replay','spool','notifications'])
    parser.add_argument('--db',default='demo.sqlite')
    parser.add_argument('--fixture')
    args=parser.parse_args()
    if args.command=='replay':
        result=replay(args.db)
    else:
        db=connect(args.db)
        if args.command=='notifications':
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

