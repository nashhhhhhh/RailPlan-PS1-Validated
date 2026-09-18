"""Offline solve of the bundled public instance (or an eight-CSV input folder)."""
import argparse
from pathlib import Path
from app.ps1 import parse_instance, load_files
from .contracts import OptimiseInput
from .service import optimise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New directory; existing directories are never overwritten')
    parser.add_argument('--input',type=Path,help='Directory containing exactly eight input CSVs')
    parser.add_argument('--options',type=Path,help='OptimiseInput JSON with bounds, locks and/or baseline')
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output directory already exists')
    options=OptimiseInput.model_validate_json(args.options.read_text()) if args.options else OptimiseInput()
    files={p.name:p.read_text(encoding='utf-8') for p in args.input.glob('*.csv')} if args.input else load_files()
    result=optimise(parse_instance(files),options)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'report.json').write_text(result.model_dump_json(indent=2)+'\n',encoding='utf-8')
    if result.publishable:
        for name,content in result.submission_files.items(): (args.output/name).write_text(content,encoding='utf-8',newline='')
    print(f'{result.solver_status}: publishable={result.publishable}; judge_validation=not_run; score_verification=internal_only')
    return 0 if result.publishable else 2

if __name__=='__main__':
    raise SystemExit(main())
