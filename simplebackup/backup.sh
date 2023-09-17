#!/bin/sh

targetnode="/dev/disk/by-uuid/MY-UUID"
targetmp="/mnt/backup/target"
targetsub="datensicherung"
sourcepath="/mnt/backup/snapshots/root"
btrfs=1

die()
{
	local msg1="$1"
	local msg2="$2"

	if [ -n "$msg1" ]; then
		echo "$msg1" >&2
	fi
	echo >&2
	echo >&2
	echo >&2
	echo >&2
	echo "### FEHLER! FEHLER! FEHLER! ###" >&2
	echo "###" >&2
	if [ -n "$msg2" ]; then
		echo "### $msg2" >&2
	else
		echo "### Die Datensicherung wurde abgebrochen und ist unvollständig!" >&2
	fi
	echo "###" >&2
	echo "### FEHLER! FEHLER! FEHLER! ###" >&2
	echo >&2
	read -p "" x
	exit 1
}

# Become root.
mypath="$(realpath -e "$0")"
if [ "$(id -u)" != "0" ]; then
	if [ "$1" = "SECOND_STAGE" ]; then
		die "Second stage failed."
	else
		exec sudo "$mypath" SECOND_STAGE
		exit 1
	fi
fi

# Setup cleanup handler.
cleanup()
{
	umount -f "$targetmp" >/dev/null 2>&1
	if [ $btrfs -ne 0 ]; then
		btrfs subvolume delete "$sourcepath" >/dev/null 2>&1
	fi
}
trap cleanup EXIT

# Create the snapshot
if [ $btrfs -ne 0 ]; then
	btrfs subvolume delete "$sourcepath" >/dev/null 2>&1
	btrfs subvolume snapshot -r / "$sourcepath" ||\
		die "btrfs snapshot failed"
fi

# Mount the backup drive.
mkdir -p "$targetmp" || die "mkdir target failed."
if ! [ -b "$targetnode" ]; then
	die "dev node not present" "The Backup-Festplatte ist nicht angeschlossen!"
fi
umount -f "$targetnode" >/dev/null 2>&1
umount -f "$targetmp" >/dev/null 2>&1
mount "$targetnode" "$targetmp" || die "target mount failed"

# Sync the backup drive with the source drive.
mkdir -p "$targetmp/$targetsub" || die
while true; do
	rsync -aHAX --inplace --delete-before --progress \
		"$sourcepath"/ \
		"$targetmp/$targetsub"
	res=$?
	[ $res -eq 24 ] && continue
	[ $res -ne 0 ] && die
	break
done
if [ $btrfs -ne 0 ]; then
	while true; do
		rsync -aHAX --inplace --delete-before --progress \
			/boot/ \
			"$targetmp/$targetsub"_boot
		res=$?
		[ $res -eq 24 ] && continue
		[ $res -ne 0 ] && die
		break
	done
fi
umount "$targetmp" || die "umount failed"
if [ $btrfs -ne 0 ]; then
	btrfs subvolume delete "$sourcepath" ||\
		die "btrfs snapshot delete failed"
fi

echo
echo
echo
echo "########################################################"
echo "###   Alles Ok!                                      ###"
echo "###   Die Festplatte kann jetzt abgesteckt werden.   ###"
echo "########################################################"
read -p "" x
