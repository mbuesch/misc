#!/bin/bash
set -e

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

loc_basedir="$basedir/locs"

GCCOM="$basedir/gccom.py"
ACCOUNT="$basedir/account"


user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"
cookie="$($GCCOM --user "$user" --password "$password" --getcookie)"

for cache in $@; do
	echo "Downloading LOC for $cache..."
	id="$($GCCOM --usecookie "$cookie" --getcacheid "$cache")"
	mkdir -p "$loc_basedir"
	file="$loc_basedir/$id.loc"
	$GCCOM --usecookie "$cookie" --file "$file" --getloc "$cache"
done

$GCCOM --usecookie "$cookie" --logout
