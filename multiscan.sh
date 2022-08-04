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
	echo " --resolution XXX        Scan resolution in DPI"
	echo " --format XXX            Set output format. Default jpg"
	echo " --quality XX            Output quality. Default 90"
	exit 1
}

[ $# -ge 1 ] || usage

count=0
resolution=
out_format="jpg"
out_quality="90"

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
	--format)
		shift
		out_format="$1"
		;;
	--resolution)
		shift
		resolution="$1"
		;;
	--quality)
		shift
		out_quality="$1"
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
	[ $first -eq 0 ] && {
		read -p "[Press enter to continue or ^C to abort]" RES
	}
	first=0
}

do_scanimage()
{
	echo "Running: scanimage $* > $filename" >&2
	scanimage "$@" || die "scanimage failed"
}

find_device()
{
	scanimage -L | while read line; do
		echo "$line" | grep -qEe '(/dev/video)|(Failed cupsGetDevices)' || {
			echo -n "$line" | cut -d'`' -f2 | cut -d\' -f1
			break
		}
	done
}

echo "Searching for scanner..."
dev="$(find_device)"
[ -n "$dev" ] || die "Did not find a scanner"
echo "Using scanner '$dev'"

first=1
while cont_prompt; do
	filename="$(printf '%s-%03d.pnm' "$filename_base" "$count")"
	opts=
	[ -n "$resolution" ] && opts="$opts --resolution $resolution"
	do_scanimage -d "$dev" \
		--mode Color \
		-l 0 -t 0 -x 210 -y 297 \
		--format=pnm \
		$opts \
		"$@" > "$filename"
	[ "$out_format" = "jpg" ] && {
		jpg_filename="$(basename "$filename" .pnm).jpg"
		echo "Converting to '$jpg_filename'..."
		convert pnm:"$filename" \
			-quality "$out_quality" jpg:"$jpg_filename" ||\
			die "Failed to convert image to jpg"
		rm "$filename"
	}
	count="$(expr "$count" + 1)"
done
