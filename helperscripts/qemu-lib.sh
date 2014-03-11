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
	local bin="$qemu_binary"
	echo "Running QEMU..."
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
	[ $opt_dryrun -eq 0 ] && {
		sleep 1
		spicy -h "$spice_host" -p "$spice_port"
		echo "Killing qemu..."
		kill "$qemu_pid"
		wait
	}
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
	for i in $(seq 0 0); do
		[ -p "$serialdir/$i" ] || {
			mkfifo "$serialdir/$i" || die "Failed to create fifo $i"
		}
	done
}

kvm_init()
{
	kvm_opt=
	if [ -w /dev/kvm ]; then
		kvm_opt="-enable-kvm"
	else
		echo "===> WARNING: /dev/kvm not writable"
	fi
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

# $1="vendor:device"
host_pci_find_by_ids()
{
	local ids="$1"

	lspci -vn | grep -e "$ids" | awk '{print $1;}'
}

# $1="00:00.0"
host_pci_prepare()
{
	local dev="$1"

	echo "Assigning PCI device $dev ..."

	local lspci_string="$(lspci -mmn | grep -e "^$dev" | head -n1)"
	[ -n "$lspci_string" ] ||\
		die "PCI device $dev not found"
	dev="0000:$dev"
	local vendorid="$(echo "$lspci_string" | cut -d' ' -f 3 | tr -d \")"
	local deviceid="$(echo "$lspci_string" | cut -d' ' -f 4 | tr -d \")"
	echo "Found PCI device $dev with IDs $vendorid:$deviceid"

	local orig_drvdir="$(find /sys/bus/pci/drivers -type l -name "$dev")"
	orig_drvdir="$(dirname "$orig_drvdir")"
	[ -n "$orig_drvdir" -a "$orig_drvdir" != "." ] || {
		echo "WARNING: Did not find attached kernel driver for PCI device $dev"
		orig_drvdir=
	}

	modprobe pci-stub || die "Failed to load 'pci-stub' kernel module"
	echo "$vendorid $deviceid" > /sys/bus/pci/drivers/pci-stub/new_id ||\
		die "Failed to register PCI-id to pci-stub driver"
	[ -n "$orig_drvdir" ] && {
		echo "$dev" > "$orig_drvdir/unbind" ||\
			die "Failed to unbind PCI kernel driver"
	}
	echo "$dev" > /sys/bus/pci/drivers/pci-stub/bind ||\
		die "Failed to bind pci-stub kernel driver"
	echo "$vendorid $deviceid" > /sys/bus/pci/drivers/pci-stub/remove_id ||\
		die "Failed to remove PCI-id from pci-stub driver"

	[ -n "$orig_drvdir" ] &&\
		assigned_pci_devs="$assigned_pci_devs $dev/$orig_drvdir"
}

host_pci_restore_all()
{
	for assigned_dev in $assigned_pci_devs; do
		local dev="$(echo "$assigned_dev" | cut -d'/' -f1)"
		local orig_drvdir="/$(echo "$assigned_dev" | cut -d '/' -f2-)"

		echo "Restoring PCI device $dev ..."
		echo "$dev" > /sys/bus/pci/drivers/pci-stub/unbind
		echo "$dev" > "$orig_drvdir"/bind
	done
}

# $1=brdev, $2=ethdev
bridge_setup()
{
	local brdev="$1"
	local ethdev="$2"

	ip link set down dev "$brdev" >/dev/null 2>&1
	brctl delbr "$brdev" >/dev/null 2>&1

	brctl addbr "$brdev" || die "Failed to add bridge '$brdev'"
	brctl addif "$brdev" "$ethdev" || die "Failed to add '$ethdev' to bridge '$brdev'"
	ip link set up dev "$ethdev" || die "Failed to bring up '$ethdev'"
	ip link set up dev "$brdev" || die "Failed to bring up bridge '$brdev'"
}

usage()
{
	echo "qemu-script.sh [OPTIONS] [--] [QEMU-OPTIONS]"
	echo
	echo "Options:"
	echo " --dry-run                   Do not run qemu/spice. (But do (de)allocate ressources)"
	echo " -m RAM                      Amount of RAM. Default: 1024m"
	echo " -n|--net-restrict on|off    Turn net restrict on/off. Default: on"
	echo " --spice 1|0                 Use spice client. Default: 1"
	echo " -u|--usb-id ABCD:1234       Use host USB device with ID ABCD:1234"
	echo " -p|--pci-id ABCD:1234       Forward PCI device with ID ABCD:1234"
	echo " -P|--pci-device 00:00.0     Forward PCI device at 00:00.0"
	echo " -B|--bridge BRDEV,ETHDEV    Create BRDEV and add ETHDEV"
}

# Global variables:
#  basedir, image, qemu_opts, rtc, qemu_binary, spice_host, spice_port,
#  opt_ram, opt_netrestrict
run()
{
	[ -n "$basedir" ] || die "No basedir specified"
	[ -n "$image" ] || die "No image specified"

	# Canonicalize paths
	basedir="$(readlink -m "$basedir")"
	image="$(readlink -m "$image")"

	# Set variable-defaults
	[ -n "$qemu_binary" ] || qemu_binary="qemu-system-i386"
	[ -n "$spice_host" ] || spice_host="127.0.0.1"
	[ -n "$spice_port" ] || spice_port="$(random_port)"
	[ -n "$rtc" ] || rtc="-rtc base=localtime,clock=host"

	# Set option-defaults
	[ -n "$opt_ram" ] || opt_ram="1024m"
	[ -n "$opt_netrestrict" ] || opt_netrestrict="on"
	[ -n "$opt_dryrun" ] || opt_dryrun=0
	[ -n "$opt_spice" ] || opt_spice=1
	local usbdevice_opt=
	local pcidevice_opt=
	local bridge_opt=

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
		-p|--pci-id)
			shift
			local ids="$1"

			local dev="$(host_pci_find_by_ids "$ids")"
			[ -n "$dev" ] || die "Did not find PCI device with IDs '$ids'"
			host_pci_prepare "$dev"
			pcidevice_opt="$pcidevice_opt -device pci-assign,host=$dev"
			;;
		-P|--pci-device)
			shift
			local dev="$1"

			host_pci_prepare "$dev"
			pcidevice_opt="$pcidevice_opt -device pci-assign,host=$dev"
			;;
		-B|--bridge)
			shift
			local devs="$1"

			local brdev="$(echo "$devs" | cut -d',' -f1)"
			local ethdev="$(echo "$devs" | cut -d',' -f2)"
			bridge_setup "$brdev" "$ethdev"
			bridge_opt="-net bridge,vlan=2,br=$brdev"
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
		-name "$(basename "$image")" \
		$kvm_opt \
		$spice_opt \
		-m "$opt_ram" \
		-hda "$image" \
		-boot c \
		-net "nic,vlan=1,model=rtl8139,macaddr=00:11:22:AA:BB:CC" \
		-net "user,restrict=${opt_netrestrict},vlan=1,net=192.168.5.1/24,smb=${sharedir},smbserver=192.168.5.4" \
		-net "nic,vlan=2,model=rtl8139,macaddr=00:11:22:AA:BB:CD" \
		-usb $usbdevice_opt \
		-serial "pipe:${serialdir}/0" \
		$pcidevice_opt \
		$bridge_opt \
		-vga qxl \
		$rtc \
		$qemu_opts \
		"$@"
	run_spice_client
	host_pci_restore_all
}
