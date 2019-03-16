# jensenlab-extract

Tools for working with EXTRACT (https://extract.jensenlab.org/)

(Under construction)

---

## Quickstart

```
./scripts/download_dict.sh tagger


mkdir db
python3 scripts/makedb.py data/tagger-dict/tagger_names.tsv db/tagger-names.sqlite
```

## For full dictionary

```
./scripts/download_dict.sh full

mkdir db
python3 scripts/makedb.py data/full-dict/full_names.tsv db/full-names.sqlite
```
