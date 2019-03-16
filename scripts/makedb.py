#!/usr/bin/env python3

import sys
import os

from logging import error

try:
    import sqlitedict
except ImportError:
    error('failed to import sqlitedict; try `pip3 install sqlitedict`')
    raise


DEFAULT_INTERVAL = 10**6

DEFAULT_MAXERR = 100


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('-i', '--commit-interval', metavar='INT', type=int,
                    default=DEFAULT_INTERVAL,
                    help='number of items to input between commits')
    ap.add_argument('-e', '--max-errors', metavar='INT', type=int,
                    default=DEFAULT_MAXERR,
                    help='maximum number of errors to ignore')
    ap.add_argument('dict', help='input dictionary in key-value TSV format')
    ap.add_argument('dbname', help='output database name')
    return ap


def process_interval(in_, dbname, idx, end, limit, options):
    seen_keys = process_interval.seen_keys
    end = min(end, limit)
    with sqlitedict.SqliteDict(dbname, autocommit=False) as db:
        while idx < end:
            ln = idx + 1
            try:
                line = next(in_)
            except StopIteration:
                error('unexpected EOF in {} at line {}'.format(in_.name, ln))
                break
            try:
                line = line.decode('utf-8')
                fields = line.rstrip('\n').split('\t')
                key, value = fields
                key = int(key)
                if key not in seen_keys:    # only add first
                    db[key] = value
                    seen_keys.add(key)
            except Exception as e:
                error('on line {} in {} (skip): {}'.format(ln, in_.name, e))
                options.max_errors -= 1
                if options.max_errors <= 0:
                    raise RuntimeError('max-errors exceeded, aborting.')
            if ln % 1024 == 0:
                print('Read {}/{} ({:.1%}) lines'.format(ln, limit, ln/limit),
                      end='\r', file=sys.stderr, flush=True)
            idx += 1
        print('Read {}/{} ({:.1%}) lines, committing...'.format(
            ln, limit, ln/limit), end='', file=sys.stderr, flush=True)
        db.commit()
        print('done.', file=sys.stderr)
    return idx
process_interval.seen_keys = set()


def process(in_, dbname, total_lines, options):
    print('Reading from {} ...'.format(in_.name), file=sys.stderr)
    idx, interval = 0, options.commit_interval
    while idx < total_lines:
        nxt = process_interval(in_, dbname, idx, idx+interval, total_lines,
                               options)
        if nxt == idx:
            break    # failed to progress
        idx = nxt
    unique = len(process_interval.seen_keys)
    ratio = 0 if idx == 0 else unique/idx
    print('Finished: read {}, stored {} unique ({:.1%}).'.format(
        idx, unique, ratio, file=sys.stderr))


def count_lines(fn):
    return sum(1 for l in open(fn, 'rb'))


def main(argv):
    args = argparser().parse_args(argv[1:])
    line_count = count_lines(args.dict)
    with open(args.dict, 'rb') as in_:
        process(in_, args.dbname, line_count, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
