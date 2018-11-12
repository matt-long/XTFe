from __future__ import absolute_import, division, print_function

import os
from subprocess import call

import yaml
import importlib
from collections import OrderedDict

import numpy as np
import xarray as xr
import pandas as pd
import cftime

import calc

grid_file = '/glade/work/mclong/grids/pop-grid-g16.nc'
year_range_clim = slice(1964,2014)

dirf = './fig'
if not os.path.exists(dirf):
    call(['mkdir','-p',dirf])

dirt = '/glade/scratch/mclong/calcs/o2-prediction'
if not os.path.exists(dirt):
    call(['mkdir','-p',dirt])


xr_open_ds = {'chunks' : {'time':1},
              'decode_coords' : False,
              'decode_times' : False}
xr.set_options(enable_cftimeindex=True)

ypm = np.array([31,28,31,30,31,30,31,31,30,31,30,31])/365

#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def make_time(year_range):
    from itertools import product
    return [cftime.DatetimeNoLeap(year, month, 1) for year, month in
            product(range(year_range[0], year_range[1]+1), range(1, 13))]


#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def open_collection(base_dataset,
                    variables,
                    op,
                    isel_name='',
                    isel={},
                    clobber=False):


    if isel and not isel_name:
        raise ValueError('need isel_name with isel')

    operators = {'ann': calc.compute_ann_mean,
                 'monclim': calc.compute_mon_climatology,
                 'monanom': calc.compute_mon_anomaly}

    if isinstance(op,str) and op in operators:
        operator = operators[op]
    else:
        raise ValueError(f'{op} unknown')


    with open('collections.yml') as f:
        spec = yaml.load(f)

    if base_dataset not in spec:
        raise ValueError(f'Unknown dataset: {base_dataset}')

    spec = spec[base_dataset]
    data_mod = importlib.import_module(spec['source'])

    if operator:
        collection_file_base = f'{dirt}/{base_dataset}.{op}'
    else:
        collection_file_base = f'{dirt}/{base_dataset}'

    if isel:
        collection_file_base = f'{collection_file_base}.{isel_name}'

    ds = xr.Dataset()
    for v in variables:

        collection_file = f'{collection_file_base}.{v}.zarr'

        if clobber:
            call(['rm','-frv',collection_file])

        if os.path.exists(collection_file):
            print(f'reading {collection_file}')
            dsi = xr.open_zarr(collection_file,decode_times=False,decode_coords=False)

        else:
            dsm = data_mod.open_dataset(variable_list=v,**spec['open_dataset'])

            if isel:
                dsm = dsm.isel(**isel)

            dsi = operator(dsm)

            print(f'writing {collection_file}')
            dsi.to_zarr(collection_file)

        ds = xr.merge((ds,dsi))

    return ds

#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def region_box(ds=None):
    m = region_mask(ds,masked_area=False)
    if len(m.region) != 1:
        raise ValueError('Region > 1 not yet implemented')

    lat = np.concatenate((np.array([(m.where(m>0) * m.TLAT).min().values]),
                          np.array([(m.where(m>0) * m.TLAT).max().values])))
    lon = np.concatenate((np.array([(m.where(m>0) * m.TLONG).min().values]),
                          np.array([(m.where(m>0) * m.TLONG).max().values])))

    y = [lat[0], lat[0], lat[1], lat[1], lat[0]]
    x = [lon[0], lon[1], lon[1], lon[0], lon[0]]
    return x,y


