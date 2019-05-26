#!/usr/bin/env python3

import sys
import os

from collections import OrderedDict
from logging import warning, error

from common import type_name, rewrite_norm_id


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('preferred', metavar='PREF-TSV',
                    help='preferred entity names')
    ap.add_argument('names', metavar='NAME-TSV',
                    help='all entity names')
    ap.add_argument('entities', metavar='ID-TSV',
                    help='entity identifiers')
    return ap


def load_names(fn, names=None):
    if names is None:
        names = {}
    read_count, error_count, store_count = 0, 0, 0
    # binary mode as there are in cases encoding issues in this data.
    with open(fn, 'rb') as f:
        for ln, l in enumerate(f, start=1):
            try:
                l = l.decode('utf-8')
            except:
                error('line {} in {}'.format(ln, fn))
                error_count += 1
                continue
            l = l.rstrip()
            fields = l.split('\t')
            serial, name = fields
            if serial not in names:
                names[serial] = name
                store_count += 1
            read_count += 1
    print('read {} names, stored {} from {} ({} errors)'.format(
        read_count, store_count, fn, error_count), file=sys.stderr)
    return names


def load_entities(fn):
    entities = OrderedDict()
    read_count, store_count = 0, 0
    with open(fn) as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip()
            fields = l.split('\t')
            serial, type_, id_ = fields
            if serial not in entities:
                entities[serial] = (type_, id_)
                store_count += 1
            read_count += 1
    print('read {} entities, stored {} from {}'.format(
        read_count, store_count, fn), file=sys.stderr)
    return entities


def make_organism_name_map(names, entities):
    organism_name = {}
    for serial, (type_, id_) in entities.items():
        if type_ == '-2' and serial in names:
            organism_name[id_] = names[serial]
    return organism_name


def main(argv):
    args = argparser().parse_args(argv[1:])
    names = load_names(args.preferred)
    names = load_names(args.names, names)
    entities = load_entities(args.entities)
    organism_name = make_organism_name_map(names, entities)
    for serial, (type_, id_) in entities.items():
        if serial not in names:
            continue    # couldn't be tagged
        name = names[serial]
        typename = type_name(type_)
        if typename == 'Gene':
            organism = organism_name.get(type_, '<UNKNOWN>')
        else:
            organism = None
        if organism is not None:
            name = '{} ({})'.format(name, organism)    # attach organism
        id_ = rewrite_norm_id(id_, typename, organism)
        print('\t'.join([serial, name, id_]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
