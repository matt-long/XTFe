#! /usr/bin/env python
'''Make history files into timeseries'''

import os
from subprocess import check_call, Popen, PIPE
from glob import glob
import re

import yaml
import tempfile
import logging

import cftime
import xarray as xr

from workflow import task_manager as tm

logging.basicConfig(level=logging.INFO)

TEST = False

globus_campaign = '6b5ab960-7bbf-11e8-9450-0a6d4e044368'
globus_glade = 'd33b3614-6d04-11e5-ba46-22000b92c6ec'

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

def get_date_string(files, freq):
    '''return a date string for timeseries files'''
    print(files[0])
    ds = xr.open_dataset(files[0], decode_times=False, decode_coords=False)
    time_units = ds.time.units
    calendar = ds.time.calendar
    tb = ds.time.bounds
    tb_dim = ds[tb].dims[-1]

    time_mid_point = cftime.num2date(ds[tb].mean(dim=tb_dim), units=time_units,
                                     calendar=calendar)

    date_start = time_mid_point[0]

    ds = xr.open_dataset(files[-1], decode_times=False, decode_coords=False)
    time_mid_point = cftime.num2date(ds[tb].mean(dim=tb_dim), units=time_units,
                                     calendar=calendar)
    date_end = time_mid_point[-1]

    year = [date_start.year, date_end.year]
    month = [date_start.month, date_end.month]
    day = [date_start.day, date_end.day]

    if freq == 'day_1':
        return (f'{year[0]:04d}{month[0]:02d}{day[0]:02d}-'
                f'{year[1]:04d}{month[1]:02d}{day[1]:02d}')

    elif freq == 'month_1':
        return (f'{year[0]:04d}{month[0]:02d}-'
                f'{year[1]:04d}{month[1]:02d}')

    elif freq == 'year_1':
        return (f'{year[0]:04d}-'
                f'{year[1]:04d}')
    else:
        raise ValueError(f'freq: {freq} not implemented')


def get_vars(files):
    '''get lists of non-time-varying variables and time varying variables'''

    ds = xr.open_dataset(files[0], decode_times=False, decode_coords=False)
    static_vars = [v for v, da in ds.variables.items() if 'time' not in da.dims]
    static_vars = static_vars+['time', ds.time.attrs['bounds']]

    time_vars = [v for v, da in ds.variables.items() if 'time' in da.dims and
                 v not in static_vars]
    return static_vars, time_vars


def main(case, droot, components, only_streams=[], campaign_transfer=False,
         slurmit=True, demo=False, clobber=False):

    with open('cesm_streams.yml') as f:
        streams = yaml.safe_load(f)

    for component in components:

        for stream, stream_info in streams[component].items():
            if only_streams:
                if stream not in only_streams:
                    continue

            dateglob = stream_info['dateglob']
            dateregex = stream_info['dateregex']
            freq = stream_info['freq']

            dout =  os.path.join(droot, component, 'proc', 'tseries', freq)
            if not os.path.exists(dout):
                os.makedirs(dout, exist_ok=True)

            # set target destination on globus
            globus_file_list = []
            if campaign_transfer:
                campaign_dout = f'{globus_campaign}:{globus_campaign_path}'
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

            # get input files
            files = sorted(glob(
                os.path.join(droot, component, 'hist',
                             '.'.join([case, stream, dateglob, 'nc']))))

            if len(files) == 0:
                logging.warning(f'no files: component={component}, stream={stream}')
                continue

            logging.info(f'component={component}, stream={stream}: nfile = {len(files)}')

            fid, tmpfile = tempfile.mkstemp(suffix='.filelist', prefix='tmpfile',
                                            dir=os.environ['TMPDIR'])

            with open(tmpfile,'w') as fid:
                for i, f in enumerate(files):
                    fid.write('%s\n'%f)
                    if TEST and i > 0:
                        break


            # get variable lists
            static_vars, time_vars = get_vars(files)

            # get the date string
            date_cat = get_date_string(files, freq)

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


                print(f'creating {file_cat}')
                vars = ','.join(static_vars+[v])
                cat_cmd = [f'cat {tmpfile} | ncrcat -O -h -v {vars} {file_cat}']
                compress_cmd = [f'ncks -O -4 -L 1 {file_cat} {file_cat}']

                if not demo:
                    if campaign_transfer:
                        label = file_cat_basename.replace('.', ' ').replace('-', ' ')
                        xfr_cmd = ['globus', 'transfer',
                                   f'{globus_glade}:{file_cat}',
                                   f'{campaign_dout}/{file_cat_basename}',
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



                    if TEST:
                        exit()
            print()

    tm.wait()

if __name__ == '__main__':

    tm.ACCOUNT = 'NCGD0011'
    slurmit = True
    demo = False

    #-- specify case details
    clobber = False
    archive_root = '/glade/scratch/mclong/archive'
    case = 'g.e21.G1850ECOIAF.T62_g17.004'
    droot = os.path.join(archive_root, case)


    campaign_transfer = False
    globus_campaign_path = '/gpfs/csfs1/cesm/development/omwg/projects/omip/cases'

    components = ['ocn']

    main(case, droot, components, only_streams=[],
         campaign_transfer=campaign_transfer,
         slurmit=slurmit,
         demo=demo, clobber=clobber)
