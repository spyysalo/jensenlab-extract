#!/usr/bin/env python3

# Compare two sets of brat-flavored annotations. (Incomplete: does
# not support all annotation types.)

import sys
import os

from collections import defaultdict
from itertools import chain
from logging import warning, info


TYPE_MAP = {
    # EVEX
    'cel': 'Cell',
    'che': 'Chemical',
    'dis': 'Disease',
    'ggp': 'Gene',
    'org': 'Organism',
    # EXTRACT
    'Chemical_compound': 'Chemical',
}


def argparser():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('-f', '--filtertypes', metavar='TYPE[,TYPE ...]',
                    default=None, help='Filter out annotations by type')
    ap.add_argument('-m', '--maptypes', default=False, action='store_true',
                    help='Apply mapping to type names (consistency)')
    ap.add_argument('-M', '--forcemap', default=False, action='store_true',
                    help='Always map types when mapping exists')
    ap.add_argument('-r', '--retype',
                    metavar='FROM:TO:FILE[;FROM:TO:FILE ...]',
                    help='Retype annotations with norm ID in file.')
    ap.add_argument('-s', '--suffix', default='.ann',
                    help='Suffix of files to compare')
    ap.add_argument('set1', metavar='FILE/DIR')
    ap.add_argument('set2', metavar='FILE/DIR')
    return ap


class FormatError(Exception):
    pass


class Textbound(object):
    def __init__(self, id_, type_, span, text):
        self.id = id_
        self.type = type_
        self.span = span
        self.text = text
        self.start, self.end = Textbound.parse_span(span)
        self.normalizations = []

    def __str__(self):
        return '{}\t{} {}\t{}'.format(self.id, self.type, self.span, self.text)

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def parse_span(span):
        start, end = span.split(' ')
        start = int(start)
        end = int(end)
        return start, end

    @classmethod
    def from_standoff(cls, line):
        id_, type_span, text = line.split('\t')
        type_, span = type_span.split(' ', 1)
        return cls(id_, type_, span, text)


class Normalization(object):
    def __init__(self, id_, type_, tb_id, norm_id, text):
        self.id = id_
        self.type = type_
        self.tb_id = tb_id
        self.norm_id = norm_id
        self.text = text

    def __str__(self):
        return '{}\t{} {} {}\t{}'.format(self.id, self.type, self.tb_id,
                                         self.norm_id, self.text)

    def __repr__(self):
        return self.__str__()
        
    @classmethod
    def from_standoff(cls, line):
        id_, type_ids, text = line.split('\t')
        type_, tb_id, norm_id = type_ids.split(' ')
        return cls(id_, type_, tb_id, norm_id, text)


def parse_standoff(fn):
    textbounds = []
    normalizations = []
    with open(fn) as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip('\n')
            if not l or l.isspace():
                continue
            elif l[0] == 'T':
                textbounds.append(Textbound.from_standoff(l))
            elif l[0] == 'N':
                normalizations.append(Normalization.from_standoff(l))
            else:
                warning('skipping line {} in {}: {}'.format(ln, fn, l))
                continue

    # Attach normalizations to textbounds
    tb_by_id = {}
    for t in textbounds:
        tb_by_id[t.id] = t
    for n in normalizations:
        tb_by_id[n.tb_id].normalizations.append(n)

    return textbounds


def maptype(type_):
    return TYPE_MAP.get(type_, type_)


def types_match(type1, type2, text, options):
    if not options.maptypes:
        match = type1 == type2
    else:
        match = (type1 == type2 or maptype(type1) == type2 or
                 type1 == maptype(type2) or maptype(type1) == maptype(type2))
    if match:
        print('type match: "{}" vs "{}" ("{}")'.format(type1, type2, text))
    if not match:
        print('TYPE MISMATCH: "{}" vs "{}" ("{}")'.format(type1, type2, text))
    return match


def filter_by_type(annotations, filtered):
    return [a for a in annotations if a.type not in filtered]


def apply_type_mapping(annotations, type_map):
    for a in annotations:
        a.type = type_map.get(a.type, a.type)
    return annotations


def retype_by_norm(annotations, from_to_ids_list):
    for a in annotations:
        for from_, to_, ids in from_to_ids_list:
            if (a.type == from_ and
                any(n for n in a.normalizations if n.norm_id in ids)):
                print('NOTE: Retype to {}: {}'.format(to_, a))
                a.type = to_
    return annotations


