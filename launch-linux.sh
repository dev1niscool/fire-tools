#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
exec python3 -m open_fire_toolkit "$@"
