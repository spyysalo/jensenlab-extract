#!/usr/bin/env python3

import sys
import os
import re
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
    ap.add_argument('-n', '--names', default=False, action='store_true',
                    help='include entity names in output')
    ap.add_argument('-w', '--words', metavar='NUM', default=None, type=int,
                    help='number of context words to include')
    ap.add_argument('-l', '--limit', type=int, metavar='INT', default=None,
                    help='maximum number of documents to convert')
    ap.add_argument('docs', help='tsv file with document text and data')
    ap.add_argument('tags', help='tsv file with tags for documents')
    ap.add_argument('entitydb', help='DB mapping tagger IDs to external IDs')
    ap.add_argument('namedb', help='DB mapping tagger IDs to names')
    return ap


def get_words(text, maximum, reverse=False):
    split = re.split(r'(\s+)', text)
    if reverse:
        split = reversed(split)
    words, count = [], 0
    for w in split:
        if count >= maximum:
            break
        words.append(w)
        if not w.isspace():
            count += 1
    if reverse:
        words = reversed(words)
    text = ''.join(words)
    return text.replace('\n', ' ').replace('\t', ' ')    # normalize space for TSV


def output(document, mentions, options):
    for m in mentions:
        norm_name = get_norm_name(m.serial, m.text, options)
        # if we have a species name, add it to the norm text
        if m.species:
            norm_name = norm_name + ' ({})'.format(m.species)
        norm_id = get_norm_id(m.serial, 'TAGGER:{}'.format(m.serial), options)
        norm_id = rewrite_norm_id(norm_id, m.typename, m.species)
        # NOTE: end-1 to revert exclusive to inclusive (see Mention.__init__)
        fields = [m.pmid, m.para, m.sent, m.start, m.end-1, m.text,
                  m.typename, norm_id]
        if options.names:
            fields.append(norm_name)
        if options.words is not None:
            doctext = document.text
            before = get_words(doctext[:m.start], options.words, reverse=True)
            after = get_words(doctext[m.end:], options.words, reverse=False)
            fields.append('{}<<<{}>>>{}'.format(before, m.text, after))
        print('\t'.join(str(i) for i in fields))


def process(docfn, tagfn, options):
    count = 0
    with open(docfn, encoding='utf-8') as docf:
        with open(tagfn, encoding='utf-8') as tagf:
            for document, mentions in read_streams(docf, tagf):
                if options.limit and count >= options.limit:
                    break
                output(document, mentions, options)
                count += 1
                if count % 1024 == 0:
                    print('Processed {} ...'.format(count), end='\r',
                          file=sys.stderr, flush=True)
    print('Done, processed {} documents.'.format(count), file=sys.stderr)
    return count


def open_db(fn, flag='r'):
    if not os.path.exists(fn):
        raise IOError("no such file: '{}'".format(fn))
    return sqlitedict.SqliteDict(fn, flag=flag)


def main(argv):
    args = argparser().parse_args(argv[1:])
    args.entitydb = open_db(args.entitydb)
    args.namedb = open_db(args.namedb)
    count = process(args.docs, args.tags, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
