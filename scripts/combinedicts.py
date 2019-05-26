#!/usr/bin/env python3

import sys
import os

from collections import OrderedDict
from logging import warning, error

from common import typename_and_species, rewrite_norm_id


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
    read_count, store_count = 0, 0
    with open(fn) as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip()
            fields = l.split('\t')
            serial, name = fields
            if serial not in names:
                names[serial] = name
                store_count += 1
            read_count += 1
    print('read {} names, stored {} from {}'.format(
        read_count, store_count, fn), file=sys.stderr)
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


def main(argv):
    args = argparser().parse_args(argv[1:])
    names = load_names(args.preferred)
    names = load_names(args.names, names)
    entities = load_entities(args.entities)
    for serial, (type_, id_) in entities.items():
        if serial not in names:
            continue    # couldn't be tagger
        name = names[serial]
        typename, species = typename_and_species(type_)
        if typename == 'Gene' and species is not None:
            name = '{} ({})'.format(name, species)    # attach species
        id_ = rewrite_norm_id(id_, typename, species)
        print('\t'.join([serial, name, id_]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
