from glob import glob
import xarray as xr
import logging

xr_open_ds = {'decode_coords' : False,
              'decode_times' : False,
              'data_vars' : 'minimal'}

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def _glob_list_files(glob_pattern,error_if_nofiles=True):
    '''Glob for files and check that some were found.'''

    logging.debug(f'glob file search: {glob_pattern}')

    files = sorted(glob(glob_pattern))
    if not files:
        if error_if_nofiles:
            raise ValueError(f'No files: {glob_pattern}')
        else:
            logging.warning(f'No files: {glob_pattern}')

    return files

#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def open_dataset(format,**kwargs):

    '''Open dataset from CESM output.

    There are two formats:
    - multi_variable:
        - if variable_list has been specified, drop extraneous variables

    - single_variable:
        - require variable_list, merge all variables into dataset
    '''

    #-- parse input arguments
    dirin = kwargs.pop('dirin')
    case = kwargs.pop('case')
    stream = kwargs.pop('stream')
    datestr = kwargs.pop('datestr')

    variable_list = kwargs.pop('variable_list', [])

    if kwargs:
        raise ValueError(f'Unknown argument: {kwargs}')

    if isinstance(variable_list,str):
        variable_list = [variable_list]

    if format == 'hist':

        file_name_pattern = f'{dirin}/{case}.{stream}.{datestr}.nc'
        files = _glob_list_files(file_name_pattern)

        logging.debug(f'Opening {len(files)} files: {files[0]}...{files[-1]}')

        ds = xr.open_mfdataset(files,**xr_open_ds)

        tb_name = ''
        if 'bounds' in ds['time'].attrs:
            tb_name = ds['time'].attrs['bounds']
        elif 'time_bound' in ds:
            tb_name = 'time_bound'

        if variable_list:

            static_vars = [v for v,da in ds.variables.items()
                           if 'time' not in da.dims]
            logging.debug(f'static vars: {static_vars}')

            keep_vars = ['time',tb_name]+variable_list+static_vars
            logging.debug(f'keep vars: {keep_vars}')

            drop_vars = [v for v,da in ds.variables.items()
                         if 'time' in da.dims and v not in keep_vars]

            logging.debug(f'dropping vars: {drop_vars}')
            ds = ds.drop(drop_vars)

    elif format == 'single_variable':

        if not variable_list:
            raise ValueError(f'Format {format} requires variable_list.')

        ds = xr.Dataset()
        for variable in variable_list:
            file_name_pattern = f'{dirin}/{case}.{stream}.{variable}.{datestr}.nc'
            files = _glob_list_files(file_name_pattern)

            logging.debug(f'Opening {len(files)} files: {files[0]}...{files[-1]}')
            ds = xr.merge((ds,xr.open_mfdataset(files,**xr_open_ds)))

        ds = ds.chunk({'time':1})
    else:
        raise ValueError(f'Unknown format: {format}')


    # should this method handle making the 'time' variable functional?
    # (i.e., take mean of time_bound, convert to date object)


    return ds


#-------------------------------------------------------------------------------
#-- function
#-------------------------------------------------------------------------------

def list_files(format,**kwargs):

    '''List files from CESM output.

    There are two formats:
    - multi_variable:
        - if variable_list has been specified, drop extraneous variables

    - single_variable:
        - require variable_list, merge all variables into dataset
    '''

    #-- parse input arguments
    dirin = kwargs.pop('dirin')
    case = kwargs.pop('case')
    stream = kwargs.pop('stream')
    datestr = kwargs.pop('datestr')

    variable_list = kwargs.pop('variable_list', [])

    if kwargs:
        raise ValueError(f'Unknown argument: {kwargs}')

    if format == 'hist':

        file_name_pattern = f'{dirin}/{case}.{stream}.{datestr}.nc'
        return _glob_list_files(file_name_pattern, error_if_nofiles=False)

    elif format == 'single_variable':

        if not variable_list:
            raise ValueError(f'Format {format} requires variable_list.')

        if isinstance(variable_list,str):
            variable_list = [variable_list]

        files = {}
        for variable in variable_list:
            file_name_pattern = f'{dirin}/{case}.{stream}.{variable}.{datestr}.nc'
            files[variable] = _glob_list_files(file_name_pattern,
                                               error_if_nofiles=False)
        return files

    else:
        raise ValueError(f'Unknown format: {format}')
