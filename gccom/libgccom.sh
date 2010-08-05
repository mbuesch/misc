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

gccom_login()
{
	local user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
	local password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"
	cookie="$(gccom --user "$user" --password "$password" --getcookie)"
}

gccom_logout()
{
	gccom --usecookie "$cookie" --logout
}

gccom_get_cacheid() # $1=guid
{
	gccom --usecookie "$cookie" --getcacheid "$guid"
}

gccom_download_recursive() # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -qrkl1 --no-cookies --header "Cookie: $cookie" "$2" || die "Recursive wget FAILED"
	cd "$origin"
}

gccom_download() # $1=target_dir $2=URL
{
	local origin="$PWD"
	cd "$1"
	wget -q --no-cookies --header "Cookie: $cookie" "$2" || die "wget FAILED"
	cd "$origin"
}

extract_guid() # $1=string
{
	python -c "print \"$1\"[-36:]" || die "Failed to extract GUID"
}
