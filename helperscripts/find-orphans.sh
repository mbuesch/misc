#!/bin/sh

for pkg in $(dpkg --get-selections |\
	     grep -Ee '[[:space:]]install$' |\
	     grep -Eoe '^[^[:space:]]+'); do
	if apt-get install --dry-run --reinstall "$pkg" |\
	   grep -q 'it cannot be downloaded'; then
	   	# Found an orphan. Print its name.
		echo "$pkg"
	fi
done
