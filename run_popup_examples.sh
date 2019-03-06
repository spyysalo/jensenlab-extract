#!/bin/bash

INDIR=examples
OUTDIR=popup-examples-output

mkdir -p "$OUTDIR"

python3 scripts/getpopup.py -d "$OUTDIR" "$INDIR"/*.txt

echo "Done, results in $OUTDIR" >&2
