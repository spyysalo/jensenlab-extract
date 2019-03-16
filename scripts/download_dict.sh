#!/bin/bash

# Download JensenLab tagger dictionary data.

function usage_exit() {
    cat <<EOF >&2
Usage: $0 DICT, where DICT is 
    "tagger" for the smaller tagger dictionary (300M download) or
    "full" for the full dictionary (1.7G download)
EOF
    exit 1
}

if [ "$1" == "tagger" ]; then
    url='http://download.jensenlab.org/tagger_dictionary.tar.gz'
    dict="$1"
elif [ "$1" == "full" ]; then
    url='http://download.jensenlab.org/full_dictionary.tar.gz'
    dict="$1"
else
    usage_exit
fi

set -euo pipefail

# https://stackoverflow.com/a/246128
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

DATADIR="$SCRIPTDIR/../data"

OUTDIR="$DATADIR/${dict}-dict"

echo "Creating data directory $OUTDIR ..." >&2
mkdir -p "$OUTDIR"

echo "Creating temporary work directory ..." >&2
TMPDIR=`mktemp -d`

function rmtmp {      
    echo -n "Deleting temporary directory ... " >&2
    rm -rf "$TMPDIR"
    echo "done." >&2
}

trap rmtmp EXIT

cd "$TMPDIR"
echo "$TMPDIR"

out=$(basename "$url")
echo "Downloading $out from $url ..." >&2
wget "$url" -O "$out"

echo "Unpacking $out to $OUTDIR ..." >&2
tar xvzf "$out" -C "$OUTDIR"

echo "Done." >&2
