#!/bin/bash

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

loc_basedir="$basedir/locs"

GCCOM="$basedir/gccom.py"
ACCOUNT="$basedir/account"

die()
{
	echo "$*"
	exit 1
}

gccom()
{
	"$GCCOM" "$@" || die "gccom.py FAILED"
}

user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"
cookie="$(gccom --user "$user" --password "$password" --getcookie)"

for cache in "$@"; do
	[ "${cache:0:2}" != "--" ] || continue # ignore options starting with --

	echo "Downloading LOC for $cache..."
	id="$(gccom --usecookie "$cookie" --getcacheid "$cache")"
	mkdir -p "$loc_basedir" || die "mkdir FAILED"
	file="$loc_basedir/$id.loc"
	gccom --usecookie "$cookie" --file "$file" --getloc "$cache"
done
gccom --usecookie "$cookie" --logout

exit 0
