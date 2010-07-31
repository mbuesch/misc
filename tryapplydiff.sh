#!/bin/bash
# Hacky script to sort patches based on whether they apply cleanly or not

p=1				# patch -p
okdir="./patches-ok"		# OK directory
faildir="./patches-fail"	# Fail directory
alreadydir="./patches-already"	# Already applied directory


tmpfile="$(mktemp)"
mkdir -p "$okdir"
mkdir -p "$faildir"
mkdir -p "$alreadydir"
while [ $# -ne 0 ]; do
	diff="$1"
	shift

	[ -f "$diff" ] || continue
	echo "Checking $diff..."

	patch --dry-run -p$p < "$diff" 2>&1 >$tmpfile
	res=$?

	cat $tmpfile
	echo "RES == $res"
	if [ "x$(grep 'Reversed (or previously applied)' "$tmpfile")" != "x" ]; then
		cp "$diff" "$alreadydir/$(basename "$diff")"
	else
		if [ $res -eq 0 ]; then
			cp "$diff" "$okdir/$(basename "$diff")"
		else
			cp "$diff" "$faildir/$(basename "$diff")"
		fi
	fi

	echo
done
rm $tmpfile
