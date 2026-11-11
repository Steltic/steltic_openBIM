"""Local flange recesses and gradual W-shape transitions on a continuous member."""
import math


KEYS=('d','bf','tf','tw')


def check_intervals(rows,extent):
    previous=0.
    for row in sorted(rows,key=lambda r:r['start_in']):
        lo,hi=row['start_in'],row['end_in']
        if not (math.isfinite(lo) and math.isfinite(hi) and lo>=previous-1e-6 and hi>lo and hi<=extent+1e-6):
            raise ValueError('Fabricated section interval lies outside its member or overlaps another interval')
        for shape in (row['start_dimensions'],row['end_dimensions']):
            if not all(math.isfinite(shape[k]) and shape[k]>0. for k in KEYS) or 2*shape['tf']>=shape['d'] or shape['tw']>=shape['bf']:
                raise ValueError('Invalid fabricated wide-flange section')
        previous=hi


def interpolate(row,station):
    fraction=(station-row['start_in'])/(row['end_in']-row['start_in'])
    return {k:row['start_dimensions'][k]*(1.-fraction)+row['end_dimensions'][k]*fraction for k in KEYS}


def cropped(rows,start,finish):
    """Return source sections between two detail stations, including reverse views."""
    result=[]
    for row in rows:
        lo=max(min(start,finish),row['start_in']);hi=min(max(start,finish),row['end_in'])
        if hi<=lo+1e-7:continue
        first,last=(lo,hi) if start<finish else (hi,lo)
        result.append(dict(row,start_in=abs(first-start),end_in=abs(last-start),
                           start_dimensions=interpolate(row,first),end_dimensions=interpolate(row,last)))
    return sorted(result,key=lambda r:r['start_in'])
