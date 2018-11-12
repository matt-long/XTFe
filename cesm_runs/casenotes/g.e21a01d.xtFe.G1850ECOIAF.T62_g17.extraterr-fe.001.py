#! /usr/bin/env python
from __future__ import absolute_import, division, print_function

try:
    input = raw_input
except NameError:
    pass

import os
from subprocess import call, Popen, PIPE
from glob import glob
from collections import OrderedDict
from cesm_case_tools import defcase, xmlchange, xmlquery, user_nl_append

import sys
if sys.version_info >= (3, 0):
    print('Requires Python 2.x, not Python 3.x')
    sys.exit(1)

#-------------------------------------------------------------------------------
#--- project and codebase
#-------------------------------------------------------------------------------

project_name = 'extraterr-fe'
project_code = 'NCGD0011'
walltime = '12:00:00'
queue = 'regular'

cesm_repo = 'https://github.com/escomp/cesm.git'
sandbox = 'cesm2_1_extraterr_fe'
coderoot = os.path.join('/glade/work',os.environ['USER'],'codes',sandbox)

tag = 'cesm2_1_alpha01d'
compref = 'g.e21a01d.xtFe'

res = 'T62_g17'
ens = 1
source_mod_dir = ''
note = project_name
compset = 'G1850ECOIAF'
mach = 'cheyenne'

#-------------------------------------------------------------------------------
#-- paths
#-------------------------------------------------------------------------------

scriptroot = os.getcwd()
inputdata='/glade/p/cesmdata/cseg/inputdata'

caserootroot = os.path.join('/glade/work',os.environ['USER'],'cesm_cases',project_name)

if not os.path.exists(caserootroot):
    call(['mkdir','-p',caserootroot])

#-------------------------------------------------------------------------------
#---- init and forcing
#-------------------------------------------------------------------------------

run_refcase = ''
run_refdate = '0281-01-01'
refcase_root= os.path.join('/glade/p/cesm/bgcwg_dev/hpss-mirror',
                           run_refcase,'rest',run_refdate+'-00000')

#----------------------------------------------------------------------
#--- make the case name
#----------------------------------------------------------------------

case = defcase(compref=compref,compset=compset,res=res,note=note,ens=ens,
               croot=caserootroot)

rundir = os.path.join(case.path['exe'],'run')

#-------------------------------------------------------------------------------
#--- record the state of this script
#-------------------------------------------------------------------------------

casenotes = os.path.join(scriptroot,'casenotes',case.name+'.py')
if not os.path.exists(os.path.join(scriptroot,'casenotes')):
    call(['mkdir','-p',os.path.join(scriptroot,'casenotes')])

if os.path.exists(casenotes):
    print('Case exists: {0}'.format(casenotes))
    overwrite = input('Overwrite\ny/[n]\n')
    if overwrite == 'y':
        call(['rm','-vf',casenotes])
    else:
        exit(0)

call(['cp','-v',__file__,casenotes])

#-------------------------------------------------------------------------------
#-- git checkout tag
#-------------------------------------------------------------------------------

if False:
    if not os.path.exists(coderoot):
        stat = call(['mkdir','-p',coderoot])
        p = Popen('git clone '+cesm_repo+' '+sandbox,shell=True,
                  cwd=coderoot+'/..',stdout=PIPE,stderr=PIPE)
        stdout,stderr = p.communicate()
        print(stdout)
        print(stderr)

    p = Popen('git fetch origin',shell=True,cwd=coderoot)
    stdout,stderr = p.communicate()
    print(stdout)
    print(stderr)

    p = Popen('git checkout %s'%tag,shell=True,cwd=coderoot)
    stdout,stderr = p.communicate()
    print(stdout)
    print(stderr)

    p = Popen('./manage_externals/checkout_externals -v',shell=True,cwd=coderoot)
    stdout,stderr = p.communicate()
    print(stdout)
    print(stderr)

    ok = input('Continue\ny/[n]\n')
    if ok != 'y':
        exit(0)

#-------------------------------------------------------------------------------
#--- create case
#-------------------------------------------------------------------------------

for key,pth in case.path.items():
    stat = call(['rm','-fvr',pth])

