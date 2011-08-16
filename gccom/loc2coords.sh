#!/bin/bash

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

for file in $@; do
	lat="$(cat "$file" | grep '<coord' | head -n1 | cut -d'"' -f2)"
	lat="$($basedir/../geoconv.py "$lat" | head -n1 | cut -d'|' -f2)"
	lon="$(cat "$file" | grep '<coord' | head -n1 | cut -d'"' -f4)"
	lon="$($basedir/../geoconv.py "$lon" | head -n1 | cut -d'|' -f2)"
	echo N $lat "  E" $lon
done
