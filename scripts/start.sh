#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$SOURCE/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m dots_panel "$@"
