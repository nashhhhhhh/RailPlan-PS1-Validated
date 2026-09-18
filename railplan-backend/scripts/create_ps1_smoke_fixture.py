"""Create a labelled one-activity PS1 fixture; never edit organiser source files."""
import argparse
import csv
import io
from pathlib import Path
from app.ps1 import load_files,parse_instance

def files():
    source=load_files()
    def rows(name):return list(csv.DictReader(io.StringIO(source[name])))
    def replace(name,data):
        header=next(csv.reader(io.StringIO(source[name])))
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=header,lineterminator='\n')
        writer.writeheader();writer.writerows(data);source[name]=stream.getvalue()
    p=rows('07_PROJECT_DETAILS.csv')[5]
    p.update(nature_of_activity='Non-live (Others)',access_type='C',contract_priority=3,
        planned_completion_date='2027-01-10',number_of_workfronts=1,number_of_maximum_access_per_week=3)
    a=rows('08_ACTIVITY_DETAILS.csv')[0]
    a.update(activity_id='SMOKE-A1',contract_number=p['contract_number'],activity_type=p['activity_type'],
        start_location_id='SEC:ALP:S01_S02:EB',end_location_id='SEC:ALP:S01_S02:EB',total_accesses=1,
        planned_start_date='2027-01-04',predecessor_activity_id='',activity_priority=1)
    replace('07_PROJECT_DETAILS.csv',[p]);replace('08_ACTIVITY_DETAILS.csv',[a])
    replace('06_PARAMETERS.csv',[{'key':'horizon_start','value':'2027-01-04'},{'key':'horizon_weeks','value':4}])
    parse_instance(source)
    return source

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    for name,content in files().items():(args.output/name).write_text(content,encoding='utf-8',newline='')
    print('Created synthetic one-activity smoke fixture. This is not the organiser dataset.')

if __name__=='__main__':main()
