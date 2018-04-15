#!/bin/sh

for pkg in $(dpkg --get-selections |\
	     grep -Ee '[[:space:]]install$' |\
	     grep -Eoe '^[^[:space:]]+'); do
	if ! apt-cache showpkg "$pkg" |\
	     grep -q '/var/lib/apt/lists/'; then
	   	# Found an orphan. Print its name.
		echo "$pkg"
	fi
done
