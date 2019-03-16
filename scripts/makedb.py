#!/usr/bin/env python3

import sys
import os

from logging import error


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('dict', help='input dictionary in key-value TSV format')
    ap.add_argument('dbname', help='output database name')
    return ap


def process(in_, dbname, lines, options):
    try:
        import sqlitedict
    except ImportError:
        error('failed to import sqlitedict; try `pip3 install sqlitedict`')
        raise

    seen_keys = set()
    print('Reading from {} ...'.format(in_.name), file=sys.stderr)
    with sqlitedict.SqliteDict(dbname, autocommit=False) as db:
        for ln, line in enumerate(in_, start=1):
            try:
                fields = line.rstrip('\n').split('\t')
                key, value = fields
                key = int(key)
                if key not in seen_keys:    # only add first
                    db[key] = value
                    seen_keys.add(key)
            except Exception as e:
                error('on line {} in {}: {}'.format(ln, in_.name, line))
                raise
            if ln % 1024 == 0:
                print('Read {}/{} ({:.1%}) lines'.format(ln, lines, ln/lines),
                      end='\r', file=sys.stderr, flush=True)
        print('Read {}/{} ({:.0%}) lines, committing...'.format(
            ln, lines, ln/lines), end='', file=sys.stderr, flush=True)
        db.commit()
    print('done.', file=sys.stderr)
    print('Print read {}, stored {} unique ({:.1%}).'.format(
        ln, len(seen_keys), len(seen_keys)/ln, file=sys.stderr))


def count_lines(fn):
    return sum(1 for l in open(fn))


def main(argv):
    args = argparser().parse_args(argv[1:])
    line_count = count_lines(args.dict)
    with open(args.dict) as in_:
        process(in_, args.dbname, line_count, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
