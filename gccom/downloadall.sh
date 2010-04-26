#!/bin/bash
set -e

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

$basedir/downloadlocs.sh $@
$basedir/downloadprint.sh $@

exit 0
