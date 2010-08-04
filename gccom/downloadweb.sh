#!/bin/bash

basedir="$(dirname "$0")"
[ "${basedir:0:1}" = "/" ] || basedir="$PWD/$basedir"

web_dir="$basedir/web"
print_dir="$basedir/print"
tmp_dir="$basedir/web.tmp"

GCCOM="$basedir/gccom.py"
ACCOUNT="$basedir/account"
BROWSER="konqueror"

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
rm -rf "$tmp_dir"
mkdir "$tmp_dir" || die "Failed to mkdir $tmp_dir"

http_download_recursive() # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -qrkl1 --no-cookies --header "Cookie: $cookie" "$2" || die "Recursive wget FAILED"
	cd "$origin"
}

http_download() # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -q --no-cookies --header "Cookie: $cookie" "$2" || die "wget FAILED"
	cd "$origin"
}

printpage_get() # $1=target_dir $2=guid $3=cacheid $4=URL-suffix
{
	local target_dir="$1"
	local guid="$2"
	local id="$3"
	local url_suffix="$4"
	local url="http://www.geocaching.com/seek/cdpf.aspx?guid=$guid$url_suffix"

	mkdir -p "$target_dir" || die "Failed to mkdir $target_dir"
	http_download_recursive "$target_dir" "$url"

	file="$target_dir/www.geocaching.com/seek/cdpf.aspx?guid=$guid$url_suffix"
	if [ "x$(grep -e 'firstaid-yes.gif' "$file")" != "x" ]; then
		echo "WARNING: $id NEEDS MAINTENANCE"
	fi

	# Patch the page
	if [ "x$(grep -e '<div id="div_hint' "$file")" != "x" ]; then
		sed -i -e 's/<\/body>/<script type="text\/javascript"> dht(); <\/script><\/body>/' \
			"$file" || die "Patching print page failed (1)"
	fi
	sed -i -e 's/<head>/<head><meta http-equiv="Content-Type" content="text\/html; charset=UTF-8" \/>/' \
		"$file" || die "Patching print page failed (2)"

	# Creating a convenience link
	clink="$target_dir/www.geocaching.com/seek/$id.html"
	ln -s "$file" "$clink" || die "Failed to create link"

	# Generate a PDF
	wkhtmltopdf "$clink" "$target_dir/$id.pdf" || die "Failed to generate PDF"
}

for cache in "$@"; do
	# Convert input to GUID.
	guid="$(python -c "print \"$cache\"[-36:]")"

	echo "Fetching GCxxxx cache ID for $guid..."
	id="$(gccom --usecookie "$cookie" --getcacheid "$guid")"

	echo "Fetching webpages for $id..."
	printpage_get "$web_dir/$id" "$guid" "$id" "&lc=10"

	tmp_file="$tmp_dir/mainpage.html"
	gccom --usecookie "$cookie" \
		--file "$tmp_file" \
		--getpage "http://www.geocaching.com/seek/cache_details.aspx?guid=$guid"
	for img in $(grep -e "ctl00_ContentBody_Images" "$tmp_file" |\
		     sed -e 's/"/\n/g' | grep "http://img.geocaching.com/cache"); do
		echo "Fetching spoiler image $img..."
		http_download "$web_dir/$id" "$img"
	done
	rm -f "$tmp_file"

	echo "Fetching printpages for $id..."
	printpage_get "$print_dir/$id" "$guid" "$id" ""

#	echo "Loading $id in browser..."
#	$BROWSER "$dlfile" 2>/dev/null >/dev/null &
done

echo "logout."
gccom --usecookie "$cookie" --logout
rm -rf "$tmp_dir"

exit 0