cmd = ['/'.join([coderoot,'cime/scripts','create_newcase']),
       '--res',     res,
       '--mach',    mach,
       '--compset', compset,
       '--case',    case.path['root'],
       '--project', project_code,
       '--run-unsupported']

stat = call(cmd)
if stat != 0: exit(1)

os.chdir(case.path['root'])

if run_refcase:
    xmlchange({'RUN_TYPE' : 'hybrid',
               'RUN_STARTDATE' : run_refdate,
               'RUN_REFCASE' : run_refcase,
               'RUN_REFDATE' : run_refdate})
    call(['mkdir','-p',rundir])
    call(' '.join(['cp','-v',refcase_root+'/*',rundir]),shell=True)
else:
    xmlchange({'RUN_TYPE' : 'startup'})

xmlchange({'JOB_QUEUE' : queue},subgroup='case.run')
xmlchange({'JOB_WALLCLOCK_TIME':walltime},subgroup='case.run')

xmlchange({'OCN_TRACER_MODULES' : 'iage ecosys abio_dic_dic14'})

#-------------------------------------------------------------------------------
#--- pe layout
#-------------------------------------------------------------------------------

xmlchange({'NTASKS_ATM' :  36,'NTHRDS_ATM' : 1,'ROOTPE_ATM' : 0,
           'NTASKS_ROF' :  36,'NTHRDS_ROF' : 1,'ROOTPE_ROF' : 0,
           'NTASKS_GLC' :   1,'NTHRDS_GLC' : 1,'ROOTPE_GLC' : 0,
           'NTASKS_LND' :   1,'NTHRDS_LND' : 1,'ROOTPE_LND' : 0,
           'NTASKS_CPL' : 72,'NTHRDS_CPL' : 1,'ROOTPE_CPL' : 36,
           'NTASKS_ICE' : 72,'NTHRDS_ICE' : 1,'ROOTPE_ICE' : 36})

xmlchange({'NTHRDS_OCN' : 1,'ROOTPE_OCN' : 108})

xmlchange({'NTASKS_OCN' : 480,
           'POP_BLCKX' : 16,
           'POP_BLCKY' : 16,
           'POP_NX_BLOCKS' : 20,
           'POP_NY_BLOCKS' : 24})

xmlchange({'POP_MXBLCKS' : 1,
           'POP_DECOMPTYPE' : 'cartesian',
           'POP_AUTO_DECOMP' : 'false'})
#-------------------------------------------------------------------------------
#--- source mods
#-------------------------------------------------------------------------------

if source_mod_dir:
    for cmp in ['pop','datm','drv']:
        frm = os.path.join(scriptroot,'source-mods',source_mod_dir,'src.'+cmp,'*')
        to = 'SourceMods/src.'+cmp+'/.'
        if glob(frm):
            call(' '.join(['cp','-v',frm,to]),shell=True)

#-------------------------------------------------------------------------------
#--- pop settings
#-------------------------------------------------------------------------------

user_nl_append(
    {'pop': [
        "dust_flux_source = 'driver'",
        "iron_flux_source = 'driver-derived'",
        #
        "riv_flux_shr_stream_year_last = 1900",           # make river forcing constant
        #
        "o2_consumption_scalef_input%scale_factor = 1.0", # turn off O2 kludge
        "o2_consumption_scalef_opt = 'const'",
        #
        "ciso_tracer_init_ext(1)%file_varname = 'DIC'",
        "ciso_tracer_init_ext(1)%mod_varname = 'DI13C'",
        "ciso_tracer_init_ext(1)%scale_factor = 1.0",
        ],
    'marbl' : [
        "ciso_on = .true.",
        ]})

#-------------------------------------------------------------------------------
#--- configure
#-------------------------------------------------------------------------------

call(['./case.setup'])

#-------------------------------------------------------------------------------
#--- build
#-------------------------------------------------------------------------------
stat = call(['./preview_namelists'])
if stat != 0: exit(1)

xmlchange({'STOP_N' : 5,
           'STOP_OPTION' : 'nyear',
           'RESUBMIT' : 0})

stat = call(['qcmd','-A',project_code,'--','./case.build'])
if stat != 0: exit(1)

call(['./case.submit'])
