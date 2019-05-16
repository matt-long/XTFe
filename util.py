from functools import reduce

import numpy as np
import xarray as xr

molw_Fe = 55.845

kgm2s_to_molm2yr = 1e3 / molw_Fe * 86400. * 365.

def pop_add_cyclic(ds):
    
    nj = ds.TLAT.shape[0]
    ni = ds.TLONG.shape[1]

    xL = int(ni/2 - 1)
    xR = int(xL + ni)

    tlon = ds.TLONG.data
    tlat = ds.TLAT.data
    
    tlon = np.where(np.greater_equal(tlon, min(tlon[:,0])), tlon-360., tlon)    
    lon  = np.concatenate((tlon, tlon + 360.), 1)
    lon = lon[:, xL:xR]

    if ni == 320:
        lon[367:-3, 0] = lon[367:-3, 0] + 360.        
    lon = lon - 360.
    
    lon = np.hstack((lon, lon[:, 0:1] + 360.))
    if ni == 320:
        lon[367:, -1] = lon[367:, -1] - 360.

    #-- trick cartopy into doing the right thing:
    #   it gets confused when the cyclic coords are identical
    lon[:, 0] = lon[:, 0] - 1e-8

    #-- periodicity
    lat = np.concatenate((tlat, tlat), 1)
    lat = lat[:, xL:xR]
    lat = np.hstack((lat, lat[:,0:1]))

    TLAT = xr.DataArray(lat, dims=('nlat', 'nlon'))
    TLONG = xr.DataArray(lon, dims=('nlat', 'nlon'))
    
    dso = xr.Dataset({'TLAT': TLAT, 'TLONG': TLONG})

    # copy coords
    for v, da in ds.coords.items():
        if not ('nlat' in da.dims and 'nlon' in da.dims):
            dso = dso.assign_coords(**{v: da})
    
    # copy vars
    varlist = [v for v in ds.data_vars if v not in ['TLAT', 'TLONG']]
    for v in varlist:
        v_dims = set(ds[v].dims)
        if not ('nlat' in v_dims and 'nlon' in v_dims):
            dso[v] = ds[v]
        else:
            other_dims = tuple(v_dims - {'nlat', 'nlon'})
            lon_dim = ds[v].dims.index('nlon')
            field = ds[v].data
            field = np.concatenate((field, field), lon_dim)
            field = field[..., :, xL:xR]
            field = np.concatenate((field, field[..., :, 0:1]), lon_dim)       
            dso[v] = xr.DataArray(field, dims=other_dims+('nlat', 'nlon'), 
                                  attrs=ds[v].attrs)

    return dso


def label_map_axes(fig, axs):
    """Add letter in upper left of map axes."""
    alp = [chr(i).upper() for i in range(97,97+26)]
    for i,axi in enumerate(axs):
        p = axi.get_position()
        y = p.y1-0.03
        x = p.x0+0.03
        fig.text(x,y,'%s'%alp[i],
                 fontsize=12.,
                 fontweight = 'semibold')
        
def compute_grid_area(ds):

    Re = 6.37122e6 # m, radius of Earth

    # normalize area so that sum over 'lat', 'lon' yields area_earth
    area = ds.gw + 0.0 * ds.lon # add 'lon' dimension
    area = (4.0 * np.pi * Re**2 / area.sum(dim=('lat', 'lon'))) * area # m^2
    area.attrs['units'] = 'm^2'
    
    return area        

def set_coords(ds, data_vars):
    """Set all variables except varname to be coords."""
    coord_vars = set(ds.data_vars) - set(data_vars)
    return ds.set_coords(coord_vars)

def open_cesm_data(col, data_vars, time_slice=None):

    # experiment list
    explist = col.df.experiment.unique().tolist()
    experiment = xr.DataArray(explist, 
                              dims=('experiment'), 
                              coords={'experiment': explist}, 
                              name='experiment')

    # construct dataset
    ds_catlist = []
    for exp in experiment.values:
        ds_mergelist = []
        ds_data_vars = []
        for v in data_vars:
            cat_query = col.search(experiment=exp, variable=v)
            if len(cat_query.query_results) > 0:
                ds_data_vars.append(v)
                filename = cat_query.query_results.file_fullpath.tolist()
                
                ds = xr.open_mfdataset(filename, decode_times=False, 
                                       decode_coords=False)
                
                ds_mergelist.append(ds)

        ds_mergelist = [set_coords(ds, ds_data_vars) for ds in ds_mergelist]
        if len(ds_mergelist) == 1:
            ds_catlist.append(ds_mergelist[0])
        else:
            ds_catlist.append(xr.merge(ds_mergelist))

    
    ds_list = xr.align(*ds_catlist, join='inner')    
       
    common_vars = set(reduce(lambda ds1, ds2: set(ds1.data_vars) & set(ds2.data_vars),
                              ds_list))

    all_vars = set(reduce(lambda ds1, ds2: set(ds1.data_vars) | set(ds2.data_vars),
                              ds_list))

    missing_vars = [all_vars - set(ds.data_vars) for ds in ds_list]
    
    for exp, ds in zip(explist, ds_list):
        desc = col.search(experiment=exp).query_results.description.unique()[0]
        print(f'{exp}: {desc}')
        print(f'\tvars: {list(ds.data_vars)}')
    
    ds = xr.concat(ds_list, dim=experiment, data_vars=common_vars)

    ds = ds.esmlab.set_time('time').compute_time_var()
   
    if time_slice is not None:
        ds = ds.sel(time=time_slice)

    non_dim_coords_reset = set(ds.coords) - set(ds.dims)
    ds = ds.reset_coords(non_dim_coords_reset)
    
    ds['time_bound_diff'] = ds.time_bound.diff('d2')[:, 0] / 365.

    with xr.set_options(keep_attrs=True):
        if 'IRON_FLUX' in ds.variables:
            ds['IRON_FLUX'] = ds.IRON_FLUX * 86400. * 365. * 1e-3
            ds.IRON_FLUX.attrs['units'] = 'mol m$^{-2}$ yr$^{-1}$'

        if 'photoC_TOT_zint' in ds.variables:
            ds['photoC_TOT_zint'] = ds.photoC_TOT_zint * 86400. * 365. * 1e-9 * 1e4
            ds.photoC_TOT_zint.attrs['units'] = 'mol m$^{-2}$ yr$^{-1}$'

        if 'Jint_100m_DIC' in ds.variables:
            ds['NCP'] = (-1.0) * ds.Jint_100m_DIC * 86400. * 365. * 1e-9 * 1e4
            ds.NCP.attrs['units'] = 'mol m$^{-2}$ yr$^{-1}$'

        if 'ATM_XTFE_FLUX_CPL' in ds.variables:
            ds['ATM_XTFE_FLUX_CPL'] = ds.ATM_XTFE_FLUX_CPL / molw_Fe * 1e4 * 86400. * 365.
            ds.ATM_XTFE_FLUX_CPL.attrs['units'] = 'mol m$^{-2}$ yr$^{-1}$'

        if 'SEAICE_XTFE_FLUX_CPL' in ds.variables:
            ds['SEAICE_XTFE_FLUX_CPL'] = ds.SEAICE_XTFE_FLUX_CPL / molw_Fe * 1e4 * 86400. * 365.
            ds.SEAICE_XTFE_FLUX_CPL.attrs['units'] = 'mol m$^{-2}$ yr$^{-1}$'

    return ds