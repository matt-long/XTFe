#!/bin/bash


campaign_path=/gpfs/csfs1/cesm/development/bgcwg/projects/xtFe/cases

CASE=g.e21.G1850ECOIAF.T62_g17.xtfe.001
ARGS="--components ocn,ice --campaign-transfer --campaign-path ${campaign_path}"
DEMO=   #"--demo"
./misc-tools/cesm_hist2tseries.py ${ARGS} ${DEMO} ${CASE}
