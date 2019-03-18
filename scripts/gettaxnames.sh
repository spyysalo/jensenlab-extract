#!/bin/bash

# Get ID-name mapping from NCBI taxonomy data.

set -euo pipefail

# https://stackoverflow.com/a/246128
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

DATADIR="$SCRIPTDIR/../data"

OUTPUT="$DATADIR/taxnames.tsv"

echo "Creating data directory $DATADIR ..." >&2
mkdir -p "$DATADIR"

echo "Creating temporary work directory ..." >&2
TMPDIR=`mktemp -d`

function rmtmp {      
  rm -rf "$TMPDIR"
}

trap rmtmp EXIT

cd "$TMPDIR"

echo "Downloading taxdump.tar.gz from NCBI ..." >&2
wget 'ftp://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz'

echo "Unpacking taxdump.tar.gz ..." >&2
tar xvzf taxdump.tar.gz

# Grab fields tax_id, name_txt and name class, filter to scientific
# names and drop the name class.
echo "Storing scientific names in $OUTPUT ..." >&2
cut -f 1,3,7 names.dmp | egrep $'\t''scientific name$' | cut -f 1,2 > "$OUTPUT"

echo "Done." >&2
