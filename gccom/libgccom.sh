GCCOM="$basedir/gccom.py"
GCSTATS="$basedir/gcstats.py"
ACCOUNT="$basedir/account"

user="$(cat "$ACCOUNT" | cut -d ' ' -f 1)"
password="$(cat "$ACCOUNT" | cut -d ' ' -f 2)"


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
	code="import gccom, re;"
	code="$code print re.match(r'.*(' + gccom.guidRegex + r').*', r'$1', re.DOTALL).group(1)"
	python -c "$code" || die "Failed to extract GUID"
}
