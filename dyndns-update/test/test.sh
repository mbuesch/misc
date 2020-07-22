#!/bin/sh
basedir="$(dirname "$0")"
[ "$(echo "$basedir" | cut -c1)" = '/' ] || basedir="$PWD/$basedir"


QUERY_STRING="domain=mydomain&user=me&pw=123&ip4=127.0.0.1&ip6=1::&ip6pfx=1::&dualstack=1" \
	"$basedir/../dyndns-update" -c "$basedir/test.conf" || exit 1
echo
cat /tmp/test_mydomain
