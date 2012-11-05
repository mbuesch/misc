#!/bin/sh

die()
{
	echo "$*"
	exit 1
}

usage()
{
	echo "Usage: $0 [options] filename-base [scanimage options]"
	echo
	echo "Options:"
	echo " --startcount XXX        Start filename count at XXX"
	exit 1
}

[ $# -ge 1 ] || usage

count=0

while [ $# -ge 1 ]; do
	case "$1" in
	-h|--help)
		usage
		;;
	--startcount)
		shift
		count="$1"
		expr "$count" + 1 >/dev/null 2>&1 ||\
			die "--startcount is not numeric"
		;;
	*)
		break
		;;
	esac
	shift
done

filename_base="$1"
shift
[ -n "$filename_base" ] || die "No filename base"


cont_prompt()
{
	printf '\nGoing to scan page %03d\n' "$count"
	read -p "[Press enter to continue or ^C to abort]" RES
}

do_scanimage()
{
	echo "Running: scanimage $* > $filename" >&2
	scanimage "$@"
}

find_device()
{
	scanimage -L | while read line; do
		echo "$line" | grep -qe '/dev/video' || {
			echo -n "$line" | cut -d'`' -f2 | cut -d\' -f1
		}
	done
}

dev="$(find_device)"
[ -n "$dev" ] || die "Did not find a scanner"

while cont_prompt; do
	filename="$(printf '%s-%03d.pnm' "$filename_base" "$count")"
	do_scanimage -d "$dev" \
		--mode Color --depth 8 --resolution 300 \
		-l 0 -t 0 -x 210 -y 297 \
		--format=pnm \
		"$@" > "$filename"
	count="$(expr "$count" + 1)"
done
