"""Strict, bounded CSV parsing. No execution or spreadsheet interpretation."""
import csv
import io
import json
import re
from collections import Counter
from datetime import date
from hashlib import sha256
from .contracts import HEADERS, POLICY, violation

def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()

def parse_submission(files, scenario):
    errors, tables = [], {name: [] for name in HEADERS}
    def error(message, **evidence):
        errors.append(violation('schema', message, **evidence))
    if set(files) != set(HEADERS):
        error('Exactly three submission CSV files are required', missing=sorted(set(HEADERS)-set(files)), unexpected=sorted(set(files)-set(HEADERS)))
    try:
        size = sum(len(value.encode('utf-8')) for value in files.values())
    except UnicodeEncodeError:
        error('Invalid Unicode in submission')
        return tables, errors
    if size > POLICY.max_bytes:
        error('Submission exceeds 4 MB', bytes=size)
        return tables, errors
    for name, header in HEADERS.items():
        if name not in files:
            continue
        try:
            reader = csv.DictReader(io.StringIO(files[name].removeprefix('\ufeff')), strict=True)
            if reader.fieldnames != header.split(','):
                error('CSV headers must match exactly', file=name, expected=header, received=reader.fieldnames)
                continue
            for index, raw in enumerate(reader):
                if index >= POLICY.max_rows_per_file:
                    error('CSV row limit exceeded', file=name, limit=POLICY.max_rows_per_file)
                    break
                if None in raw or any(v is None for v in raw.values()):
                    error('CSV column count mismatch', file=name,
                          row={k if k is not None else '__extra_columns__':v for k,v in raw.items()})
                    continue
                row = {k: v.strip() for k, v in raw.items()}
                if any(not v or len(v)>256 or any(ord(c)<32 for c in v) for v in row.values()):
                    error('Missing or invalid cell', file=name, row=row)
                    continue
                valid = True
                for key in ('access_seq', 'week', 'eclo', 'access_night', 'overrun_days'):
                    if key not in row:
                        continue
                    minimum = 0 if key in ('eclo', 'overrun_days') else 1
                    maximum = 1 if key == 'eclo' else 100000
                    value = row[key]
                    if not re.fullmatch(r'[0-9]+', value) or not minimum <= int(value) <= maximum:
                        error('Invalid integer or ECLO value', file=name, field=key, value=value, row=row)
                        valid = False
                    else:
                        row[key] = int(value)
                if 'scenario' in row:
                    if row['scenario'] != scenario:
                        error('Mixed or mismatched scenario', file=name, expected=scenario, row=row)
                        valid = False
                    try:
                        value = row['simulated_completion_date']
                        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                            raise ValueError()
                        date.fromisoformat(value)
                    except ValueError:
                        error('Invalid ISO completion date', file=name, row=row)
                        valid = False
                if valid:
                    tables[name].append(row)
        except (csv.Error, ValueError) as exc:
            error('Malformed CSV', file=name, reason=str(exc))
        tables[name].sort(key=lambda r: json.dumps(r, sort_keys=True))
        keys = {'SCHEDULE_ACCESS.csv': ('activity_id', 'access_seq'),
                'SCHEDULE_OCCUPANCY.csv': ('activity_id', 'week', 'location_id'),
                'RESULTS.csv': ('contract_number',)}[name]
        counts = Counter(tuple(r[k] for k in keys) for r in tables[name])
        for key, count in sorted(counts.items()):
            if count > 1:
                ref = dict(zip(keys, key))
                errors.append(violation('duplicate', 'Duplicate logical records',
                    activities=[ref['activity_id']] if 'activity_id' in ref else [],
                    contracts=[ref['contract_number']] if 'contract_number' in ref else [],
                    week=ref.get('week'), locations=[ref['location_id']] if 'location_id' in ref else [],
                    file=name, key=ref, count=count))
    return tables, errors
