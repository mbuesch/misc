#!/bin/sh
#
# Simple dosbox wrapper
#

basedir="$(realpath -s "$0" | xargs dirname)"
tooldir="$(realpath -P "$0" | xargs dirname)"

die()
{
    echo "ERROR: $*" >&2
    exit 1
}

rootdir=

while [ $# -gt 0 ]; do
    case "$1" in
        *)
            [ -z "$rootdir" ] || die "Unknown option: $*"
            rootdir="$*"
            ;;
    esac
    shift
done

[ -d "$rootdir" ] || die "Selected root directory '$rootdir' not found."
rootdir="$(realpath "$rootdir")"
conf="$rootdir/dosbox.conf"
[ -r "$conf" ] || die "Configuration file '$conf' is not readable."

cd "$rootdir" || die "Failed to enter rootdir."

mkdir -p "$rootdir/c/bin" ||\
    die "Failed to make bin directory."
if ! [ -e "$rootdir/c/bin/kfast.com" ]; then
    python3 "$tooldir/gen_kfast.py" "$rootdir/c/bin/kfast.com" ||\
        die "Failed to make KFAST.COM"
fi

dosbox -conf "$conf" || die "Dosbox exited with an error."

# vim: ts=4 sw=4 expandtab
