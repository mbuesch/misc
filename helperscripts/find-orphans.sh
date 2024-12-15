#!/bin/sh

for pkg in $(dpkg --get-selections |\
	     grep -Ee '[[:space:]]install$' |\
	     grep -Eoe '^[^[:space:]]+'); do

	line="$(apt-cache showpkg "$pkg" | grep '/var/lib/apt/lists/' | head -n1)"

	if [ -n "$line" ]; then
		file="$(echo "$line" | cut -d'(' -f2 | cut -d')' -f1)"
		if [ -r "$file" ]; then
			continue
		fi
	fi
	# Found an orphan. Print its name.
	echo "$pkg"
done
