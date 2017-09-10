#!/usr/bin/env python3

"""
Rotate MAC addresses on a specified interval, with a bit of variation added.
Requires superuser privileges and the `ip` commmand, which is standard on modern
Linux.
"""

from argparse import ArgumentParser
from functools import partial
from inspect import getdoc
from operator import ne
import os
import random
import re
from shutil import which
import sys
import subprocess
import time


DESCRIPTION = getdoc(sys.modules[__name__])

DEFAULTS = dict(
    device_name=eth0,
    cycle_seconds=30 * 60,
    cycle_variance=0.25,
    maximum_mac_address_randomisation_sequential_errors=3)

VENDORS = dict(
    intel='00:1b:77',
    hewlett_packard='00:1b:78',
    foxconn='00:01:6c',
    cisco='00:10:29',
    amd='00:0c:87')


def underscored_to_capitalised(string):
    first = string[0].upper() if 0 < len(string) else ''

    rest = re.sub(
        '_(\w)',
        lambda x: ' ' + next(filter(partial(ne, None), x.groups())).upper(),
        string[1:] if 0 < len(string) else '')

    return first + rest

def make_mapping(f, xs):
    return {x: f(x) for x in xs}


vendor_names = make_mapping(underscored_to_capitalised, VENDORS.keys())
choose_vendor = partial(random.choice, tuple(VENDORS.items()))


class MissingProgramError(RuntimeError):
    pass


def get_program_path(program):
    path = which(program)
    if path is None:
        raise MissingProgramError('the {} program was not found'.format(
            command))
    return path


def set_device_mac_address(device_name, address):
    ip_command = get_program_path('ip')

    output = subprocess.check_output((
        ip_command,
        "link",
        "set",
        "dev",
        device_name,
        "addr",
        address))

    if 0 < len(output):
        print(output.decode())


def make_random_mac_address_section():
    return '{}{}'.format(random.randint(1, 9), random.randint(1, 9))


def make_random_mac_address():
    vendor, prefix = choose_vendor()
    address = '{}:{}:{}:{}'.format(
        prefix,
        *(make_random_mac_address_section() for _ in range(3)))
    return vendor, address


def variate(seconds, variance):
    delta = (random.random() - 0.5) * variance
    return seconds + (seconds * delta)


def generate_mac_addresses(device_name, cycle_seconds):
    set_mac_address = partial(set_device_mac_address, device_name)

    while True:
        vendor, address = make_random_mac_address()
        try:
            set_mac_address(address)
            yield 'ok', vendor, address
        except subprocess.CalledProcessError as e:
            yield 'error', e
        time.sleep(variate(cycle_seconds, DEFAULTS['cycle_variance']))


class TooManyMacAddressChangeErrorsError(RuntimeError):
    pass


def run_main_loop(mac_addresses, maximum_error_count):
    errors = []
    for message in mac_addresses:
        status, *data = message

        if status == 'ok':
            vendor, mac_address = data

            errors.clear()
            print('Set to MAC address {} of vendor {}.'.format(
                mac_address,
                vendor_names[vendor]))

        elif status == 'error':
            (error,) = data

            print(
                'An error occured; the program will stop if {} more '
                'occur sequentially.'.format(
                    3 - len(errors)))

            errors.append(error)
            if 3 <= len(errors):
                msg = '\n'.join(map(str, errors))
                raise TooManyMacAddressChangeErrorsError(msg)

        else:
            raise RuntimeError('unknown status: ' + status)


def parse_arguments():
    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--device-name', default=DEFAULTS['device_name'])

    parser.add_argument(
            '--cycle-seconds',
            type=int,
            default=DEFAULTS['cycle_seconds'])

    return parser.parse_args()


def main():
    print('Rotating MAC address...')

    arguments = parse_arguments()

    mac_addresses = generate_mac_addresses(
        arguments.device_name,
        arguments.cycle_seconds)

    try:
        run_main_loop(
            mac_addresses,
            maximum_error_count=DEFAULTS[
                'maximum_mac_address_randomisation_sequential_errors'])
    except KeyboardInterrupt as e:
        print('Keyboard interrupt caught; finished cycling MAC addresses.')
    except Exception as e:
        print('An error occured: ' + str(e))


if __name__ == '__main__':
    main()
