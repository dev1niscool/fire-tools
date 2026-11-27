#!/bin/sh
# Run from source with the installed Python on macOS or Linux.
unset CDPATH
caller_dir=$(pwd -P) || exit 1

resolve_file() {
    case $1 in
        /*) file=$1 ;;
        *) file=$caller_dir/$1 ;;
    esac
    hops=0
    while [ -L "$file" ]; do
        [ "$hops" -lt 40 ] || return 1
        target=$(command -p readlink "$file") || return 1
        case $target in
            /*) file=$target ;;
            *) file=${file%/*}/$target ;;
        esac
        hops=$((hops + 1))
    done
    parent=$(cd -P "${file%/*}/" && pwd -P) || return 1
    printf '%s/%s\n' "${parent%/}" "${file##*/}"
}

launcher=$(resolve_file "$0") || exit 1
root=${launcher%/*}
interpreter=$(command -v python3) || { echo 'Install Python 3.11 or later.' >&2; exit 1; }
case $interpreter in
    /*) ;;
    *) interpreter=$caller_dir/$interpreter ;;
esac
found_in=$(cd -P "${interpreter%/*}/" && pwd -P) || exit 1
resolved=$(resolve_file "$interpreter") || exit 1
for directory in "$found_in" "${resolved%/*}"; do
    if [ "$directory" -ef "$root" ] || [ "$directory" -ef "$caller_dir" ]; then
        echo 'Use an installed Python interpreter outside the source and current directories.' >&2
        exit 1
    fi
done
exec "$interpreter" -I -S "$root/open_fire_toolkit/__main__.py" "$@"
