#!/bin/sh
date="$(date '+%Y%m%d-%H%M%S')"
tarfile="/sdcard/termux-backup-$date.tar.gz"
echo "Backup to $tarfile ..."
exec tar czf "$tarfile" -C /data/data/com.termux/files ./home ./usr
