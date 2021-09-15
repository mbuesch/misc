#!/bin/sh
tarfile="$1"
if ! [ -r "$tarfile" ]; then
	echo "Usage: $0 BACKUP_TARFILE"
	exit 1
fi
echo "Restoring from $tarfile ..."
exec tar xf "$tarfile" -C /data/data/com.termux/files --recursive-unlink --preserve-permissions
