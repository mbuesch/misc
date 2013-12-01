# QEMU support lib

die()
{
	echo "$*" >&2
	exit 1
}

get_ports_db_file()
{
	local dbfile="/tmp/qemu-lib-ports.db"

	touch "$dbfile"
	chmod 666 "$dbfile"
	echo "$dbfile"
}

random_port()
{
	local dbfile="$(get_ports_db_file)"
	local port=

	while true; do
		port="$(expr "$(hexdump -n2 -e'/2 "%u"' /dev/urandom)" '%' 16384 '+' 1024)"
		grep -qEe "^${port}\$" "$dbfile" || break
	done

	echo "$port" >> "$dbfile"
	echo "$port"
}

# $1=portnumber
release_port()
{
	local port="$1"
	local dbfile="$(get_ports_db_file)"

	sed -ie '/^'"$port"'$/d' "$dbfile"
}

run_qemu()
{
	local bin="qemu-system-i386"
	echo "$bin $*"
	[ $opt_dryrun -eq 0 ] || return
	if [ $opt_spice -eq 0 ]; then
		exec "$bin" "$@"
	else
		"$bin" "$@" &
		qemu_pid=$!
		echo "Forked qemu (pid ${qemu_pid})"
	fi
}

run_spice_client()
{
	[ $opt_spice -eq 0 ] && return
	echo "Running spice client on ${spice_host}:${spice_port}..."
	sleep 1
	spicy -h "$spice_host" -p "$spice_port"
	echo "Killing qemu..."
	kill "$qemu_pid"
	wait
	release_port "$spice_port"
}

share_init()
{
	sharedir="$basedir/share"
	mkdir -p "$sharedir" || die "Failed to create $sharedir"
}

serial_init()
{
	serialdir="$basedir/serial"
	mkdir -p "$serialdir" || die "Failed to create $serialdir"
	for i in $(seq 0 1); do
		[ -p "$serialdir/$i" ] || {
			mkfifo "$serialdir/$i" || die "Failed to create fifo $i"
		}
	done
}

kvm_init()
{
	kvm_opt=
	[ -w /dev/kvm ] && kvm_opt="-enable-kvm"
}

# $1="vendor:device"
host_usb_id_prepare()
{
	local ids="$1"

	local lsusb_string="$(lsusb | grep -e "$ids" | head -n1)"
	[ -n "$lsusb_string" ] ||\
		die "USB device $ids not found"
	local busnr="$(echo "$lsusb_string" | awk '{print $2;}')"
	local devnr="$(echo "$lsusb_string" | awk '{print $4;}' | cut -d':' -f1)"
	echo "Found USB device $ids on $busnr:$devnr"

	echo "Changing device permissions..."
	sudo chmod o+w "/dev/bus/usb/$busnr/$devnr" ||\
		die "Failed to set usb device permissions"
}

usage()
{
	echo "qemu-script.sh [OPTIONS] [--] [QEMU-OPTIONS]"
	echo
	echo "Options:"
	echo " -m RAM                      Amount of RAM. Default: 1024m"
	echo " -n|--net-restrict on|off    Turn net restrict on/off. Default: on"
	echo " --spice 1|0                 Use spice client. Default: 1"
	echo " -u|--usb-id ABCD:1234       Use host USB device with ID ABCD:1234"
}

# Global variables: basedir, image, qemu_opts
run()
{
	[ -n "$spice_host" ] || spice_host="127.0.0.1"
	[ -n "$spice_port" ] || spice_port="$(random_port)"

	[ -n "$opt_ram" ] || opt_ram="1024m"
	[ -n "$opt_netrestrict" ] || opt_netrestrict="on"
	[ -n "$opt_dryrun" ] || opt_dryrun=0
	[ -n "$opt_spice" ] || opt_spice=1

	local usbdevice_opt=

	share_init
	serial_init
	kvm_init

	local end=0
	while [ $# -gt 0 -a $end -eq 0 ]; do
		case "$1" in
		-h|--help)
			usage
			exit 0
			;;
		-m)
			shift
			opt_ram="$1"
			;;
		-n|--net-restrict)
			shift
			opt_netrestrict="$1"
			;;
		--dry-run)
			opt_dryrun=1
			;;
		--spice)
			shift
			opt_spice="$1"
			;;
		-u|--usb-id)
			shift
			local ids="$1"

			host_usb_id_prepare "$ids"
			usbdevice_opt="$usbdevice_opt -usbdevice host:$ids"
			;;
		--)
			end=1
			;;
		*)
			die "Unknown option: $1"
			;;
		esac
		shift
	done

	local spice_opt=
	[ $opt_spice -ne 0 ] && {
		spice_opt="-spice addr=${spice_host},port=${spice_port},"
		spice_opt="${spice_opt}disable-ticketing,agent-mouse=off,"
		spice_opt="${spice_opt}plaintext-channel=main,plaintext-channel=display,"
		spice_opt="${spice_opt}plaintext-channel=cursor,plaintext-channel=inputs,"
		spice_opt="${spice_opt}plaintext-channel=record,plaintext-channel=playback"
	}

	run_qemu \
		-name "$image" \
		$kvm_opt \
		$spice_opt \
		-m "$opt_ram" \
		-hda "${basedir}/${image}" \
		-boot c \
		-net "nic,vlan=1,model=ne2k_pci,macaddr=00:11:22:AA:BB:CC" \
		-net "user,restrict=${opt_netrestrict},vlan=1,net=192.168.5.1/24,smb=${sharedir},smbserver=192.168.5.4" \
		-net "nic,vlan=2,model=ne2k_pci,macaddr=00:11:22:AA:BB:CD" \
		-usb $usbdevice_opt \
		-serial "pipe:${serialdir}/0" -serial "pipe:${serialdir}/1" \
		-vga qxl \
		$qemu_opts \
		"$@"
	run_spice_client
}
