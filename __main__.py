#!/usr/bin/env python3

"""
Rotate MAC addresses on a specified interval, with a bit of variation added.
Requires superuser privileges. Supports macOS and Linux.
"""

from argparse import ArgumentParser
from functools import partial
from inspect import getdoc
from operator import ne
from shutil import which
from typing import Callable, List, Tuple

import functools
import os
import random
import re
import subprocess
import sys
import time


DESCRIPTION = getdoc(sys.modules[__name__])

DEFAULT_DEVICE_NAME = 'eth0'
DEFAULT_CYCLE_SECONDS = 30 * 60
DEFAULT_CYCLE_VARIANCE = 0.25
DEFAULT_MAXIMUM_MAC_ADDRESS_RANDOMISATION_SEQUENTIAL_ERRORS = 3

VENDORS = dict(
    intel='00:1b:77',
    hewlett_packard='00:1b:78',
    foxconn='00:01:6c',
    cisco='00:10:29',
    amd='00:0c:87')


def make_function(f):
    return functools.update_wrapper(f(), f)


def underscored_to_capitalised(string: str) -> str:
    first = string[0].upper() if 0 < len(string) else ''

    def replace(x):
        return ' ' + x.group(1).upper()

    rest = re.sub(
        '_(\w)',
        replace,
        string[1:] if 0 < len(string) else '')

    return first + rest


def make_mapping(f, xs):
    return {x: f(x) for x in xs}


vendor_names = make_mapping(underscored_to_capitalised, VENDORS.keys())


def choose_vendor() -> Tuple[str, str]:
    items = tuple(VENDORS.items())
    return random.choice(items)


class MissingProgramError(RuntimeError):
    pass


def get_program_path(program: str) -> str:
    path = which(program)
    if path is None:
        raise MissingProgramError('the {} program was not found'.format(
            program))
    return path


@make_function
def set_device_mac_address() -> Callable[[str, str], None]:

    def mac_os(device_name, address):
        ifconfig_command = get_program_path('ifconfig')

        output = subprocess.check_output((
            'ifconfig',
            device_name,
            'ether',
            address))

        if 0 < len(output):
            print(output.decode())

    def linux(device_name, address):
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

    # `ifconfig` works on many Unix-like platforms apart from macOS, so use it
    # for all non-Linux systems.
    return linux if sys.platform == 'linux' else mac_os


def make_random_mac_address_section() -> str:
    return '{}{}'.format(random.randint(1, 9), random.randint(1, 9))


def make_random_mac_address() -> Tuple[str, str]:
    vendor, prefix = choose_vendor()
    address = '{}:{}:{}:{}'.format(
        prefix,
        *(make_random_mac_address_section() for _ in range(3)))
    return vendor, address


def variate(seconds: int, variance: float) -> float:
    delta = (random.random() - 0.5) * variance
    return seconds + (seconds * delta)


def generate_mac_addresses(device_name: str, cycle_seconds: int):
    set_mac_address = partial(set_device_mac_address, device_name)

    while True:
        vendor, address = make_random_mac_address()
        try:
            set_mac_address(address)
            yield 'ok', vendor, address
        except subprocess.CalledProcessError as e:
            yield 'error', e
        time.sleep(variate(cycle_seconds, DEFAULT_CYCLE_VARIANCE))


class TooManyMacAddressChangeErrorsError(RuntimeError):
    pass


def run_main_loop(mac_addresses, maximum_error_count: int):
    errors: List[Exception] = []
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
    parser.add_argument('--device-name', default=DEFAULT_DEVICE_NAME)

    parser.add_argument(
            '--cycle-seconds',
            type=int,
            default=DEFAULT_CYCLE_SECONDS)

    return parser.parse_args()


def main() -> None:
    print('Rotating MAC address...')

    arguments = parse_arguments()

    mac_addresses = generate_mac_addresses(
        arguments.device_name,
        arguments.cycle_seconds)

    try:
        run_main_loop(
            mac_addresses,
            maximum_error_count=DEFAULT_MAXIMUM_MAC_ADDRESS_RANDOMISATION_SEQUENTIAL_ERRORS)
    except KeyboardInterrupt as e:
        print('Keyboard interrupt caught; finished cycling MAC addresses.')
    except Exception as e:
        print('An error occured: ' + str(e))


if __name__ == '__main__':
    main()
