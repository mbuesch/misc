#!/bin/bash

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

loc_basedir="$basedir/locs"

. "$basedir/libgccom.sh"

gccom_login

for cache in "$@"; do
	[ "${cache:0:2}" != "--" ] || continue # ignore options starting with --

	echo "Downloading LOC for $cache..."
	guid="$(extract_guid "$cache")"
	id="$(gccom_get_cacheid "$guid")"
	mkdir -p "$loc_basedir" || die "mkdir FAILED"
	file="$loc_basedir/$id.loc"
	gccom --usecookie "$cookie" --file "$file" --getloc "$cache"
done

gccom_logout

exit 0
