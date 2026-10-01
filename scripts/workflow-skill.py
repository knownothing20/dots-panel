#!/usr/bin/env python3
"""Inspect/export bundled workflow source; never installs into an account."""
import argparse,json,sys
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from dots_panel.workflow_bundle import bundle_status,export_bundle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path,help='New ZIP outside the source tree; never overwrites')
    args=parser.parse_args()
    try:
        if args.export:
            path=export_bundle(SOURCE,args.export)
            print(json.dumps({'exported':str(path),'account_installation':'not_verified'}))
        else:
            print(json.dumps(bundle_status(SOURCE),ensure_ascii=False,indent=2))
    except (ValueError,OSError,UnicodeError) as error:
        parser.exit(1,f'Error: {error}\n')
if __name__=='__main__':main()