#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def region_mask(ds=None,masked_area=True):
    if ds is None:
        ds = xr.open_dataset(grid_file,decode_coords=False)
    TLAT = ds.TLAT
    TLONG = ds.TLONG
    KMT = ds.KMT
    TAREA = ds.TAREA

    nj,ni = KMT.shape

    #-- define the mask logic
    M = xr.DataArray(np.ones(KMT.shape),dims=('nlat','nlon'))
    region_defs = OrderedDict([
        ( 'CalCOFI', M.where((25 <= TLAT) & (TLAT <= 38) &
                             (360-126<=TLONG) & (TLONG <= 360-115)) )
        ])

    #-- do things different if z_t is present
    if 'z_t' not in ds.variables:
        mask3d = xr.DataArray(np.ones(((len(region_defs),)+KMT.shape)),
                    dims=('region','nlat','nlon'),
                    coords={'region':list(region_defs.keys()),
                            'TLAT':TLAT,
                            'TLONG':TLONG})
        for i,mask_logic in enumerate(region_defs.values()):
            mask3d.values[i,:,:] = mask_logic.fillna(0.)
        mask3d = mask3d.where(KMT>0)

    else:
        z_t = ds.z_t
        nk = len(z_t)
        ONES = xr.DataArray(np.ones((nk,nj,ni)),dims=('z_t','nlat','nlon'),coords={'z_t':z_t})
        K = xr.DataArray(np.arange(0,len(z_t)),dims=('z_t'))
        MASK = K * ONES
        MASK = MASK.where(MASK <= KMT-1)
        MASK.values = np.where(MASK.notnull(),1.,0.)

        mask3d = xr.DataArray(np.ones(((len(region_defs),)+z_t.shape+KMT.shape)),
                            dims=('region','z_t','nlat','nlon'),
                            coords={'region':list(region_defs.keys()),
                                    'TLAT':TLAT,
                                    'TLONG':TLONG})

        for i,mask_logic in enumerate(region_defs.values()):
            mask3d.values[i,:,:,:] = ONES * mask_logic.fillna(0.)
        mask3d = mask3d.where(MASK==1.)

    if masked_area:
        area_total = (mask3d * TAREA).sum(['nlat','nlon'])
        mask3d = (mask3d * TAREA) / area_total.where(area_total > 0)
        for i in range(len(region_defs)):
            valid = mask3d.isel(region=i).sum(['nlat','nlon'])
            valid = valid.where(valid>0)
            #np.testing.assert_allclose(valid[~np.isnan(valid)],np.ones(len(z_t))[~np.isnan(valid)])

    return mask3d

#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def regional_mean(ds,masked_weights=None,mask_z_level=0.):
    if masked_weights is None:
        masked_weights = region_mask(ds,masked_area=True)

    save_attrs = {v:ds[v].attrs for v in ds.variables}

    dsr = xr.Dataset()


    valid = masked_weights.sum(['nlat','nlon'])
    if 'z_t' in ds.variables:
        validk = valid.sel(z_t=mask_z_level,method='nearest')

    for v in ds.variables:
        if ds[v].dims[-2:] == ('nlat','nlon'):
            if 'z_t' in ds[v].dims or 'z_t' not in ds.variables:
                dsr[v] = (ds[v] * masked_weights).sum(['nlat','nlon']).where(valid>0)
            else:
                dsr[v] = (ds[v] * masked_weights.sel(z_t=mask_z_level,method='nearest')).sum(['nlat','nlon']).where(validk>0)
            dsr[v].attrs = save_attrs[v]
        else:
            dsr[v] = ds[v]

    return dsr

#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def xcorr(x,y,dim=None):
    valid = (x.notnull() & y.notnull())
    N = valid.sum(dim=dim)

    x = x.where(valid)
    y = y.where(valid)
    x_dev = x - x.mean(dim=dim)
    y_dev = y - y.mean(dim=dim)

    cov = (x_dev * y_dev).sum(dim=dim) / N
    covx = (x_dev ** 2).sum(dim=dim) / N
    covy = (y_dev ** 2).sum(dim=dim) / N
    return ( cov / np.sqrt(covx * covy) )


#------------------------------------------------------------------------------------
#-- function
#------------------------------------------------------------------------------------

def rmsd(x,y,dim=None):
    valid = (x.notnull() & y.notnull())
    N = valid.sum(dim=dim)
    return np.sqrt(((x-y)**2).sum(dim=dim) / N )
