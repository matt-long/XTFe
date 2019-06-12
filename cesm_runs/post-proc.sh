#!/bin/bash
#SBATCH -J post-proc
#SBATCH -n 1
#SBATCH --ntasks-per-node=1
#SBATCH -p dav
#SBATCH -A NCGD0011
#SBATCH -t 24:00:00
#SBATCH --mem=1GB
#SBATCH -e %J.out
#SBATCH -o %J.out
if [ -z $MODULEPATH_ROOT ]; then
  unset MODULEPATH_ROOT
else
  echo "NO MODULEPATH_ROOT TO RESET"
fi
if [ -z $MODULEPATH ]; then
  unset MODULEPATH
else
  echo "NO MODULEPATH TO RESET"
fi
if [ -z $LMOD_SYSTEM_DEFAULT_MODULES ]; then
  unset LMOD_SYSTEM_DEFAULT_MODULES
else
  echo "NO LMOD_SYSTEM_DEFAULT_MODULES TO RESET"
fi
source /etc/profile
export TERM=xterm-256color
export HOME=/glade/u/home/mclong
unset LD_LIBRARY_PATH
export PATH=/glade/work/mclong/miniconda3/bin:$PATH
export PYTHONUNBUFFERED=False
export TMPDIR=/glade/scratch/mclong/tmp
module load nco
module list
source activate analysis

campaign_path=/gpfs/csfs1/cesm/development/bgcwg/projects/xtFe/cases

CASE=g.e21.G1850ECOIAF.T62_g17.004
ARGS="--components ocn,ice --campaign-transfer --campaign-path ${campaign_path}"
ARGS="${ARGS} --year-groups 1:62,63:124,125:186,187:248,249:310"
#ARGS="${ARGS} --only-streams pop.h"
DEMO=  #"--demo"
/glade/u/home/mclong/p/xtfe/cesm_runs/misc-tools/cesm_hist2tseries.py ${ARGS} ${DEMO} ${CASE}
