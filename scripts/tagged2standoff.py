#!/usr/bin/env python3

import sys
import os
import errno

import itertools
import collections

from itertools import tee, count
from collections import defaultdict
from logging import info, warning, error

from standoff import Textbound, Normalization

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

# From NCBI Taxonomy
TAXID_NAME_MAP = {
    3702: 'Arabidopsis thaliana',
    4896: 'Schizosaccharomyces pombe',
    4932: 'Saccharomyces cerevisiae',
    6239: 'Caenorhabditis elegans',
    7227: 'Drosophila melanogaster',
    7955: 'Danio rerio',
    9031: 'Gallus gallus',
    9606: 'Homo sapiens',
    9823: 'Sus scrofa',
    9913: 'Bos taurus',
    10090: 'Mus musculus',
    10116: 'Rattus norvegicus',
}

def load_taxid_name_map(fn):
    taxid_name_map = {}
    try:
        print('loading taxid-name map from {} ... '.format(fn),
              end='', file=sys.stderr, flush=True)
        with open(fn) as f:
            for line in f:
                id_, name = line.rstrip('\n').split('\t')
                taxid_name_map[int(id_)] = name
        print('done.', file=sys.stderr)
    except Exception as e:
        error('failed to load {}: {}'.format(fn, e))
        return None
    return taxid_name_map


def get_taxname(taxid):
    """Return scientific name for NCBI Taxonomy ID."""
    if get_taxname.id_name_map is None:
        get_taxname.id_name_map = load_taxid_name_map('data/taxnames.tsv')
        if get_taxname.id_name_map is None:    # assume fail, fallback
            get_taxname.id_name_map = TAXID_NAME_MAP
    return get_taxname.id_name_map.get(taxid, '<UNKNOWN>')
get_taxname.id_name_map = None


def typename_and_species(type_):
    if type_ > 0:    # Gene/protein of species with this NCBI tax id
        return ('Gene', get_taxname(type_))
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
        if len(fields) == 5:
            info('line {} in {}: got 5 fields; assuming empty abstract'.\
                 format(ln, fn))
            fields.append('')
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
        self.serial = int(serial)

        self.typename, self.species = typename_and_species(self.type)

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


def get_norm_name(id_, default, options):
    if id_ not in get_norm_name._cache:
        if options.namedb is None:
            return default
        else:
            get_norm_name._cache[id_] = options.namedb.get(id_, default)
    return get_norm_name._cache[id_]
get_norm_name._cache = {}


def get_norm_id(id_, default, options):
    if id_ not in get_norm_id._cache:
        if options.entitydb is None:
            return default
        else:
            get_norm_id._cache[id_] = options.entitydb.get(id_, default)
    return get_norm_id._cache[id_]
get_norm_id._cache = {}


def rewrite_norm_id(id_, type_, species):
    # Rewrite tagger IDs to NAMESPACE:ID format
    if type_.startswith('Chemical') and id_.startswith('CIDs'):
        id_ = id_.replace('CIDs', 'CID:', 1)
    elif type_ == 'Organism' and id_.isdigit():
        id_ = 'NCBITaxon:{}'.format(id_)
    elif type_ == 'Gene':
        if species == 'Arabidopsis thaliana' and id_.startswith('AT'):
            id_ = id_.replace('AT', 'AT:', 1)    # TAIR (A. thaliana)
        elif species == 'Drosophila melanogaster' and id_.startswith('FB'):
            id_ = id_.replace('FB', 'FB:', 1)    # Flybase
        elif species == 'Schizosaccharomyces pombe' and id_.startswith('SP'):
            id_ = id_.replace('SP', 'SP:', 1)    # PomBase (S. pombe)
        elif species == 'Caenorhabditis elegans' and ':' not in id_:
            id_ = 'WB:{}'.format(id_)    # WormBase
        elif species == 'Saccharomyces cerevisiae' and ':' not in id_:
            id_ = 'SGD:{}'.format(id_)    # SGD (S. cerevisiae)
        elif id_.startswith('ENS'):
            id_ = id_.replace('ENS', 'ENS:', 1)    # Ensembl
    return id_


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


def read_streams(docs, tags):
    tag_it = LookaheadIterator(tags, start=1)
    for doc_ln, doc_line in enumerate(docs, start=1):
        document = Document.from_tsv(doc_line, doc_ln, docs.name)
        doc_text = document.text
        mentions = []
        while tag_it:
            if skippable_line(tag_it.lookahead):
                tag_line, tag_ln = next(tag_it), tag_it.index
                warning('skipping line {} in {}: {}'.format(
                    tag_ln, tags.name, tag_line.rstrip('\n')))
                continue
            elif tag_it.lookahead.split('\t')[0] != document.pmid:
                break    # tagged for next document
            tag_line, tag_ln = next(tag_it), tag_it.index
            mention = Mention.from_tsv(tag_line, tag_ln, tags.name)
            mention.validate_text(doc_text)
            mentions.append(mention)
        yield document, mentions
    for i, l in enumerate(tag_it, start=1):
        l = l.rstrip('\n')
        warning('extra line {} in {}: {}'.format(tag_it.index, tags.name, l))
        if i >= 10:
            warning('{} extra lines, ignoring rest'.format(i))
            break


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
