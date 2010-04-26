#!/bin/bash
set -e

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

templates_basedir="$basedir/print_templates"

GCCOM="$basedir/gccom.py"
ACCOUNT="$basedir/account"
BROWSER="konqueror"


user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"
cookie="$($GCCOM --user "$user" --password "$password" --getcookie)"

function http_download_recursive # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -qrkl1 --no-cookies --header "Cookie: $cookie" "$2"
	cd $PWD
}

function http_download # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -q --no-cookies --header "Cookie: $cookie" "$2"
	cd $PWD
}

for cache in $@; do
	# Convert input to GUID.
	guid="$(python -c "print \"$cache\"[-36:]")"

	echo "Fetching GCxxxx cache ID for $guid..."
	id="$($GCCOM --usecookie "$cookie" --getcacheid "$guid")"
	dldir="$templates_basedir/$id"
	tmpdir="$dldir/tmp"
	mkdir -p "$dldir"
	mkdir -p "$tmpdir"

	echo "Fetching print page for $id..."
	url="http://www.geocaching.com/seek/cdpf.aspx?guid=$guid"
	http_download_recursive "$dldir" "$url"
	dlfile="$dldir/www.geocaching.com/seek/cdpf.aspx?guid=$guid"
	if [ "x$(grep -e 'firstaid-yes.gif' "$dlfile")" != "x" ]; then
		echo "WARNING: $id NEEDS MAINTENANCE"
		# Re-download with logs
		url="$url&lc=10"
		dlfile="$dlfile&lc=10"

		rm -Rf "$dldir"
		mkdir -p "$dldir"
		mkdir -p "$tmpdir"
		http_download_recursive "$dldir" "$url"
	fi

	$GCCOM --usecookie "$cookie" \
		--file "$tmpdir/mainpage.html" \
		--getpage "http://www.geocaching.com/seek/cache_details.aspx?guid=$guid"
	for image in $(grep -e "ctl00_ContentBody_Images" "$tmpdir/mainpage.html" | sed -e 's/"/\n/g' | grep "http://img.geocaching.com/cache"); do
		echo "Fetching spoiler image $image..."
		http_download "$dldir" "$image"
	done

	echo "Patching $id..."
	sed -i -e 's/<\/body>/<script type="text\/javascript"> dht(); <\/script><\/body>/' "$dlfile"
	sed -i -e 's/<head>/<head><meta http-equiv="Content-Type" content="text\/html; charset=UTF-8" \/>/' "$dlfile"

	rm -Rf "$tmpdir"

	echo "Loading $id in browser..."
	$BROWSER "$dlfile" 2>/dev/null >/dev/null &
done

echo "logout."
$GCCOM --usecookie "$cookie" --logout
