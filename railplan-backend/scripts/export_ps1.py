"""Rebuild the public preview from the exact bundled eight CSV input files."""
import json
import shutil
from pathlib import Path
from app.ps1 import load_files,parse_instance

def main():
    root=Path(__file__).resolve().parents[1]
    target=root.parent/'public/ps1'
    target.mkdir(parents=True,exist_ok=True)
    files=load_files();dataset=parse_instance(files)
    (target/'example.json').write_text(json.dumps({'name':'Organiser PS1 public instance','files':files,'dataset':dataset},indent=2)+'\n')
    for name in ('SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv'):
        shutil.copyfile(root/'data/PS1/03_submission_sample'/name,target/name)
    shutil.copyfile(root/'data/PS1/02_references/network_diagram.svg',target/'network_diagram.svg')
    print(json.dumps(dataset['summary']))

if __name__=='__main__':main()
