#!/usr/bin/env python3

import sys
import os

from common import type_name


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('dict', help='combined dictionary (run combinedicts.py)')
    ap.add_argument('tagged', help='tagger output')                    
    return ap


def load_combined(fn):
    serial_map = {}
    with open(fn) as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip()
            fields = l.split('\t')
            serial, name, norm = fields
            serial_map[serial] = (name, norm)
    return serial_map


def process(fn, serial_map):
    with open(fn, encoding='utf-8') as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip('\n')
            fields = l.split('\t')
            if len(fields) != 8:
                raise ValueError('line {} in {}: wanted 8 fields, got {}: {}'.\
                                 format(ln, fn, len(fields), l))
            pmid, para, sent, start, end, text, type_, serial = fields
            if serial in serial_map:
                name, norm = serial_map[serial]
            tname = type_name(type_)
            print('\t'.join([
                pmid, para, sent, start, end, text, tname, name, norm]))


def main(argv):
    args = argparser().parse_args(argv[1:])
    serial_map = load_combined(args.dict)
    process(args.tagged, serial_map)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
