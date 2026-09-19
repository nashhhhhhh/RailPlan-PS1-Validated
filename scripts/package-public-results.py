"""Package only the accepted competition-submission tree."""
import argparse
from pathlib import Path
import zipfile

EXPECTED={
    'README.md','evidence/checksums.sha256',
    *(f'evidence/scenario-{scenario}.json' for scenario in 'abc'),
    *(f'scenario-{scenario}/{name}' for scenario in 'abc'
      for name in ('RESULTS.csv','SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv')),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--source',type=Path,default=Path('competition-submission'))
    args=parser.parse_args()
    files=sorted(path for path in args.source.rglob('*') if path.is_file())
    relative={path.relative_to(args.source).as_posix() for path in files}
    if relative!=EXPECTED:
        raise SystemExit(f'Unexpected public result tree: missing={sorted(EXPECTED-relative)}, extra={sorted(relative-EXPECTED)}')
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:archive.write(path,path.relative_to(args.source).as_posix())
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None or set(archive.namelist())!=EXPECTED:
            raise RuntimeError('Public result ZIP verification failed')
    print(f'Packaged {len(files)} public result files: {args.output} ({args.output.stat().st_size} bytes)')


if __name__=='__main__':main()
