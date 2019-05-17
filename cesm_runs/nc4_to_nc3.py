#! /usr/bin/env python

import click
from subprocess import Popen, PIPE


@click.command()
@click.argument('file')
def ncks_3(file):
    cmd = ' && '.join(['module load nco', f'ncks -O -3 {file} {file}'])

    p = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
    stdout, stderr = p.communicate()

    if p.returncode != 0:
        stdout = stdout.decode('UTF-8')
        stderr = stderr.decode('UTF-8')
        if stdout:
            print('error stdout: ' + stdout)
        if stderr:
            print('error stderr: ' + stderr)
            
if __name__ == '__main__':
    ncks_3()