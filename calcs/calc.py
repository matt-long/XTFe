#! /usr/bin/env python
from __future__ import absolute_import, division, print_function
import xarray as xr
import numpy as np
import cftime

xr_open_ds = {'chunks' : {'time':1},
              'decode_coords' : False,
              'decode_times' : False,
              'data_vars' : 'minimal'}

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------
def _list_to_indexer(index_list):
    '''
    .. function:: _list_to_indexer(index_list)

    Convert string formatted as: dimname,start[,stop[,stride]]
    to index (for the case where only 'start' is provided)
    or indexing object (slice).

    :param index_list: index list as passed in from
                       --isel dimname:start,stop,stride

    :returns: dict -- {dimname: indexing object}
    '''

    if len(index_list) == 1:
        return index_list[0]
    elif len(index_list) == 2:
        return slice(index_list[0],index_list[1])
    elif len(index_list) == 3:
        return slice(index_list[0],index_list[1],index_list[2])
    else:
        raise ValueError('illformed dimension subset')


#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def time_bound_var(ds):
    tb_name = ''
    if 'bounds' in ds['time'].attrs:
        tb_name = ds['time'].attrs['bounds']
    elif 'time_bound' in ds:
        tb_name = 'time_bound'
    else:
        raise ValueError('No time_bound variable found')
    tb_dim = ds[tb_name].dims[1]
    return tb_name,tb_dim

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def compute_mon_climatology(dsm):
    '''Compute a monthly climatology'''

    tb_name,tb_dim = time_bound_var(dsm)

    grid_vars = [v for v in dsm.variables if 'time' not in dsm[v].dims]
    variables = [v for v in dsm.variables if 'time' in dsm[v].dims and v not in ['time',tb_name]]

    # save attrs
    attrs = {v:dsm[v].attrs for v in dsm.variables}
    encoding = {v:{key:val for key,val in dsm[v].encoding.items()
                   if key in ['dtype','_FillValue','missing_value']}
                for v in dsm.variables}

    #-- compute time variable
    date = cftime.num2date(dsm[tb_name].mean(tb_dim),
                           units = dsm.time.attrs['units'],
                           calendar = dsm.time.attrs['calendar'])
    dsm.time.values = date
    if len(date)%12 != 0:
        raise ValueError('Time axis not evenly divisible by 12!')

    #-- compute climatology
    ds = dsm.drop(grid_vars).groupby('time.month').mean('time').rename({'month':'time'})

    #-- put grid_vars back
    ds = xr.merge((ds,dsm.drop([v for v in dsm.variables if v not in grid_vars])))

    attrs['time'] = {'long_name':'Month','units':'month'}
    del encoding['time']

    # put the attributes back
    for v in ds.variables:
        ds[v].attrs = attrs[v]

    # put the encoding back
    for v in ds.variables:
        if v in encoding:
            ds[v].encoding = encoding[v]

    return ds

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def compute_mon_anomaly(dsm):
    '''Compute a monthly anomaly'''

    tb_name,tb_dim = time_bound_var(dsm)

    grid_vars = [v for v in dsm.variables if 'time' not in dsm[v].dims]
    variables = [v for v in dsm.variables if 'time' in dsm[v].dims and v not in ['time',tb_name]]

    # save attrs
    attrs = {v:dsm[v].attrs for v in dsm.variables}
    coords = {v:dsm[v].attrs for v in dsm.variables}
    encoding = {v:{key:val for key,val in dsm[v].encoding.items()
                   if key in ['dtype','_FillValue','missing_value']}
                for v in dsm.variables}

    #-- compute time variable
    time_values_orig = dsm.time.values
    date = cftime.num2date(dsm[tb_name].mean(tb_dim),
                           units = dsm.time.attrs['units'],
                           calendar = dsm.time.attrs['calendar'])
    dsm.time.values = date
    if len(date)%12 != 0:
        raise ValueError('Time axis not evenly divisible by 12!')

    #-- compute anomaly
    ds = dsm.drop(grid_vars).groupby('time.month') - dsm.drop(grid_vars).groupby('time.month').mean('time')
    ds.reset_coords('month',inplace=True)

    #-- put grid_vars back
    ds = xr.merge((ds,dsm.drop([v for v in dsm.variables if v not in grid_vars])))
    ds.time.values = time_values_orig

    attrs['month'] = {'long_name':'Month'}

    # put the attributes back
    for v in ds.variables:
        ds[v].attrs = attrs[v]

    # put the encoding back
    for v in ds.variables:
        if v in encoding:
            ds[v].encoding = encoding[v]

    return ds

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def compute_ann_mean(dsm):
    '''Compute an annual mean'''
    tb_name,tb_dim = time_bound_var(dsm)

    grid_vars = [v for v in dsm.variables if 'time' not in dsm[v].dims]
    variables = [v for v in dsm.variables if 'time' in dsm[v].dims and v not in ['time',tb_name]]

    # save attrs
    attrs = {v:dsm[v].attrs for v in dsm.variables}
    encoding = {v:{key:val for key,val in dsm[v].encoding.items()
                   if key in ['dtype','_FillValue','missing_value']}
                for v in dsm.variables}

    #-- compute time variable
    date = cftime.num2date(dsm[tb_name].mean(tb_dim),
                           units = dsm.time.attrs['units'],
                           calendar = dsm.time.attrs['calendar'])
    dsm.time.values = date
    if len(date)%12 != 0:
        raise ValueError('Time axis not evenly divisible by 12!')
    nyr = len(date)/12

    #-- compute weights
    dt = dsm[tb_name].diff(dim=tb_dim)[:,0]
    wgt = dt.groupby('time.year')/dt.groupby('time.year').sum()
    np.testing.assert_allclose(wgt.groupby('time.year').sum(),1.)

    # groupby.sum() does not seem to handle missing values correctly: yields 0 not nan
    # the groupby.mean() does return nans, so create a mask of valid values for each variable
    valid = {v : dsm[v].groupby('time.year').mean(dim='time').notnull().rename({'year':'time'}) for v in variables}
    ones = dsm.drop(grid_vars).where(dsm.isnull()).fillna(1.).where(dsm.notnull()).fillna(0.)

    # compute the annual means
    ds = (dsm.drop(grid_vars) * wgt).groupby('time.year').sum('time').rename({'year':'time'},inplace=True)
    ones_out = (ones * wgt).groupby('time.year').sum('time').rename({'year':'time'},inplace=True)
    ones_out = ones_out.where(ones_out>0.)

    # renormalize to appropriately account for missing values
    ds = ds / ones_out

    # put the grid variables back
    ds = xr.merge((ds,dsm.drop([v for v in dsm.variables if v not in grid_vars])))

    # apply the valid-values mask
    for v in variables:
        ds[v] = ds[v].where(valid[v])

    # put the attributes back
    for v in ds.variables:
        ds[v].attrs = attrs[v]

    # put the encoding back
    for v in ds.variables:
        ds[v].encoding = encoding[v]

    return ds

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def compute_diff_wrt_reference(ds_list,ds_ref):
    ds_list_out = []
    for ds in ds_list:
        ds_list_out.append(ds-ds_ref)
    return ds_list_out

