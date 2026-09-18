"""Independent topology expansion; never uses uploaded occupancy or cached spans."""
def chains(dataset):
    tables = dataset['tables']
    result = {}
    for line in sorted(r['line_code'] for r in tables['lines']):
        stations = sorted((r for r in tables['stations'] if r['line_code']==line), key=lambda r:r['seq'])
        sectors = {r['from_station_id']: r['sector_id'] for r in tables['sectors'] if r['line_code']==line}
        for bound in ('EB', 'WB'):
            chain = []
            for station in stations:
                sid = station['station_id']
                chain.append(f'PLAT:{line}:{sid}:{bound}')
                if sid in sectors:
                    chain.append(f'{sectors[sid]}:{bound}')
            result[line, bound] = chain
    return result

def opposite(location):
    stem, bound = location.rsplit(':', 1)
    return stem + (':WB' if bound=='EB' else ':EB')

def expand(activity, project, network):
    _, line, _, bound = activity['start_location_id'].split(':')
    chain = network[line, bound]
    lo, hi = sorted((chain.index(activity['start_location_id']), chain.index(activity['end_location_id'])))
    if chain[lo].startswith('SEC:'): lo -= 1
    if chain[hi].startswith('SEC:'): hi += 1
    occupied = set(chain[lo:hi+1])
    nature = project['nature_of_activity']
    radius = {'Live':2, 'Non-live (Consist)':1, 'Non-live (Others)':0}[nature]
    own = set(chain[max(0, lo-2*radius):min(len(chain), hi+2*radius+1)])
    mirror = {opposite(loc) for loc in own} if nature=='Live' else set()
    cross = set()
    hubs = {f'PLAT:{line}:H01:{bound}', f'PLAT:{line}:H02:{bound}', f'SEC:{line}:H01_H02:{bound}'}
    if nature=='Live' and own & hubs:
        other = 'BET' if line=='ALP' else 'ALP'
        cross = {f'{stem}:{other}:{location}:{b}' for b in ('EB', 'WB')
                 for stem, location in (('PLAT','H01'), ('PLAT','H02'), ('SEC','H01_H02'))}
    return {'occupied':occupied, 'buffer':own-occupied, 'opposite':mirror,
            'interchange':cross, 'closure':own | mirror | cross,
            'lines':{loc.split(':')[1] for loc in own | mirror | cross}}
