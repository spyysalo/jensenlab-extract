#!/bin/bash

set -euo pipefail

# https://stackoverflow.com/a/246128
BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

INDIR="$BASEDIR/examples"
OUTDIR="$BASEDIR/popup-standoff-output"

TMPDIR=$(mktemp -d)
function rmtemp {
    rm -rf "$TMPDIR"
}
trap rmtemp EXIT

python3 "$BASEDIR/scripts/getpopup.py" -d "$TMPDIR" "$INDIR"/*.txt

mkdir -p "$OUTDIR"

python3 "$BASEDIR/scripts/popuphtml2standoff.py" -d "$OUTDIR" "$TMPDIR"/*.html

cp "$INDIR/annotation.conf" "$OUTDIR"
cp "$INDIR/tools.conf" "$OUTDIR"
cp "$INDIR/visual.conf" "$OUTDIR"

echo "Done, results in $OUTDIR"
