# jensenlab-extract

Tools for working with JensenLab tools (https://jensenlab.org/resources/textmining/)

(Under construction)

---

## Quickstart

Convert examples to standoff

```
python3 scripts/tagged2standoff.py -d standoff examples/example-{docs,tags}.tsv
```

## Name and entity DBs

Prepare DBs using "tagger" dictionary subset

```
./scripts/download_dict.sh tagger

mkdir db
python3 scripts/makedb.py data/tagger-dict/tagger_names.tsv db/names.sqlite
python3 scripts/makedb.py -f 3 data/tagger-dict/tagger_entities.tsv db/entities.sqlite
```

Alternatively, using full dictionary

```
./scripts/download_dict.sh full

mkdir db
python3 scripts/makedb.py data/full-dict/full_names.tsv db/names.sqlite
python3 scripts/makedb.py -f 3 data/full-dict/full_entities.tsv db/entities.sqlite
```

## Conversion using name and entity DBs

```
python3 scripts/tagged2standoff.py -d standoff2 -n db/names.sqlite -e db/entities.sqlite examples/example-{docs,tags}.tsv
```

Difference

```
diff -r standoff standoff2
```
