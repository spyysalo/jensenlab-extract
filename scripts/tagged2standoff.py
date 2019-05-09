#!/usr/bin/env python3

import sys
import os
import errno

from itertools import count
from collections import defaultdict
from logging import info, warning, error

from standoff import Textbound, Normalization
from common import read_streams
from common import get_norm_name, get_norm_id, rewrite_norm_id

try:
    import sqlitedict
except ImportError:
    error('failed to import sqlitedict; try `pip3 install sqlitedict`')
    raise


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('-l', '--limit', type=int, metavar='INT', default=None,
                    help='maximum number of documents to convert')
    ap.add_argument('-e', '--entitydb', default=None,
                    help='sqlite DB mapping tagger IDs to external IDs')
    ap.add_argument('-n', '--namedb', default=None,
                    help='sqlite DB mapping tagger IDs to names')
    ap.add_argument('-d', '--directory', default=None,
                    help='output directory (default STDOUT)')
    ap.add_argument('-D', '--database', default=None,
                    help='output database (default STDOUT)')
    ap.add_argument('-P', '--dir-prefix', type=int, default=None,
                    help='add subdirectories with given length doc ID prefix')
    ap.add_argument('docs', help='tsv file with document text and data')
    ap.add_argument('tags', help='tsv file with tags for documents')
    return ap


def mentions_to_standoffs(mentions, options):
    standoffs = []
    # Mentions with identical span and type map to one textbound with
    # multiple normalizations.
    grouped = defaultdict(list)
    for m in mentions:
        grouped[(m.start, m.end, m.typename, m.text)].append(m)
    t_idx, n_idx = count(1), count(1)
    for (start, end, type_, text), group in sorted(grouped.items()):
        t_id = 'T{}'.format(next(t_idx))
        standoffs.append(Textbound(t_id, type_, start, end, text))
        for m in group:
            n_id = 'N{}'.format(next(n_idx))
            n_name = get_norm_name(m.serial, m.text, options)
            # if we have a species name, add it to the norm text
            if m.species:
                n_name = n_name + ' ({})'.format(m.species)
            norm_id = get_norm_id(m.serial, 'TAGGER:{}'.format(m.serial),
                                  options)
            norm_id = rewrite_norm_id(norm_id, type_, m.species)
            standoffs.append(Normalization(n_id, t_id, norm_id, n_name))
    return standoffs


def skippable_line(line):
    # empty lines and comments are skippable
    return len(line) == 0 or line.isspace() or line[0] == '#'


def output_directory(doc_id, options):
    """Return directory to store document with given ID in."""
    assert options.directory, 'internal error'
    if options.dir_prefix is None:
        return options.directory
    else:
        return os.path.join(options.directory, doc_id[:options.dir_prefix])


# https://stackoverflow.com/a/600612
def mkdir_p(path):
    if path in mkdir_p.known_to_exist:
        return
    try:
        os.makedirs(path)
        mkdir_p.known_to_exist.add(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            mkdir_p.known_to_exist.add(path)
        else:
            raise
mkdir_p.known_to_exist = set()


def write_standoff(document, mentions, options):
    standoffs = mentions_to_standoffs(mentions, options)
    if options.directory is None and options.database is None:    # STDOUT
        print(document)
        for s in standoffs:
            print(s)
    elif options.database is not None:
        txt_key = '{}.txt'.format(document.pmid)
        ann_key = '{}.ann'.format(document.pmid)
        options.database[txt_key] = str(document)
        options.database[ann_key] = '\n'.join(str(s) for s in standoffs)
    else:
        outdir = output_directory(document.pmid, options)
        mkdir_p(outdir)
        txt_fn = os.path.join(outdir, '{}.txt'.format(document.pmid))
        ann_fn = os.path.join(outdir, '{}.ann'.format(document.pmid))
        with open(txt_fn, 'w', encoding='utf-8') as txt_f:
            print(document, file=txt_f)
        with open(ann_fn, 'w', encoding='utf-8') as ann_f:
            for s in standoffs:
                print(s, file=ann_f)
              

def process(docfn, tagfn, options):
    count = 0
    with open(docfn, encoding='utf-8') as docf:
        with open(tagfn, encoding='utf-8') as tagf:
            for document, mentions in read_streams(docf, tagf):
                if options.limit and count >= options.limit:
                    break
                write_standoff(document, mentions, options)
                count += 1
                if count % 1024 == 0:
                    print('Processed {} ...'.format(count), end='\r',
                          file=sys.stderr, flush=True)
                if options.database and count % 10000 == 0:
                    print('Processed {}, committing ...'.format(count),
                          file=sys.stderr)
                    options.database.commit()
    print('Done, processed {} documents.'.format(count), file=sys.stderr)
    if options.database:
        print('Committing ...', end='', flush=True, file=sys.stderr)
        options.database.commit()
        print('done.', file=sys.stderr)
    return count


def open_db(fn, flag='r'):
    if not os.path.exists(fn):
        raise IOError("no such file: '{}'".format(fn))
    return sqlitedict.SqliteDict(fn, flag=flag)


def main(argv):
    args = argparser().parse_args(argv[1:])
    if args.directory and args.database:
        error('cannot output to both --directory and --database')
        return 1
    if args.database:
        args.database = sqlitedict.SqliteDict(args.database)
    if args.entitydb is not None:
        args.entitydb = open_db(args.entitydb)
    if args.namedb is not None:
        args.namedb = open_db(args.namedb)
    count = process(args.docs, args.tags, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
