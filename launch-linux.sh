#!/bin/sh
launcher=$(command -p readlink -f -- "$0") || exit 1
root=${launcher%/*}
interpreter=$(command -v python3) || { echo 'Install Python 3.11 or later.' >&2; exit 1; }
case $interpreter in
    /*) ;;
    *) interpreter=$PWD/$interpreter ;;
esac
interpreter_dir=$(command -p readlink -f -- "${interpreter%/*}") || exit 1
if [ "$interpreter_dir" = "$root" ] || [ "$interpreter_dir" = "$(pwd -P)" ]; then
    echo 'Use an installed Python interpreter outside the source and current directories.' >&2
    exit 1
fi
exec "$interpreter" -I -S "$root/open_fire_toolkit/__main__.py" "$@"
