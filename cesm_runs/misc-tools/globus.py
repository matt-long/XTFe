#! /usr/bin/env python
import os
import sys
from subprocess import Popen, PIPE
import tempfile
from time import sleep
import click

import yaml
import json

import logging

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

tmpdir = os.environ.get('TMPDIR')
if not tmpdir:
    logger.warning("TMPDIR not found in environment, using /tmp")
    tmpdir = "/tmp"
package_dir = os.path.dirname(os.path.realpath(__file__))

with open(f'{package_dir}/globus-endpoints.yaml', 'r') as fid:
    endpoints = yaml.safe_load(fid)


def get_endpoint_uuid(endpoint):
    """Get the endpoint UUID."""
    if endpoint in endpoints:
        return endpoints[endpoint]
    else:
        raise ValueError(f'unknown endpoint: {endpoint}')


def activate(endpoint):
    """Activate endpoint via web."""
    endpoint_uuid = get_endpoint_uuid(endpoint)

    cmd = ['globus', 'endpoint', 'activate', '--web', '--no-browser',
           endpoint_uuid]

    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    print(stderr.decode('UTF-8'))
    print(stdout.decode('UTF-8'))
    if p.returncode == 1:
        raise OSError('activate command failed')
    elif p.returncode == 2:
        raise OSError('activate command failed')
    else:
        raise ValueError('activate: unknown return code')


def isactivated(endpoint):
    """Check if a named endpoint is activated."""
    endpoint_uuid = get_endpoint_uuid(endpoint)

    cmd = ['globus', 'endpoint', 'is-activated',
           endpoint_uuid]

    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode == 0:
        return True
    elif p.returncode == 1:
        return False
    elif p.returncode == 2:
        print(stderr.decode('UTF-8'))
        print(stdout.decode('UTF-8'))
        raise OSError('isactivated command failed')
    else:
        raise ValueError('isactivated: unknown return code')


def listdir(endpoint, path, filter=None):
    """Return a list containing the names of the entries in the
       directory given by path.

    Parameters
    ----------
    endpoint : str
       Endpoint name (must be in known endpoints).
    path : str
        This is the directory, which needs to be explored.
    filter : str, optional
        Filter results to filenames matching the given pattern.

        Filter patterns must start with =, ~, !, or !~
        If none of these are given, = will be used

        = does exact matching

        ~ does regex matching, supporting globs (*)

        ! does inverse = matching

        !~ does inverse ~ matching

    Returns
    -------
    dir_listing : list
      A sorted list containing names of entries in the directory.

    """
    if not isactivated(endpoint):
        raise ValueError('endpoint is not activated')

    endpoint_uuid = get_endpoint_uuid(endpoint)

    cmd = ['globus', 'ls', '--format', 'json']
    if filter is not None:
        cmd += ['--filter', filter]

    cmd += [f'{endpoint_uuid}:{path}']

    p = Popen(' '.join(cmd), shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        return []

    data = json.loads(stdout.decode('UTF-8'))

    return sorted([d['name'] for d in data['DATA']])


def mkdir(endpoint, path):
    """Make directory."""
    if not isactivated(endpoint):
        raise ValueError('endpoint is not activated')

    endpoint_uuid = get_endpoint_uuid(endpoint)

    cmd = ['globus', 'mkdir', f'{endpoint_uuid}:{path}']
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise OSError('mkdir failed')


def makedirs(endpoint, path):
    """Recursive directory creation function. Like mkdir(),
       but makes all intermediate-level directories needed
       to contain the leaf directory.

    Parameters
    ----------
    endpoint : str
      Endpoint name (must be in known endpoints).

    """

    endpoint_uuid = get_endpoint_uuid(endpoint)

    pathpart = os.path.normpath(path).split('/')
    if path[0] == '/':
        pathpart[0] = '/'
    for i in range(1, len(pathpart)):
        if pathpart[i] not in listdir(endpoint, os.path.join(*pathpart[0:i])):
            logger.info(f'mkdir: {os.path.join(*pathpart[0:i+1])}')
            mkdir(endpoint, os.path.join(*pathpart[0:i + 1]))


def transfer_async(src, dst, batch_file=None):
    """Submit a globus transfer task (asynchronous).

    Parameters
    ----------
    src : str
      The source endpoint UUID.
    dst : str
      The destination endpoint UUID.
    batch_file : str, optional
      A filename for batch transfers. Batch files are structured as follows:
        path/on/src path/on/dst
      with one line per file or directory.

    Returns
    -------
    task_data : dict
      Attributes of transfer.
    """

    cmd = ['globus', 'transfer', src, dst,
           '--notify', 'failed,inactive',
           '--format', 'json']

    if batch_file is not None:
        cmd += ['--batch < ' + batch_file]

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
    """Return list of globus tasks.

    Parameters
    ----------
    status_filter : str, optional
      Possible values: [ACTIVE|INACTIVE|FAILED|SUCCEEDED]

    Returns
    -------
    task_data : list
      List of dictionaries with information on task matching `status_filter`.
    """

    cmd = [
        'globus',
        'task',
        'list',
        f'--filter-status={status_filter}',
        '--format=json']
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode('UTF-8')
    stderr = stderr.decode('UTF-8')
    task_data = json.loads(stdout)
    return task_data['DATA']


def wait_tasklist(N=80):
    """Wait until task list has less than `N` active tasks.

    Parameters
    ----------
    N : int
        Wait until there are less than `N` active tasks.
    """
    while len(tasklist(status_filter='ACTIVE')) > N:
        sleep(10)


def wait(task_data_or_id):
    """Wait on a globus task.

    Parameters
    ----------
    task_data_or_id : str or dict
        Can be dict as returned from `transfer_async` or the `task_id` entry if __name__ == '__main__':
            such a dictionary.

    Returns
    -------
    status : boolean
        Returns `True` if task has succeeded; otherwise returns `False`.
    """

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
        with open(f'{tmpdir}/{task_id}.failure.json', 'w') as fid:
            json.dump(task_data, fid)

        return False

    return True


def transfer(src_ep, dst_ep, src_paths=[],
             dst_paths=[], batch_file=None, retry=3):
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

    Returns
    -------
    status : boolean
        Returns `True` if transfer succeeded; otherwise returns `False`.
    """

    src_ep_uuid = get_endpoint_uuid(src_ep)
    dst_ep_uuid = get_endpoint_uuid(dst_ep)

    if batch_file is None:
        fid, batch_file = tempfile.mkstemp(suffix='.filelist', prefix='globus.batch.',
                                           dir=tmpdir)

        with open(batch_file, 'w') as fid:
            for src_path, dst_path in zip(src_paths, dst_paths):
                fid.write(f'{src_path} {dst_path}\n')

    for _ in range(retry):
        wait_tasklist()
        task_data = transfer_async(
            src_ep_uuid, dst_ep_uuid, batch_file=batch_file)
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
    """Command line interface to `transfer`."""
    if isinstance(src_paths, str):
        src_paths = src_paths.split(',')
    if isinstance(dst_paths, str):
        dst_paths = dst_paths.split(',')

    return transfer(src_ep, dst_ep, src_paths, dst_paths, batch_file, retry)


if __name__ == '__main__':

    ok = main()
    if not ok:
        sys.exit(1)
    else:
        sys.exit(0)
