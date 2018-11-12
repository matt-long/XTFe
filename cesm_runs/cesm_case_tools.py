#! /usr/bin/env python
import sys
import os
from subprocess import call,PIPE,Popen

SCRATCH = os.path.join('/glade/scratch',os.environ['USER'])

#--------------------------------------------------------
#--- class
#--------------------------------------------------------
class defcase(object):
    def __init__(self,compref,compset,res,note,ens,
                 croot):
        self.name = '.'.join([compref,compset,res,note,'%03d'%ens])
        self.path = {'root'    : '/'.join([croot,self.name]),
                     'exe'     : '/'.join([SCRATCH,self.name]),
                     'dout_s'  : '/'.join([SCRATCH,'archive',self.name]),
                     'dout_sl' : '/'.join([SCRATCH,'archive.locked',self.name])}


#--------------------------------------------------------
#--- function
#--------------------------------------------------------
def xmlchange(xmlsetting,file_name='',subgroup=''):
    print('')
    for var,val in xmlsetting.items():
        if type(val) == bool:
            val = str(val).upper()
        elif any([type(val) == tp for tp in [float,int]]):
            val = str(val)

        cmd = ['./xmlchange']
        if file_name:
            cmd = cmd+['--file',file_name]
        if subgroup:
            cmd += ['--subgroup',subgroup]
        cmd += ['--id',var,'--val',val]

        print(' '.join(cmd))
        stat = call(cmd)
        if stat != 0: sys.exit(1)
    print('')

#--------------------------------------------------------
#--- function
#--------------------------------------------------------
def xmlquery(xmlvar):
    cmd = ['./xmlquery',xmlvar]
    p = Popen(cmd,stdin=None,stdout=PIPE, stderr=PIPE)
    stdout,stderr = p.communicate()
    if stderr:
        print(stderr)
        sys.exit(1)
    return stdout.split(':')[1].strip()


#--------------------------------------------------------
#--- function
#--------------------------------------------------------
def user_nl_append(user_nl):
    for mdl,nml in user_nl.items():
        print('writing to: '+'user_nl_'+mdl)
        with open('user_nl_'+mdl,'a') as fid:
            for l in nml:
                print(l)
                fid.write('%s\n'%l)
        print('')


if __name__ == '__main__':
    pass
