#! /usr/bin/env python
import sys
import os
from subprocess import call, check_call, PIPE, Popen

SCRATCH = os.path.join('/glade/scratch', os.environ['USER'])

class defcase(object):
    def __init__(self, compref, compset, res, note, ens, croot):
        name_parts = [compref, compset, res]
        if note:
            name_parts.append(note)
        name_parts.append('%03d'%ens)

        self.name = '.'.join(name_parts)

        self.path = {
            'root': os.path.join(croot, self.name),
            'exe': os.path.join(SCRATCH, self.name),
            'dout_s': os.path.join(SCRATCH,'archive', self.name),
            'dout_sl': os.path.join(SCRATCH,'archive.locked', self.name),
            }

def xmlchange(xmlsetting, file_name='', subgroup=''):
    print('')
    for var, val in xmlsetting.items():
        if type(val) == bool:
            val = str(val).upper()
        elif any([type(val) == tp for tp in [float, int]]):
            val = str(val)

        cmd = ['./xmlchange']
        if file_name:
            cmd = cmd+['--file', file_name]
        if subgroup:
            cmd += ['--subgroup', subgroup]
        cmd += ['--id', var, '--val', val]

        print(' '.join(cmd))
        stat = call(cmd)
        if stat != 0: sys.exit(1)
    print('')


def xmlquery(xmlvar):
    cmd = ['./xmlquery', xmlvar]
    p = Popen(cmd, stdin=None, stdout=PIPE,  stderr=PIPE)
    stdout, stderr = p.communicate()
    if stderr:
        print(stderr)
        sys.exit(1)
    return stdout.split(':')[1].strip()



def user_nl_append(user_nl):
    for mdl, nml in user_nl.items():
        print('writing to: '+'user_nl_'+mdl)
        with open('user_nl_'+mdl, 'a') as fid:
            for l in nml:
                print(l)
                fid.write('%s\n'%l)
        print('')


def code_checkout(cesm_repo, coderoot, tag):
    """Checkout code for CESM
    If sandbox exists, check that the right tag has been checked-out.

    Otherwise, download the code, checkout the tag and run manage_externals.

    The scripts don't seem to like multiple applications of manage_externals.
    """

    sandbox = os.path.split(coderoot)[-1]

    if os.path.exists(coderoot):
        print('Check for right tag: '+coderoot)
        p = Popen('git status', shell=True, cwd=coderoot, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        stdout = stdout.decode('UTF-8')
        stderr = stderr.decode('UTF-8')
        print(stdout)
        print(stderr)
        if tag not in stdout.split('\n')[0]:
            raise ValueError('tag does not match')

    else:
        stat = check_call(['mkdir', '-p', coderoot])
        if stat != 0: sys.exit(1)

        # clone the repo
        p = Popen('git clone '+cesm_repo+' '+sandbox, shell=True,
                  cwd=coderoot+'/..', stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        if p.returncode != 0:
            raise Exception('git error')

        # check out the right tag
        p = Popen('git checkout %s'%tag, shell=True, cwd=coderoot)
        stdout, stderr = p.communicate()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        if p.returncode != 0:
            raise Exception('git error')

        # check out externals
        p = Popen('./manage_externals/checkout_externals -v', shell=True, cwd=coderoot)
        stdout, stderr = p.communicate()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        if p.returncode != 0:
            raise Exception('git error')