#-------------------------------------------------------------------------------
#-- main
#-------------------------------------------------------------------------------

if __name__ == '__main__':
    import os
    from subprocess import call

    import argparse
    import sys

    #---------------------------------------------------------------------------
    #-- parse args
    p = argparse.ArgumentParser(description='Process timeseries files.')

    p.add_argument('file_in',
                   type = lambda kv: kv.split(','))

    p.add_argument('file_out',
                   type = str)
    p.add_argument('--op', dest = 'operation',
                   required = True,
                   help = 'Specify operation')

    p.add_argument('-v', dest = 'variable_list',
                   default = [],
                   required = False,
                   help = 'variable list')

    p.add_argument('-x', dest = 'invert_var_selction',
                   action = 'store_true',
                   required = False,
                   help = 'invert variable list')

    p.add_argument('-O', dest = 'overwrite',
                   required = False,
                   action ='store_true',
                   help = 'overwrite')

    p.add_argument('--verbose', dest = 'verbose',
                   required = False,
                   action ='store_true',
                   help = 'Verbose')

    p.add_argument('--isel', dest = 'isel',
                   required = False,
                   default=[],
                   action = 'append',
                   help = 'subsetting mechanism "isel"')

    p.add_argument('--pbs-cluster', dest = 'pbs_cluster',
                   required = False,
                   action ='store_true',
                   help = 'do PBS cluster')

    p.add_argument('--pbs-spec', dest = 'pbs_spec',
                   type = lambda csv: {kv.split('=')[0]:kv.split('=')[1] for kv in csv.split(',')},
                   required = False,
                   default = {},
                   help = 'PBS cluster specifications')

    args = p.parse_args()

    #-- if the user has supplied a spec, assume pbs_cluster=True
    if args.pbs_spec:
        args.pbs_cluster = True

    #---------------------------------------------------------------------------
    #-- check output file existence and intentional overwrite
    if os.path.exists(args.file_out):
        if args.overwrite:
            call(['rm','-rfv',args.file_out])
        else:
            raise ValueError(f'{args.file_out} exists.  Use -O to overwrite.')

    #---------------------------------------------------------------------------
    #-- determine output format
    ext = os.path.splitext(args.file_out)[1]
    if ext == '.nc':
        write_output = lambda ds: ds.to_netcdf(args.file_out,unlimited_dims=['time'])
    elif ext == '.zarr':
        write_output = lambda ds: ds.to_zarr(args.file_out)
    else:
        raise ValueError('Unknown output file extension: {ext}')

    #---------------------------------------------------------------------------
    #-- set the operator
    if args.operation == 'annmean':
        operator = compute_ann_mean

    elif args.operation == 'monclim':
        operator = compute_mon_climatology

    elif args.operation == 'monanom':
        operator = compute_mon_anomaly
    else:
        raise ValueError(f'Unknown operation {args.operation}')

    #---------------------------------------------------------------------------
    #-- parse index
    isel = {}
    for dim_index in args.isel:
        dim = dim_index.split(',')[0]
        isel[dim] = _list_to_indexer([int(i) for i in dim_index.split(',')[1:]])

    #---------------------------------------------------------------------------
    #-- report args
    if args.verbose:
        print(f'\n{__file__}')
        for arg in vars(args):
            print(f'{arg}: {getattr(args, arg)}')
        print()

    #---------------------------------------------------------------------------
    #-- spin up dask cluster?
    if args.pbs_cluster:
        queue = args.pbs_spec.pop('queue','regular')
        project = args.pbs_spec.pop('project','NCGD0011')
        walltime = args.pbs_spec.pop('walltime','04:00:00')
        n_nodes = args.pbs_spec.pop('n_nodes',4)

        if args.pbs_spec:
            raise ValueError(f'Unknown fields in pbs_spec: {args.pbs_spec.keys()}')

        from dask.distributed import Client
        from dask_jobqueue import PBSCluster

        USER = os.environ['USER']

        cluster = PBSCluster(queue = queue,
                             cores = 36,
                             processes = 9,
                             memory = '100GB',
                             project = project,
                             walltime = walltime,
                             local_directory=f'/glade/scratch/{USER}/dask-tmp')
        client = Client(cluster)
        cluster.scale(9*n_nodes)

    #---------------------------------------------------------------------------
    #-- read the input dataset
    ds = xr.open_mfdataset(args.file_in,**xr_open_ds)
    if isel:
        ds = ds.isel(**isel)

    if args.variable_list:
        if args.invert_var_selction:
            drop_vars = [v for v in ds.variables if v in args.variable_list]
        else:
            drop_vars = [v for v in ds.variables if v not in args.variable_list]
        ds = ds.drop(drop_vars)

    if args.verbose:
        print('\ninput dateset:')
        ds.info()

    #---------------------------------------------------------------------------
    #-- compute
    if args.verbose:
        print(f'\ncomputing {args.operation}')

    dso = operator(ds)

    if args.verbose:
        print('\noutput dateset:')
        dso.info()

    #---------------------------------------------------------------------------
    #-- write output
    if args.verbose:
        print(f'\nwriting {args.file_out}')

    write_output(dso)

    #---------------------------------------------------------------------------
    #-- wrap up
    if args.pbs_cluster:
        cluster.close()

    if args.verbose:
        print('\ndone.')
