#! /usr/bin/env python
import os
import click
import xarray as xr
import numpy as np

@click.command()
@click.option('--rtol', default=1e-5, help='Relative tolerance')
@click.option('--atol', default=1e-8, help='Absolute tolerance')
@click.argument('file1')
@click.argument('file2')

def compare_files(file1, file2, rtol=1e-5, atol=1e-8):

    if not os.path.exists(file1):
        raise FileNotFoundError(file1)

    if not os.path.exists(file2):
        raise FileNotFoundError(file2)

    print(f'Examining:\n(1) {file1}\n(2) {file2}')
    ds1 = xr.open_dataset(file1, decode_times=False, decode_coords=False)
    ds2 = xr.open_dataset(file2, decode_times=False, decode_coords=False)


    compare_results = {}
    equal = []
    close = []
    for v in ds1.variables:
        if v not in ds2.variables:
            print(f'missing {v} in (2)')
        else:
            try:
                xr.testing.assert_identical(ds1[v], ds2[v])
                compare_results[v] = 'identical'
                equal.append(True)
                close.append(True)
            except:
                try:
                    xr.testing.assert_allclose(ds1[v], ds2[v], rtol=rtol, atol=atol)
                    compare_results[v] = 'close'
                    equal.append(False)
                    close.append(True)
                except:
                    compare_results[v] = 'different'
                    equal.append(False)
                    close.append(False)


    print(f'All equal: {all(equal)}')

    if not all(equal):
        print(f'All close: {all(close)}')
        for v, result in compare_results.items():
            print(f'{v}: {result}')





if __name__ == '__main__':
    compare_files()
