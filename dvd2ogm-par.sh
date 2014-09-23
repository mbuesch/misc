#!/bin/sh
#
# dvd2ogm-par.sh IMAGE.ISO TITLE TITLE TITLE...
#

set -e

nicelvl=19
dvd2ogm="dvd2ogm.sh"
image="$1"
shift
titles="$*"

export PATH="$(pwd):$PATH"

for title in $titles; do
	(
		mkdir "title-$title"
		cd "title-$title"
		nice -n$nicelvl $dvd2ogm "$image" "$title"
		cd ..
		mv "title-$title/out.ogm" "./title-$title.ogm"
		rmdir "title-$title"
	) &
done

wait
exit 0
