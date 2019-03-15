#!/usr/bin/env python3

import sys
import os

import itertools
import collections

from itertools import tee, count
from collections import defaultdict
from logging import error


def argparser():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument('-d', '--directory', default=None,
                    help='Output directory (default STDOUT)')
    ap.add_argument('docs', help='tsv file with document text and data')
    ap.add_argument('tags', help='tsv file with tags for documents')
    return ap


# From https://bitbucket.org/larsjuhljensen/tagger/
TYPE_MAP = {
    -1: 'Chemical',
    -2:	'Organism',    # NCBI species taxonomy id (tagging species)
    -3:	'Organism',    # NCBI species taxonomy id (tagging proteins)
    -11: 'Wikipedia',
    -21: 'Biological_process',    # GO biological process
    -22: 'Cellular_component',    # GO cellular component
    -23: 'Molecular_function',    # GO molecular function
    -24: 'GO_other',    # GO other (unused)
    -25: 'Tissue',    # BTO tissues
    -26: 'Disease',    # DOID diseases
    -27: 'Environment',    # ENVO environments
    -28: 'Phenotype',    # APO phenotypes
    -29: 'Phenotype',    # FYPO phenotypes
    -30: 'Phenotype',    # MPheno phenotypes
    -31: 'Behaviour',    # NBO behaviors
    -36: 'Phenotype',	 # mammalian phenotypes
}


def typename_and_species(type_):
    if type_ > 0:    # Gene/protein of species with this NCBI tax id
        return ('Gene', 'TODO')
    elif type_ < 0 and type_ in TYPE_MAP:    # Lookup, no species information
        return (TYPE_MAP[type_], None)
    else:
        assert 'Unexpected type {}'.format(type_)

        
class FormatError(Exception):
    pass


class LookaheadIterator(collections.abc.Iterator):
    """Lookahead iterator from http://stackoverflow.com/a/1518097."""

    def __init__(self, it, start=0):
        self._it, self._nextit = tee(iter(it))
        self.index = start - 1
        self._advance()

    def _advance(self):
        self.lookahead = next(self._nextit, None)
        self.index = self.index + 1

    def __next__(self):
        self._advance()
        return next(self._it)

    def __bool__(self):
        return self.lookahead is not None


class Document(object):
    def __init__(self, id_, authors, journal, year, title, abstract):
        self.id = id_
        self.pmid = id_[5:] if id_.startswith('PMID:') else None
        self.authors = authors
        self.journal = journal
        self.year = year
        self.title = title
        self.abstract = abstract

    @property
    def text(self):
        return self.title + '\n' + self.abstract

    def __str__(self):
        return self.text
    
    @classmethod
    def from_tsv(cls, line, ln, fn):
        line = line.rstrip('\n')
        fields = line.split('\t')
        if len(fields) != 6:
            raise FormatError('line {} in {}: expected 6 fields, got {}: {}'.\
                              format(ln, fn, len(fields), line))
        return cls(*fields)


class Mention(object):
    def __init__(self, pmid, para, sent, start, end, text, type_, serial):
        self.pmid = pmid
        self.para = int(para)    # paragraph number
        self.sent = int(sent)    # sentence number
        self.start = int(start)
        self.end = int(end) + 1  # adjust inclusive to exclusive
        self.text = text
        self.type = int(type_)
        self.serial = serial

        self.typename, self.organism = typename_and_species(self.type)

    def validate_text(self, text):
        ref = text[self.start: self.end]
        assert self.text == ref, 'Text mismatch in {}: "{}" vs "{}"'.format(
            self.pmid, self.text, ref)

    def to_standoff(self):
        return [
            'T0\t{} {} {}\t{}'.format(
                self.typename, self.start, self.end, self.text)
        ]
    
    @classmethod
    def from_tsv(cls, line, ln, fn):
        line = line.rstrip('\n')
        fields = line.split('\t')
        if len(fields) != 8:
            raise FormatError('line {} in {}: expected 8 fields, got {}: {}'.\
                              format(ln, fn, len(fields), line))
        return cls(*fields)


class Textbound(object):
    def __init__(self, id_, type_, start, end, text):
        self.id = id_
        self.type = type_
        self.start = start
        self.end = end
        self.text = text

    def __str__(self):
        return '{}\t{} {} {}\t{}'.format(
            self.id, self.type, self.start, self.end, self.text)


class Normalization(object):
    def __init__(self, id_, tb_id, norm_id, text):
        self.id = id_
        self.tb_id = tb_id
        self.norm_id = norm_id
        self.text = text

    def __str__(self):
        return '{}\tReference {} {}\t{}'.format(
            self.id, self.tb_id, self.norm_id, self.text)


def mentions_to_standoffs(mentions):
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
            standoffs.append(Normalization(
                n_id, t_id, 'TAGGER:{}'.format(m.serial), m.text))
    return standoffs


def read_streams(docs, tags):
    tag_it = LookaheadIterator(tags, start=1)
    for doc_ln, doc_line in enumerate(docs, start=1):
        document = Document.from_tsv(doc_line, doc_ln, docs.name)
        doc_text = document.text
        mentions = []
        while tag_it and tag_it.lookahead.split('\t')[0] == document.pmid:
            tag_line, tag_ln = next(tag_it), tag_it.index
            mention = Mention.from_tsv(tag_line, tag_ln, tags.name)
            mention.validate_text(doc_text)
            mentions.append(mention)
        yield document, mentions
    for l in tag_it:
        warning('Extra line {} in {}: {}'.format(tag_it.index, tags.name, l))


def write_standoff(document, mentions, options):
    if options.directory is None:    # STDOUT
        print(document)
        for m in mentions_to_standoffs(mentions):
            print(m)
    else:
        txt_fn = os.path.join(options.directory, '{}.txt'.format(document.pmid))
        ann_fn = os.path.join(options.directory, '{}.ann'.format(document.pmid))
        with open(txt_fn, 'w', encoding='utf-8') as txt_f:
            print(document, file=txt_f)
        with open(ann_fn, 'w', encoding='utf-8') as ann_f:
            for m in mentions_to_standoffs(mentions):
                print(m, file=ann_f)
              

def process(docfn, tagfn, options):
    with open(docfn, encoding='utf-8') as docf:
        with open(tagfn, encoding='utf-8') as tagf:
            for document, mentions in read_streams(docf, tagf):
                write_standoff(document, mentions, options)


def main(argv):
    args = argparser().parse_args(argv[1:])
    process(args.docs, args.tags, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
