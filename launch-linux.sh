#!/bin/sh
# Keep the original Linux command working for existing users.
launcher=$(command -p readlink -f -- "$0") || exit 1
exec /bin/sh "${launcher%/*}/launch.sh" "$@"
