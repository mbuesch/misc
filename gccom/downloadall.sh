#!/bin/bash

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

if ! $basedir/downloadlocs.sh $@; then
	echo "Failed to download LOCs"
	exit 1
fi
if ! $basedir/downloadweb.sh $@; then
	echo "Failed to download WEB"
	exit 1
fi

exit 0
