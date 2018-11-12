'''
.. module:: grid_tools

Tools for grids.
'''

import xarray as xr
import numpy as np
import logging

Re = 6.37122e6 # m
deg2rad = np.pi/180.

#------------------------------------------------------------------------
#-- FUNCTION
#------------------------------------------------------------------------

def compute_grid_area_lonlat(lon_in,lat_in):
    '''Compute the grid area on a regular lat x lon grid.'''

    if isinstance(lon_in,xr.DataArray):
        longitude = lon_in.values
    else:
        longitude = lon_in
        
    if isinstance(lat_in,xr.DataArray):        
        latitude = lat_in.values
    else:
        latitude = lat_in
        

    dx = np.diff(longitude)
    dy = np.diff(latitude)
    if not (dx == dx[0]).all():
        raise ValueError('dx must be constant')  
    if not np.allclose(dy,dy[0]):
        raise ValueError('dt must be constant')


    dx = dx[0]
    dy = dy[0]
    ny = latitude.shape[0]
    nx = longitude.shape[0]

    yc = np.broadcast_to(latitude[:,None],(ny,nx))
    xc = np.broadcast_to(longitude[None,:],(ny,nx))

    yv = np.stack((yc-dy/2.,yc-dy/2.,yc+dy/2.,yc+dy/2.),axis=2)
    xv = np.stack((xc-dx/2.,xc+dx/2.,xc+dx/2.,xc-dx/2.),axis=2)

    y0 = np.sin(yv[:,:,0]*deg2rad) # south
    y1 = np.sin(yv[:,:,3]*deg2rad) # north
    x0 = xv[:,:,0]*deg2rad         # west
    x1 = xv[:,:,1]*deg2rad         # east
    area = (y1-y0)*(x1-x0)*Re**2.

    logging.info('total area = %.16e'%np.sum(area))
    logging.info('check area = %.16e'%(4.*np.pi*Re**2.))


    area = xr.DataArray(area,dims=('lat','lon'))
    area.attrs['long_name'] = 'Cell area'
    area.attrs['units'] = 'm^2'
    if isinstance(lon_in,xr.DataArray) and isinstance(lat_in,xr.DataArray):
        area = area.assign_coords(**{lat_in.name:lat_in,lon_in.name:lon_in})                           
        
    return area

#------------------------------------------------------------------------
#-- FUNCTION
#------------------------------------------------------------------------

def generate_latlon_grid(nx,ny,lon0=0.,file_out=''):
    '''
    .. function:: generate_latlon_grid(nx,ny[,file_out=''])

    Generate a regular lat,lon grid file.

    :param nx: number of x points.

    :param ny: number of y points.

    :param file_out: optional output file.

    :returns: dataset with grid variables

    '''

    dx = 360./nx
    dy = 180./ny

    if file_out:
        print('dx = %.6f'%dx)
        print('dy = %.6f'%dy)

    lat = np.arange(-90.+dy/2.,90.,dy)
    lon = np.arange(lon0+dx/2.,lon0+360.,dx)

    yc = np.broadcast_to(lat[:,None],(ny,nx))
    xc = np.broadcast_to(lon[None,:],(ny,nx))

    yv = np.stack((yc-dy/2.,yc-dy/2.,yc+dy/2.,yc+dy/2.),axis=2)
    xv = np.stack((xc-dx/2.,xc+dx/2.,xc+dx/2.,xc-dx/2.),axis=2)

    y0 = np.sin(yv[:,:,0]*deg2rad) # south
    y1 = np.sin(yv[:,:,3]*deg2rad) # north
    x0 = xv[:,:,0]*deg2rad         # west
    x1 = xv[:,:,1]*deg2rad         # east
    area = (y1-y0)*(x1-x0)*Re**2.

    if file_out:
        print('total area = %.16e'%np.sum(area))
        print('check area = %.16e'%(4.*np.pi*Re**2.))

    ds = xr.Dataset(
        {'lat':xr.DataArray(lat,dims=('lat'),
                            attrs={'units':'degrees_north',
                                   'long_name':'Latitude'}),
         'lon':xr.DataArray(lon,dims=('lon'),
                            attrs={'units':'degrees_east',
                            'long_name':'Longitude'})})

    ds['xc'] = xr.DataArray(xc,dims=('lat','lon'),
                            attrs={'units':'degrees_east',
                                   'long_name':'longitude of cell centers'})

    ds['yc'] = xr.DataArray(yc,dims=('lat','lon'),
                            attrs={'units':'degrees_north',
                                   'long_name':'latitude of cell centers'})

    ds['xv'] = xr.DataArray(xv,dims=('lat','lon','nv'),
                            attrs={'units':'degrees_east',
                                   'long_name':'longitude of cell corners'})
    
    ds['yv'] = xr.DataArray(yv,dims=('lat','lon','nv'),
                            attrs={'units':'degrees_north',
                                   'long_name':'latitude of cell corners'})

    ds['area'] = xr.DataArray(area,dims=('lat','lon'),
                              attrs={'units':'m^2',
                                     'long_name':'area'})

    if file_out:
        ds.to_netcdf(file_out)

    return ds

#------------------------------------------------------------------------
#-- FUNCTION
#------------------------------------------------------------------------
def index_point_on_grid(plon,plat,xv,yv):
    '''determine if points are in grid cells
    '''
    ux = np.cos(np.deg2rad(xv)) * np.cos(np.deg2rad(yv))
    uy = np.sin(np.deg2rad(xv)) * np.cos(np.deg2rad(yv))
    uz = np.sin(np.deg2rad(yv))

    xp = np.cos(np.deg2rad(plon)) * np.cos(np.deg2rad(plat))
    yp = np.sin(np.deg2rad(plon)) * np.cos(np.deg2rad(plat))
    zp = np.sin(np.deg2rad(plat))

    xv1 = ux - xp
    yv1 = uy - yp
    zv1 = uz - zp

    xv2 = np.roll(ux,shift=-1,axis=2) - xp
    yv2 = np.roll(uy,shift=-1,axis=2) - yp
    zv2 = np.roll(uz,shift=-1,axis=2) - zp

    xpv = yv1 * zv2 - zv1 * yv2
    ypv = zv1 * xv2 - xv1 * zv2
    zpv = xv1 * yv2 - yv1 * xv2

    incell = (xpv * xp + ypv * yp + zpv * zp >= 0).all(axis=2)
    J,I = np.where(incell)

    if len(J) > 1:
        J = J[-1]
        I = I[-1]

    return J,I
