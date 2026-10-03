"""Validate and compile sparse lake/river beds and integer water levels."""
from pathlib import Path
import struct
import numpy as np

def load_water(path, meta):
    with np.load(path, allow_pickle=False) as data:
        arrays={k:np.asarray(data[k]) for k in ('x','y','bed','water')}
    n=arrays['x'].size
    if not n or any(a.ndim!=1 or a.size!=n for a in arrays.values()):
        raise ValueError('Water arrays must be nonempty, equally sized 1D arrays')
    if any(not np.all(np.isfinite(a)) for a in arrays.values()):
        raise ValueError('Water data must be finite')
    for k in ('x','y','water'):
        if not np.all(arrays[k]==np.floor(arrays[k])):
            raise ValueError(f'{k} must contain integers')
        if np.any(arrays[k]<-2147483648) or np.any(arrays[k]>2147483647):
            raise ValueError(f'{k} outside signed integer range')
        arrays[k]=arrays[k].astype(np.int32)
    x,y=arrays['x']-meta['x'],arrays['y']-meta['y']
    if np.any(x<0) or np.any(y<0) or np.any(x>=meta['width']) or np.any(y>=meta['height']):
        raise ValueError('Water coordinates outside dimension')
    if np.unique(y.astype(np.int64)*meta['width']+x).size!=n:
        raise ValueError('Duplicate water coordinates')
    bed=arrays['bed'].astype(np.float32)
    water=arrays['water']
    if np.any(bed<meta['min_height']) or np.any(water>=meta['max_height']) or np.any(water<meta['min_height']+1):
        raise ValueError('Water/bed outside build limits')
    if np.any(np.floor(bed)>=water):
        raise ValueError('Every water cell must have its bed below its water level')
    arrays['bed']=bed
    return arrays

def write_water(path, data):
    records=np.empty(len(data['x']),dtype=[('x','>i4'),('y','>i4'),('bed','>f4'),('water','>i4')])
    for k in data:records[k]=data[k]
    with Path(path).open('wb') as stream:
        stream.write(struct.pack('>5si',b'WPHY1',len(records)))
        records.tofile(stream)
