#!/usr/bin/env python3

from __future__ import print_function

import os
import sys
import requests

from logging import error


DEFAULT_URL = 'http://tagger.jensenlab.org/ExtractPopup'

ENTITY_TYPES = [
    '0',      # Genes/proteins
    '-1',     # PubChem Compound identifiers
    '-2',     # NCBI Taxonomy entries
#    '-21',    # Gene Ontology biological process terms
#    '-22',    # Gene Ontology cellular component terms
#    '-23',    # Gene Ontology molecular function terms
#    '-25',    # BRENDA Tissue Ontology terms
    '-26',    # Disease Ontology terms
#    '-27',    # Environment Ontology terms
]

def argparser():
    import argparse
    ap = argparse.ArgumentParser(description='Invoke EXTRACT tagger on text(s)')
    ap.add_argument('-d', '--directory', default=None,
                    help='Output directory (default STDOUT)')
    ap.add_argument('-u', '--url', default=DEFAULT_URL,
                    help='EXTRACT tagger URL (default {})'.format(DEFAULT_URL))
    ap.add_argument('files', nargs='+', metavar='FILE', help='Input text')
    return ap


def extract_request(url, text):
    post_data = {
        'document': text,
        'entity_types': ' '.join(ENTITY_TYPES)
    }
    r = requests.post(url, data=post_data)
    return r.text


def write_response(fn, response, options):
    if options.directory is None:
        print(response)
    else:
        bn = os.path.splitext(os.path.basename(fn))[0]+'.html'
        ofn = os.path.join(options.directory, bn)
        with open(ofn, 'w') as out:
            print(response, file=out)


def main(argv):
    args = argparser().parse_args(argv[1:])

    for fn in args.files:
        with open(fn) as f:
            text = f.read()
        try:
            response = extract_request(args.url, text)
        except Exception as e:
            error('failed for {}: {}'.format(fn, e))
            continue
        write_response(fn, response, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
