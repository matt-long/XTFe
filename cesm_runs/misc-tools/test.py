#! /usr/bin/env python
import click

@click.command()
@click.option('--junk-1', default=False, is_flag=True)
@click.argument('arg', default=[])
def test(arg, junk_1):
    print(arg.split(','))

    print(type(junk_1))

if __name__ == '__main__':
    test()
