#!/bin/sh

max_age="$(expr 60 \* 60 \* 24 \* 7)"
max_age_text="eine Woche"
dialog_timeout_ms=60000
text_summary="Datensicherung ist alt"
text_body="Die Datensicherung ist älter als $max_age_text.\nBitte JETZT eine Datensicherung durchführen."

####

die()
{
	echo "$*" >&2
	exit 1
}

# Check if the backup is too old
stamp=/var/lib/simplebackup/stamp
too_old=0
if [ -r "$stamp" ]; then
	backup_time="$(cat "$stamp")"
	now="$(date --utc '+%s')"
	if [ -z "$backup_time" ] || [ -z "$now" ]; then
		echo "Simplebackup: Failed to get time stamps." >&2
		too_old=1
	else
		diff="$(expr "$now" - "$backup_time")"
		if [ -z "$diff" ]; then
			echo "Simplebackup: Failed to calculate age." >&2
			too_old=1
		elif [ "$diff" -gt "$max_age" ]; then
			echo "Simplebackup: Backup is outdated!"
			too_old=1
		fi
	fi
else
	echo "Simplebackup: Time stamp not found." >&2
	too_old=1
fi

# Display a desktop notification, if the backup is too old.
if [ "$too_old" -ne 0 ]; then
	[ -n "$DISPLAY" ] || export DISPLAY=:0.0
	[ -n "$XDG_RUNTIME_DIR" ] || export XDG_RUNTIME_DIR="/run/user/$(id -u)"
	[ -n "$HOME" ] || export HOME="/home/$(id -un)"
	[ -n "$XAUTHORITY" ] || export XAUTHORITY="$HOME/.Xauthority"
	export PATH="/usr/bin:$PATH"
	notify-send \
		-t "$dialog_timeout_ms" \
		-a "Backup" \
		-u normal \
		-i dialog-warning \
		"$text_summary" \
		"$text_body" \
		|| die "Failed to run notify-send"
fi

exit 0
