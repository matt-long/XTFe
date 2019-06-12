#! /usr/bin/env python
import os
import sys
from subprocess import Popen, PIPE
import tempfile
from time import sleep
import click
import json

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
#formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
#handler.setFormatter(formatter)
logger.addHandler(handler)

tmpdir = os.environ['TMPDIR']

endpoints = {
    'campaign': '6b5ab960-7bbf-11e8-9450-0a6d4e044368',
    'glade': 'd33b3614-6d04-11e5-ba46-22000b92c6ec'}

def listdir(endpoint, path, filter=None):

    if endpoint in endpoints:
        endpoint_code = endpoints[endpoint]
    else:
        raise ValueError(f'unknown endpoint: {endpoint}')

    cmd = ['globus', 'ls', '--format', 'json']
    if filter is not None:
        cmd += ['--filter', filter]

    cmd += [f'{endpoint_code}:{path}']

    p = Popen(' '.join(cmd), shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        return []

    data = json.loads(stdout.decode('UTF-8'))

    return [d['name'] for d in data['DATA']]


def mkdir(endpoint, path):
    if endpoint in endpoints:
        endpoint_code = endpoints[endpoint]
    else:
        raise ValueError(f'unknown endpoint: {endpoint}')

    cmd = ['globus', 'mkdir', f'{endpoint_code}:{path}']
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise OSError('mkdir failed')


def makedirs(endpoint, path):
    """Recursive directory creation function. Like mkdir(),
       but makes all intermediate-level directories needed
       to contain the leaf directory."""

    if endpoint in endpoints:
        endpoint_code = endpoints[endpoint]
    else:
        raise ValueError(f'unknown endpoint: {endpoint}')

    pathpart = os.path.normpath(path).split('/')
    if path[0] == '/':
        pathpart[0] = '/'
    for i in range(1, len(pathpart)):
        if pathpart[i] not in listdir(endpoint, os.path.join(*pathpart[0:i])):
            logger.info(f'mkdir: {os.path.join(*pathpart[0:i+1])}')
            mkdir(endpoint, os.path.join(*pathpart[0:i+1]))


def unit_transfer(src, dst, batch_file=None):
    """Submit a globus transfer task (asynchronous)."""

    cmd = ['globus', 'transfer', src, dst,
           '--notify', 'failed,inactive',
           '--format', 'json']

    if batch_file is not None:
        cmd += ['--batch < '+batch_file]

    p = Popen(' '.join(cmd), shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode('UTF-8')
    stderr = stderr.decode('UTF-8')

    if p.returncode != 0:
        print(stdout)
        print(stderr)
        raise OSError('globus transfer failed')

    task_data = json.loads(stdout)
    task_id = task_data['task_id']
    logger.info(f'transfer started: {task_id}')

    with open(f'{tmpdir}/{task_id}.json', 'w') as fid:
        json.dump(task_data, fid)

    return task_data


def tasklist(status_filter='ACTIVE'):
    cmd = ['globus', 'task', 'list', f'--filter-status={status_filter}', '--format=json']
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode('UTF-8')
    stderr = stderr.decode('UTF-8')
    task_data = json.loads(stdout)
    return task_data['DATA']


def wait_tasklist(N=80):
    while len(tasklist()) > N:
        sleep(10)


def wait(task_data_or_id):
    """Wait on a globus task."""

    if isinstance(task_data_or_id, dict):
        task_id = task_data_or_id['task_id']
    else:
        task_id = task_data_or_id

    logger.info(f'waiting on: {task_id}')

    # there seems to be some kind of bug: when I run this
    # under a "click" context, it returns non-zero exit code
    # without the -vvv flag.
    cmd = ['globus', 'task', 'wait', '--polling-interval', '15',
           '-vvv',
           '--format', 'json', task_id]

    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode('UTF-8')
    stderr = stderr.decode('UTF-8')

    if p.returncode != 0:
        print(stdout)
        raise OSError(stderr)

    task_data = json.loads(stdout)

    logger.info(f'transfer status: {task_data["status"]}')

    if task_data['status'] != 'SUCCEEDED':
        with open(f'{tmpdir}/{task_id}.failure.json','w') as fid:
            json.dump(task_data, fid)

        return False

    return True


def transfer(src_ep, dst_ep, src_paths=[], dst_paths=[], batch_file=None, retry=3):
    """Perform globus transfer task and wait until completion.

    Parameters
    ----------

    src_ep : str
      Source endpoint name; must be in defined endpoints.
    dst_ep : str
      Destination endpoint name; must be in defined endpoints.
    src_paths : list or csv string
      List of source paths.
    dst_paths : list or csv string
      List of destination paths.
    batch_file : filename
      Filename of batch file with line for each transfer:
        {src_path} {dst_path}
    retry : int
      Number of times to retry transfer.
    """

    if src_ep in endpoints:
        src_ep_code = endpoints[src_ep]
    else:
        raise ValueError(f'unknown endpoint: {src_ep}')

    if dst_ep in endpoints:
        dst_ep_code = endpoints[dst_ep]
    else:
        raise ValueError(f'unknown endpoint: {dst_ep}')

    if batch_file is None:
        fid, batch_file = tempfile.mkstemp(suffix='.filelist', prefix='globus.batch.',
                                        dir=os.environ['TMPDIR'])

        with open(batch_file,'w') as fid:
            for src_path, dst_path in zip(src_paths, dst_paths):
                fid.write(f'{src_path} {dst_path}\n')

    for _ in range(retry):
        wait_tasklist()
        task_data = unit_transfer(src_ep_code, dst_ep_code, batch_file=batch_file)
        if wait(task_data):
            return True
        sleep(10)

    return False

@click.command()
@click.option('--src-ep')
@click.option('--dst-ep')
@click.option('--src-paths', default=[])
@click.option('--dst-paths', default=[])
@click.option('--batch-file', default=None)
@click.option('--retry', default=3)

def main(src_ep, dst_ep, src_paths, dst_paths, batch_file, retry):

    if isinstance(src_paths, str):
        src_paths = src_paths.split(',')
    if isinstance(dst_paths, str):
        dst_paths = dst_paths.split(',')

    return  transfer(src_ep, dst_ep, src_paths, dst_paths, batch_file, retry)

if __name__ == '__main__':

    ok = main()
    if not ok:
        sys.exit(1)
    else:
        sys.exit(0)