def compare_files(file1, file2, options, stats):
    assert os.path.isfile(file1) and os.path.isfile(file2)

    ann1 = parse_standoff(file1)
    ann2 = parse_standoff(file2)
    if options.retype:
        ann1 = retype_by_norm(ann1, options.retype)
        ann2 = retype_by_norm(ann2, options.retype)
    if options.filtertypes:
        ann1 = filter_by_type(ann1, options.filtertypes)
        ann2 = filter_by_type(ann2, options.filtertypes)
    if options.forcemap:
        ann1 = apply_type_mapping(ann1, TYPE_MAP)
        ann2 = apply_type_mapping(ann2, TYPE_MAP)

    match1, only1 = set(), set()
    match2, only2 = set(), set()
    for a1 in ann1:
        a2m = [a2 for a2 in ann2 if a1.start == a2.start and a1.end == a2.end
               and types_match(a1.type, a2.type, a1.text, options)]
        if a2m:
            print('MATCH: "{}" ({}/{})'.format(a1.text, a1.type, a2m[0].type))
            match1.add(a1)
            match2.update(a2m)
            stats['metrics total']['TP'] += 1
            stats['metrics {}'.format(a1.type)]['TP'] += 1
            for a in chain([a1], a2m):
                stats['by type']['matched {}'.format(a.type)] += 1
        else:
            print('ONLY1: "{}" ({})'.format(a1.text, a1.type))
            only1.add(a1)
            stats['metrics total']['FN'] += 1
            stats['metrics {}'.format(a1.type)]['FN'] += 1
            stats['by type']['missed {}'.format(a1.type)] += 1
    for a2 in ann2:
        if a2 not in match2:
            print('ONLY2: "{}" ({})'.format(a2.text, a2.type))
            only2.add(a2)
            stats['metrics total']['FP'] += 1
            stats['metrics {}'.format(a2.type)]['FP'] += 1
            stats['by type']['missed {}'.format(a2.type)] += 1

    # update stats
    if only1 or only2:
        stats['doc-level']['mismatch'] += 1
    else:
        stats['doc-level']['match'] += 1
        if match1 and match2:
            stats['doc-level']['match-nonempty'] += 1
        else:
            stats['doc-level']['match-empty'] += 1
    stats['doc-level']['TOTAL'] += 1

    # rough "score" for document
    if only1 or only2:
        score = -max(len(only1), len(only2))
    else:
        score = max(len(match1), len(match2))
    print('SCORE {}\t{}'.format(score, file1))
    
    return stats


def compare_dirs(dir1, dir2, options, stats):
    assert os.path.isdir(dir1) and os.path.isdir(dir2)
    list1 = set(os.listdir(dir1))
    list2 = set(os.listdir(dir2))
    for name in sorted(list(list1 & list2)):
        path1 = os.path.join(dir1, name)
        path2 = os.path.join(dir2, name)
        ext = os.path.splitext(name)[1]
        if (os.path.isdir(path1) or
            (os.path.isfile(path1) and ext == options.suffix)):
            stats = compare(path1, path2, options, stats)
        else:
            info('skipping {}'.format(name))
    return stats


def compare(path1, path2, options, stats=None):
    if stats is None:
        stats = defaultdict(lambda: defaultdict(int))
    if os.path.isfile(path1):
        if os.path.isfile(path2):
            return compare_files(path1, path2, options, stats)
        elif not os.path.exists(path2):
            warning('error: {} does not exist'.format(path2))
            return stats
        else:
            warning('mismatch: {} is file, {} is not'.format(path1, path2))
            return stats
    elif os.path.isdir(path1):
        if os.path.isdir(path2):
            return compare_dirs(path1, path2, options, stats)
        elif not os.path.exists(path2):
            warning('error: {} does not exist'.format(path2))
            return stats
        else:
            warning('mismatch: {} is file, {} is not'.format(path2, path1))
            return stats


def read_ids(fn):
    ids = set()
    with open(fn) as f:
        for ln, l in enumerate(f, start=1):
            l = l.rstrip('\n')
            ids.add(l)
    return ids


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.filtertypes is not None:
        args.filtertypes = args.filtertypes.split(',')

    if args.retype is not None:
        retype = []
        for from_to_file in args.retype.split(';'):
            from_, to_, fn = from_to_file.split(':')
            retype.append((from_, to_, read_ids(fn)))
        args.retype = retype

    # primary processing
    stats = compare(args.set1, args.set2, args)

    # print metrics
    print('-'*78)
    for m in sorted(set([k for k in stats.keys() if k.startswith('metrics')])):
        try:
            tp, fp, fn = stats[m]['TP'], stats[m]['FP'], stats[m]['FN']
            p = 1.*tp/(tp+fp)
            r = 1.*tp/(tp+fn)
            f = 2*p*r/(p+r)
            print('{}: f:{:.2%} (p:{:.2%} r:{:.2%}, tp:{} fp:{} fn:{})'.format(
                m, f, p, r, tp, fp, fn))
        except Exception as e:
            print('ERROR: failed to get metrics for {}: {}'.format(m, e))
        del stats[m]
    
    # print other stats
    print('-'*78)
    for t, s in sorted(stats.items()):
        print('stats {}'.format(t))
        for k, v in sorted(s.items(), reverse=True):
            print('{}\t{}'.format(k, v))
        print('-'*10)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
