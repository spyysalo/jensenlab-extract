#!/usr/bin/env python3

# Convert HTML returned by http://tagger.jensenlab.org/ExtractPopup
# into brat-flavoured standoff (http://brat.nlplab.org/standoff.html).

import sys
import os

from collections import defaultdict
from html.parser import HTMLParser
from logging import warn, error


EXTRACT_DATA_CONTENT_CLASS = 'content'
EXTRACT_DATA_DIV_CLASS = 'ajax_table'
EXTRACT_MATCH_CLASS = 'extract_match'
EXTRACT_TYPE_CLASS = 'type'
EXTRACT_NAME_CLASS = 'name'
EXTRACT_ID_CLASS = 'identifier'
EXTRACT_ID_ROW_CLASSES = set(['even', 'odd'])


# Type rewrites
EXTRACT_TYPE_MAP = {
    'Arabidopsis thaliana gene': 'Gene',
    'Bos taurus gene': 'Gene',
    'Caenorhabditis elegans gene': 'Gene',
    'Danio rerio gene': 'Gene',
    'Drosophila melanogaster gene': 'Gene',
    'Gallus gallus gene': 'Gene',
    'Homo sapiens gene': 'Gene',
    'Mus musculus gene': 'Gene',
    'Rattus norvegicus gene': 'Gene',
    'Saccharomyces cerevisiae gene': 'Gene',
    'Schizosaccharomyces pombe gene': 'Gene',
    'Sus scrofa gene': 'Gene',
}


def argparser():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('-d', '--directory', default=None,
                    help='Output directory')
    ap.add_argument('files', metavar='FILE', nargs='+', help='Input files')
    return ap


class ExtractHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_content_div = False
        self.in_data_div = False
        self.in_data_paragraph = False
        self.in_match_span = False
        self.in_id_row = False
        self.starttag_handler = {
            'div': self.handle_div_starttag,
            'p': self.handle_p_starttag,
            'span': self.handle_span_starttag,
            'tr': self.handle_tr_starttag,
            'td': self.handle_td_starttag,
        }
        self.endtag_handler = {
            'div': self.handle_div_endtag,
            'p': self.handle_p_endtag,
            'span': self.handle_span_endtag,
            'tr': self.handle_tr_endtag,
            'td': self.handle_td_endtag,
        }
        self.texts = []
        self.current_offset = 0
        self.current_ids = []
        self.spans = []
        self.current_td_classes = None
        self.current_id_name = None
        self.current_id_type = None
        self.current_id_id = None
        self.identifiers = []
        
    def handle_div_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if attr_dict.get('class') == EXTRACT_DATA_CONTENT_CLASS:
            self.in_content_div = True
        elif self.in_content_div and \
             attr_dict.get('class') == EXTRACT_DATA_DIV_CLASS:
            self.in_data_div = True
        else:
            self.in_content_div = False
            self.in_data_div = False
            self.in_data_paragraph = False
            self.in_match_span = False

    def handle_div_endtag(self, tag):
        self.in_content_div = False
        self.in_data_div = False
        self.in_data_paragraph = False
        self.in_match_span = False

    def handle_p_starttag(self, tag, attrs):
        if self.in_data_div:
            self.in_data_paragraph = True
        else:
            self.in_data_paragraph = False
            self.in_match_span = False

    def handle_p_endtag(self, tag):
        self.in_data_paragraph = False
        self.in_match_span = False

    def handle_span_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = attr_dict.get('class', '').split(' ')
        if self.in_data_paragraph and EXTRACT_MATCH_CLASS in classes:
            self.in_match_span = True
            self.current_ids = [i for i in classes if i != EXTRACT_MATCH_CLASS]

    def handle_span_endtag(self, tag):
        self.in_match_span = False

    def handle_tr_starttag(self, tag, attrs):
        classes = dict(attrs).get('class', '').split(' ')
        if any(c for c in classes if c in EXTRACT_ID_ROW_CLASSES):
            self.in_id_row = True
        else:
            self.in_id_row = False
        self.current_id_name = None
        self.current_id_type = None
        self.current_id_id = None

    def handle_tr_endtag(self, tag):
        if self.in_id_row:
            self.identifiers.append((self.current_id_name,
                                     self.current_id_type,
                                     self.current_id_id))
        self.in_id_row = False
        self.current_id_name = None
        self.current_id_type = None
        self.current_id_id = None

    def handle_td_starttag(self, tag, attrs):
        self.current_td_classes = dict(attrs).get('class', '').split(' ')

    def handle_td_endtag(self, tag):
        self.current_td_classes = None

    def handle_starttag(self, tag, attrs):
        if tag in self.starttag_handler:
            self.starttag_handler[tag](tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.endtag_handler:
            self.endtag_handler[tag](tag)

    def handle_data(self, data):
        if self.in_data_paragraph:
            if self.in_match_span:
                start = self.current_offset
                end = self.current_offset + len(data)
                ids = self.current_ids
                if not ids:
                    warn('missing ids for span')
                self.spans.append((start, end, ids))
            self.texts.append(data)
            self.current_offset += len(data)
        elif self.current_td_classes is not None:
            if EXTRACT_TYPE_CLASS in self.current_td_classes:
                self.current_id_type = data
            elif EXTRACT_NAME_CLASS in self.current_td_classes:
                self.current_id_name = data
            elif EXTRACT_ID_CLASS in self.current_td_classes:
                self.current_id_id = data


def create_id_map(identifiers):
    id_map = {}
    for name, type_, id_ in identifiers:
        if id_ in id_map and id_map[id_] != (name, type_):
            error('conflicting data for {}: {} vs {}'.\
                  format(id_, id_map[id_], (name, type_)))
        id_map[id_] = (name, type_)
    return id_map


def rewrite_type(type_):
    type_ = EXTRACT_TYPE_MAP.get(type_, type_)
    return type_.replace(' ', '_')


def rewrite_id(id_, type_):
    # Rewrite EXTRACT IDs to NAMESPACE:ID format
    if type_.startswith('Chemical') and id_.startswith('CIDs'):
        id_ = id_.replace('CIDs', 'CID:', 1)
    elif type_ == 'Organism' and id_.isdigit():
        id_ = 'NCBITaxon:{}'.format(id_)
    elif type_.endswith('gene'):
        if type_ == 'Arabidopsis thaliana gene' and id_.startswith('AT'):
            id_ = id_.replace('AT', 'AT:', 1)    # TAIR (A. thaliana)
        elif type_ == 'Drosophila melanogaster gene' and id_.startswith('FB'):
            id_ = id_.replace('FB', 'FB:', 1)    # Flybase
        elif type_ == 'Schizosaccharomyces pombe gene' and id_.startswith('SP'):
            id_ = id_.replace('SP', 'SP:', 1)    # PomBase (S. pombe)
        elif type_ == 'Caenorhabditis elegans gene' and ':' not in id_:
            id_ = 'WB:{}'.format(id_)    # WormBase
        elif type_ == 'Saccharomyces cerevisiae gene' and ':' not in id_:
            id_ = 'SGD:{}'.format(id_)    # SGD (S. cerevisiae)
        elif id_.startswith('ENS'):
            id_ = id_.replace('ENS', 'ENS:', 1)    # Ensembl
    return id_


def group_by_type(ids, id_map):
    # A span can be annotated with IDs corresponding to more than one
    # upper-level type. Group by (abbreviated) types for output in standoff.
    grouped = defaultdict(list)
    for id_ in ids:
        if id_ not in id_map:
            error('missing id: {}'.format(id_))
            continue
        name, type_ = id_map[id_]
        short_type = rewrite_type(type_)
        grouped[short_type].append((name, id_, type_))
    return grouped


def write_standoff(fn, text, spans, identifiers, options):
    id_map = create_id_map(identifiers)
    txt_fn = os.path.splitext(os.path.basename(fn))[0] + '.txt'
    ann_fn = os.path.splitext(os.path.basename(fn))[0] + '.ann'
    if options.directory is not None:
        txt_fn = os.path.join(options.directory, txt_fn)
        ann_fn = os.path.join(options.directory, ann_fn)
    with open(txt_fn, 'w') as out:
        print(text, file=out)
    with open(ann_fn, 'w') as out:
        t_seq, n_seq = 1, 1
        for start, end, ids in spans:
            ref = text[start:end]
            grouped = group_by_type(ids, id_map)
            for type_, name_id_origtype_list in grouped.items():
                print('T{}\t{} {} {}\t{}'.format(t_seq, type_, start, end, ref),
                      file=out)
                for name, id_, orig_type in name_id_origtype_list:
                    id_ = rewrite_id(id_, orig_type)
                    print('N{}\tReference T{} {}\t{}'.\
                          format(n_seq, t_seq, id_, name), file=out)
                    n_seq += 1
                t_seq += 1


def process(fn, options):
    parser = ExtractHTMLParser()
    with open(fn) as f:
        for l in f:
            parser.feed(l)
    text = ''.join(parser.texts)
    write_standoff(fn, text, parser.spans, parser.identifiers, options)


def main(argv):
    args = argparser().parse_args(argv[1:])
    for fn in args.files:
        process(fn, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
