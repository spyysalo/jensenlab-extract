#!/bin/bash

set -euo pipefail

# https://stackoverflow.com/a/246128
BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

INDIR="$BASEDIR/examples"
OUTDIR="$BASEDIR/popup-examples-output"

mkdir -p "$OUTDIR"

python3 "$BASEDIR/scripts/getpopup.py" -d "$OUTDIR" "$INDIR"/*.txt

echo "Done, results in $OUTDIR" >&2
