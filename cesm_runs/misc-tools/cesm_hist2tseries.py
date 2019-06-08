#! /usr/bin/env python
"""Make history files into timeseries"""

import os
from subprocess import check_call, Popen, PIPE
from glob import glob
import re
import click

import yaml
import tempfile
import logging

import cftime
import xarray as xr
import numpy as np

from workflow import task_manager as tm

logging.basicConfig(level=logging.INFO)

script_dir = os.path.dirname(__file__)

GLOBUS_CAMPAIGN = '6b5ab960-7bbf-11e8-9450-0a6d4e044368'
GLOBUS_GLADE = 'd33b3614-6d04-11e5-ba46-22000b92c6ec'
GLOBUS_CAMPAIGN_PATH = '/gpfs/csfs1/cesm/development/bgcwg/projects/xtFe/cases'

USER = os.environ['USER']
ARCHIVE_ROOT = f'/glade/scratch/{USER}/archive'

tm.ACCOUNT = 'NCGD0011'
tm.MAXJOBS = 30

xr_open = dict(decode_times=False, decode_coords=False)

def globus(cmd, arg):
    if not isinstance(arg, list):
        arg = [arg]
    cmd = ['globus', cmd] + arg
    print(cmd)
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode('UTF-8')
    stderr = stderr.decode('UTF-8')
    ok = p.returncode == 0
    return ok

def get_year_filename(file):
    """Get the year from the datestr part of a file."""
    date_parts = [int(d) for d in file.split('.')[-2].split('-')]
    return date_parts[0]

class file_date(object):
    """Class with attributes for the start, stop, and middle of a file's time
       axis.
    """
    def __init__(self, file):
        with xr.open_dataset(file, **xr_open) as ds:
            time_units = ds.time.units
            calendar = ds.time.calendar
            tb = ds.time.bounds
            tb_dim = ds[tb].dims[-1]

            t0 = ds[tb].isel(**{'time': 0, tb_dim: 0})
            tf = ds[tb].isel(**{'time': -1, tb_dim: -1})

            self.date = cftime.num2date(np.mean([t0, tf]), units=time_units,
                                        calendar=calendar)
            self.year = self.date.year
            self.month = self.date.month
            self.day = self.date.day

            time_mid_point = cftime.num2date(ds[tb].mean(dim=tb_dim),
                                             units=time_units, calendar=calendar)

            self.t0 = time_mid_point[0]
            self.tf = time_mid_point[-1]


def get_date_string(files, freq):
    """return a date string for timeseries files"""

    date_start = file_date(files[0])
    date_end = file_date(files[-1])

    year = [date_start.t0.year, date_end.tf.year]
    month = [date_start.t0.month, date_end.tf.month]
    day = [date_start.t0.day, date_end.tf.day]

    if freq in ['day_1', 'daily', 'day']:
        return (f'{year[0]:04d}{month[0]:02d}{day[0]:02d}-'
                f'{year[1]:04d}{month[1]:02d}{day[1]:02d}')

    elif freq in ['month_1', 'monthly',  'mon']:
        return (f'{year[0]:04d}{month[0]:02d}-'
                f'{year[1]:04d}{month[1]:02d}')

    elif freq in ['year_1', 'yearly', 'year', 'ann']:
        return (f'{year[0]:04d}-'
                f'{year[1]:04d}')
    else:
        raise ValueError(f'freq: {freq} not implemented')


def get_vars(files):
    """get lists of non-time-varying variables and time varying variables"""

    with xr.open_dataset(files[0], **xr_open) as ds:
        static_vars = [v for v, da in ds.variables.items() if 'time' not in da.dims]
        static_vars = static_vars+['time', ds.time.attrs['bounds']]

        time_vars = [v for v, da in ds.variables.items() if 'time' in da.dims and
                     v not in static_vars]
    return static_vars, time_vars


@click.command()
@click.argument('case')
@click.option('--components', default='ocn')
@click.option('--archive-root', default=ARCHIVE_ROOT)
@click.option('--only-streams', default=[])
@click.option('--campaign-transfer', default=False, is_flag=True)
@click.option('--campaign-path', default=GLOBUS_CAMPAIGN_PATH)
@click.option('--year-groups', default=None)
@click.option('--demo', default=False, is_flag=True)
@click.option('--clobber', default=False, is_flag=True)

