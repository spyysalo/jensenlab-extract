import sys
import collections

from itertools import tee
from logging import info, warning, error


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


def typename_and_species(type_):
    if type_ > 0:    # Gene/protein of species with this NCBI tax id
        return ('Gene', get_taxname(type_))
    elif type_ < 0 and type_ in TYPE_MAP:    # Lookup, no species information
        return (TYPE_MAP[type_], None)
    else:
        assert 'Unexpected type {}'.format(type_)


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
