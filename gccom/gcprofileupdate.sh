#!/bin/bash
# Geocaching.com - Automatic profile update
set -e

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

GCCOM="$basedir/gccom.py"
GCSTATS="$basedir/gcstats.py"
ACCOUNT="$basedir/account"

user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"

echo "Generating statistics..."
$GCSTATS --user "$user" --password "$password" -o "$basedir"
echo
echo "Uploading profile..."
$GCCOM --user "$user" --password "$password" -f "$basedir/gcstats.html" --setprofile