def main(case, components=['ocn', 'ice'], archive_root=ARCHIVE_ROOT, only_streams=[],
         campaign_transfer=False, campaign_path=None, year_groups=None,
         demo=False, clobber=False):

    droot = os.path.join(archive_root, case)
    if isinstance(components, str):
        components = components.split(',')

    if campaign_transfer and campaign_path is None:
        raise ValueError('campaign path required')

    if isinstance(year_groups, str):
        year_groups = year_groups.split(',')
        year_groups = [tuple(int(i) for i in ygi.split(':')) for ygi in year_groups]

    if year_groups is None:
        year_groups = [(-1e36, 1e36)]

    if isinstance(only_streams, str):
        only_streams = only_streams.split(',')

    logging.info('constructing time-series of the following year groups:')
    logging.info(year_groups)
    print()

    with open(f'{script_dir}/cesm_streams.yml') as f:
        streams = yaml.safe_load(f)


    for component in components:
        print('='*80)
        logging.info(f'working on component: {component}')
        print('='*80)
        for stream, stream_info in streams[component].items():

            if only_streams:
                if stream not in only_streams:
                    continue

            print('-'*80)
            logging.info(f'working on stream: {stream}')
            print('-'*80)

            dateglob = stream_info['dateglob']
            dateregex = stream_info['dateregex']
            freq = stream_info['freq']

            dout = f'{droot}/{component}/proc/tseries/{freq}'
            if not os.path.exists(dout):
                os.makedirs(dout, exist_ok=True)

            # set target destination on globus
            globus_file_list = []
            if campaign_transfer:
                campaign_dout = f'{GLOBUS_CAMPAIGN}:{campaign_path}'
                additions = [case, component, 'proc', 'tseries', freq]
                for add in additions:
                    campaign_dout = f'{campaign_dout}/{add}'
                    if not globus('ls', campaign_dout):
                        globus('mkdir', campaign_dout)

                # get list of files already on campaign
                p = Popen(['globus', 'ls', campaign_dout], stdout=PIPE, stderr=PIPE)
                stdout, stderr = p.communicate()
                stdout = stdout.decode('UTF-8')
                stderr = stderr.decode('UTF-8')
                ok = p.returncode == 0
                if not ok:
                    print(stdout)
                    print(stderr)
                    raise Exception('globus "ls" failed')
                globus_file_list = stdout.split('\n')
                logging.info(f'found {len(globus_file_list)} files on campaign.')


            # get input files
            files = sorted(glob(f'{droot}/{component}/hist/{case}.{stream}.{dateglob}.nc'))
            if len(files) == 0:
                logging.warning(f'no files: component={component}, stream={stream}')
                continue

            # get file dates
            files_year = [get_year_filename(f) for f in files]

            # get variable lists
            static_vars, time_vars = get_vars(files)

            # make a report
            logging.info(f'found {len(files)} history files')
            logging.info(f'history file years: {min(files_year)}-{max(files_year)}')
            logging.info(f'found {len(time_vars)} variables to process')
            logging.info(f'expecting to generate {len(time_vars) * len(year_groups)} timeseries files')

            for y0, yf in year_groups:
                logging.info(f'working on year group {y0}-{yf}')

                files_group_i = [f for f, y in zip(files, files_year)
                                 if (y0 <= y) and (y <= yf)]

                fid, tmpfile = tempfile.mkstemp(suffix='.filelist', prefix='tmpfile',
                                                dir=os.environ['TMPDIR'])

                with open(tmpfile,'w') as fid:
                    for i, f in enumerate(files_group_i):
                        fid.write('%s\n'%f)

                # get the date string
                date_cat = get_date_string(files_group_i, freq)

                for i, v in enumerate(time_vars):
                    file_cat_basename = '.'.join([case, stream, v, date_cat, 'nc'])
                    file_cat = os.path.join(dout, file_cat_basename)

                    if not clobber:
                        if file_cat_basename in globus_file_list:
                            print(f'on campaign: {file_cat_basename}...skipping')
                            continue
                        if os.path.exists(file_cat):
                            print(f'exists: {file_cat_basename}...skipping')
                            continue

                    logging.info(f'creating {file_cat}')
                    vars = ','.join(static_vars+[v])
                    cat_cmd = [f'cat {tmpfile} | ncrcat -O -h -v {vars} {file_cat}']
                    compress_cmd = [f'ncks -O -4 -L 1 {file_cat} {file_cat}']

                    if not demo:
                        if campaign_transfer:
                            label = file_cat_basename.replace('.', ' ').replace('-', ' ')
                            xfr_cmd = ['globus', 'transfer',
                                       f'{GLOBUS_GLADE}:{file_cat}',
                                       f'{campaign_dout}/{file_cat_basename}',
                                       '--notify', 'failed,inactive',
                                       '--label', f'"{label}"']

                            xfr_cmd = ' '.join(xfr_cmd)
                            xfr_cmd = f"task_id=$({xfr_cmd} | tail -n 1 | awk -F': ' '{{print $2}}')"
                            xfr_cmd = [xfr_cmd]
                            wait_cmd = ['globus task wait ${task_id}']
                            cleanup_cmd = ['rm', '-f', file_cat]
                        else:
                            xfr_cmd = []
                            wait_cmd = []
                            cleanup_cmd = []

                        jid = tm.submit([cat_cmd, compress_cmd,
                                         xfr_cmd, wait_cmd,
                                         cleanup_cmd],
                                         modules=['nco'], memory='100GB')



                print()

    tm.wait()

if __name__ == '__main__':
    main()
