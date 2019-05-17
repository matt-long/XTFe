#! /usr/bin/env python
from __future__ import absolute_import, division, print_function

try:
    input = raw_input
except NameError:
    pass

import os
from subprocess import check_call, Popen, PIPE
from glob import glob
from collections import OrderedDict
from cesm_case_tools import defcase, xmlchange, xmlquery, user_nl_append, code_checkout

import sys
if sys.version_info[0] >= 3:
    print('Requires Python 2.x, not Python 3.x')
    sys.exit(1)

#-------------------------------------------------------------------------------
#--- project and codebase
#-------------------------------------------------------------------------------

project_name = ''
project_code = 'NCGD0011'
walltime = '12:00:00'
queue = 'regular'

cesm_repo = 'https://github.com/matt-long/cesm.git'
tag = 'cesm2.1.1-rc.02_xtfe0.2'

coderoot = os.path.join('/glade/work', 'mclong', 'codes', tag)

compref = 'g.e21'
res = 'T62_g17'
ens = 1

source_mod_dir = 'source-mod/fe-dep-ocean-ice-correction-xtfe-30x'
note = 'xtfe'
compset = 'G1850ECOIAF'
mach = 'cheyenne'

description = 'Ocean-ice hindcast, XT-Fe forcing 100% soluble, applied 30x multiplier'

#-------------------------------------------------------------------------------
#-- paths
#-------------------------------------------------------------------------------

scriptroot = os.getcwd()
inputdata='/glade/p/cesmdata/cseg/inputdata'

caserootroot = os.path.join('/glade/work',os.environ['USER'],'cesm_cases')
if project_name:
    caserootroot = os.path.join(caserootroot, project_name)

if not os.path.exists(caserootroot):
    check_call(['mkdir','-p',caserootroot])

#-------------------------------------------------------------------------------
#---- init and forcing
#-------------------------------------------------------------------------------

run_refcase = None #'g.e21.G1850ECOIAF.T62_g17.003'
if run_refcase:
    run_refdate = '0003-01-01'
    refcase_root= os.path.join('/glade/scratch/mclong/archive',
                               run_refcase,'rest',run_refdate+'-00000')

#----------------------------------------------------------------------
#--- make the case name
#----------------------------------------------------------------------

case = defcase(compref=compref,
               compset=compset,
               res=res,
               note=note,
               ens=ens,
               croot=caserootroot)

rundir = os.path.join(case.path['exe'], 'run')

case_desc_file = 'case-description/'+case.name+'.description'
assert not os.path.exists(case_desc_file)
with open(case_desc_file, 'w') as f:
    f.write(description)

#-------------------------------------------------------------------------------
#-- git checkout tag
#-------------------------------------------------------------------------------

code_checkout(cesm_repo, coderoot, tag)

ok = input('Continue\ny/[n]\n')
if ok != 'y':
    exit(0)

#-------------------------------------------------------------------------------
#--- create case
#-------------------------------------------------------------------------------

for key,pth in case.path.items():
    stat = check_call(['rm','-fvr',pth])

cmd = ['/'.join([coderoot,'cime/scripts','create_newcase']),
       '--res',     res,
       '--mach',    mach,
       '--compset', compset,
       '--case',    case.path['root'],
       '--project', project_code,
       '--run-unsupported']

stat = check_call(cmd)
if stat != 0: exit(1)

os.chdir(case.path['root'])

if run_refcase:
    xmlchange({'RUN_TYPE' : 'hybrid',
               'RUN_STARTDATE' : run_refdate,
               'RUN_REFCASE' : run_refcase,
               'RUN_REFDATE' : run_refdate})
    check_call(['mkdir','-p',rundir])
    check_call(' '.join(['cp','-v',refcase_root+'/*',rundir]),shell=True)

else:
    xmlchange({'RUN_TYPE' : 'startup'})

xmlchange({'JOB_QUEUE' : queue},subgroup='case.run')
xmlchange({'JOB_WALLCLOCK_TIME':walltime},subgroup='case.run')

xmlchange({'OCN_TRACER_MODULES' : 'iage ecosys'})

#-------------------------------------------------------------------------------
#--- pe layout
#-------------------------------------------------------------------------------

xmlchange({'NTASKS_ATM':  36, 'NTHRDS_ATM': 2, 'ROOTPE_ATM': 0,
           'NTASKS_ROF':  36, 'NTHRDS_ROF': 2, 'ROOTPE_ROF': 0,
           'NTASKS_GLC':  36, 'NTHRDS_GLC': 2, 'ROOTPE_GLC': 0,
           'NTASKS_LND':  36, 'NTHRDS_LND': 2, 'ROOTPE_LND': 0,
           'NTASKS_ESP':  36, 'NTHRDS_LND': 2, 'ROOTPE_LND': 0,
           'NTASKS_CPL':  36, 'NTHRDS_CPL': 2, 'ROOTPE_CPL': 0,
           'NTASKS_ICE':  36, 'NTHRDS_ICE': 2, 'ROOTPE_ICE': 0})

xmlchange({'NTASKS_OCN': 216, 'NTHRDS_OCN': 2,'ROOTPE_OCN': 36})

"""
xmlchange({
           'POP_BLCKX' : 16,
           'POP_BLCKY' : 16,
           'POP_NX_BLOCKS' : 20,
           'POP_NY_BLOCKS' : 24})

xmlchange({'POP_MXBLCKS' : 1,
           'POP_DECOMPTYPE' : 'cartesian',
           'POP_AUTO_DECOMP' : 'false'})
"""


#-------------------------------------------------------------------------------
#--- source mods
#-------------------------------------------------------------------------------

if source_mod_dir:
    for cmp in ['pop','datm','drv']:
        frm = os.path.join(scriptroot, source_mod_dir, 'src.'+cmp,'*')
        to = 'SourceMods/src.'+cmp+'/.'
        if glob(frm):
            check_call(' '.join(['cp','-v',frm,to]),shell=True)

#-------------------------------------------------------------------------------
#--- DATM settings
#-------------------------------------------------------------------------------

xmlchange({'DATM_PRESAERO': 'clim_2000'})

# SWDN is the 3rd stream; set temporal interpolation scheme to COSZEN
user_nl_append(
    {'datm': [('tintalgo = "linear", "linear", "coszen", "linear", "linear", "linear",'
                         '"linear", "linear", "linear", "linear", "linear", "linear"')]}
    )

#-------------------------------------------------------------------------------
#--- pop settings
#-------------------------------------------------------------------------------

user_nl_append(
    {'pop': [
        "dust_flux_source = 'driver'",
        "iron_flux_source = 'driver-derived'",
        #
        "riv_flux_shr_stream_year_align = 1",
        "riv_flux_shr_stream_year_first = 2000",
        "riv_flux_shr_stream_year_last = 2000",           # make river forcing constant
        #
        "o2_consumption_scalef_input%scale_factor = 1.0", # turn off O2 kludge
        "o2_consumption_scalef_opt = 'const'",
        #
        "ciso_tracer_init_ext(1)%file_varname = 'DIC'",
        "ciso_tracer_init_ext(1)%mod_varname = 'DI13C'",
        "ciso_tracer_init_ext(1)%scale_factor = 1.0",
        "dust_ratio_thres = 66.28178906901309"
        ],
    'marbl' : [
        "ciso_on = .false.",
        ]})


#-------------------------------------------------------------------------------
#--- configure
#-------------------------------------------------------------------------------

check_call(['./case.setup'])

#-------------------------------------------------------------------------------
#--- build
#-------------------------------------------------------------------------------
stat = check_call(['./preview_namelists'])
if stat != 0: exit(1)

xmlchange({'STOP_N' : 2,
           'STOP_OPTION' : 'nyear',
           'RESUBMIT' : 0})

stat = check_call(['qcmd','-A',project_code,'--','./case.build'])
if stat != 0: exit(1)

check_call(['./case.submit'])
