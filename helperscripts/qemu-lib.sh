# QEMU support lib

die()
{
	echo "$*" >&2
	exit 1
}

# $1=text
tolower()
{
	local str="$1"

	echo -n "$str" | tr '[:upper:]' '[:lower:]'
}

# $1=value
parse_bool()
{
	local str="$1"

	str="$(tolower "$str")"
	! [ "$str" = "0" -o \
	    "$str" = "off" -o \
	    "$str" = "false" -o \
	    "$str" = "no" ]
}

# $1=value
bool_to_1_0()
{
	parse_bool "$1" && echo -n 1 || echo -n 0
}

# $1=value
bool_to_on_off()
{
	parse_bool "$1" && echo -n on || echo -n off
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
	local serialdir="$basedir/serial"
	local from=0
	local to=0

	mkdir -p "$serialdir" || die "Failed to create $serialdir"
	for i in $(seq $from $to); do
		[ -p "$serialdir/$i" ] || {
			mkfifo "$serialdir/$i" || die "Failed to create fifo $i"
		}
		serial_opt="$serial_opt -serial pipe:$serialdir/0"
	done
}

kvm_init()
{
	modprobe kvm >/dev/null 2>&1
	modprobe kvm-amd >/dev/null 2>&1
	modprobe kvm-intel >/dev/null 2>&1

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

	# Find the vendor and device IDs
	local lspci_string="$(lspci -mmn | grep -e "^$dev" | head -n1)"
	[ -n "$lspci_string" ] || die "PCI device $dev not found"
	dev="0000:$dev"
	local vendorid="$(echo "$lspci_string" | cut -d' ' -f 3 | tr -d \")"
	local deviceid="$(echo "$lspci_string" | cut -d' ' -f 4 | tr -d \")"
	echo "Found PCI device $dev with IDs $vendorid:$deviceid"

	# Find out which driver currently runs the device.
	local orig_drvdir="$(find /sys/bus/pci/drivers -type l -name "$dev")"
	orig_drvdir="$(dirname "$orig_drvdir")"
	if [ -n "$orig_drvdir" -a "$orig_drvdir" != "." ]; then
		echo "Original driver for $dev is '$orig_drvdir'"
	else
		echo "WARNING: Did not find attached kernel driver for PCI device $dev"
		orig_drvdir=
	fi

	# Register the device to VFIO
	modprobe vfio-pci || die "Failed to load 'vfio-pci' kernel module"
	echo "$vendorid $deviceid" > /sys/bus/pci/drivers/vfio-pci/new_id ||\
		die "Failed to register PCI-id to vfio-pci driver"
	if [ -n "$orig_drvdir" ]; then
		echo "$dev" > "$orig_drvdir/unbind" ||\
			die "Failed to unbind PCI kernel driver"
	fi
	echo "$dev" > /sys/bus/pci/drivers/vfio-pci/bind ||\
		die "Failed to bind vfio-pci kernel driver"
	echo "$vendorid $deviceid" > /sys/bus/pci/drivers/vfio-pci/remove_id ||\
		die "Failed to remove PCI-id from vfio-pci driver"

	# Remember the pci dev for cleanup
	if [ -n "$orig_drvdir" ]; then
		assigned_pci_devs="$assigned_pci_devs $dev/$orig_drvdir"
	fi
}

host_pci_restore_all()
{
	for assigned_dev in $assigned_pci_devs; do
		local dev="$(echo "$assigned_dev" | cut -d'/' -f1)"
		local orig_drvdir="/$(echo "$assigned_dev" | cut -d '/' -f2-)"

		echo "Unbinding PCI device $dev from VFIO..."
		echo "$dev" > /sys/bus/pci/drivers/vfio-pci/unbind
		if [ -e "$orig_drvdir"/bind ]; then
			echo "Rebinding PCI device $dev to original driver '$orig_drvdir'..."
			echo "$dev" > "$orig_drvdir"/bind
		fi
	done
}

usage()
{
	echo "qemu-script.sh [OPTIONS] [--] [QEMU-OPTIONS]"
	echo
	echo "Options:"
	echo " --dry-run                   Do not run qemu/spice. (But do (de)allocate ressources)"
	echo " -m|--ram RAM                Amount of RAM. Default: 1024M"
	echo " -n|--net-restrict 1|0       Turn net restrict on/off. Default: 1"
	echo " -s|--spice 1|0              Use spice client. Default: 1"
	echo " -M|--mouse MOUSETYPE        Select the mouse type:"
	echo "                             -M not specified: usbtablet"
	echo "                             default: Use qemu default"
	echo "                             usbmouse: Use USB mouse"
	echo "                             usbtablet: Use USB tablet"
	echo " -u|--usb-id ABCD:1234       Use host USB device with ID ABCD:1234"
	echo " -p|--pci-id ABCD:1234       Forward PCI device with ID ABCD:1234"
	echo " -P|--pci-device 00:00.0     Forward PCI device at 00:00.0"
	echo " -T|--tap                    Set up a tap to the default host bridge"
	echo " -S|--screens 1|2            Number of screens. Default: 1"
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
	[ -n "$image_format" ] || image_format="raw"
	[ -n "$qemu_binary" ] || qemu_binary="qemu-system-i386"
	[ -n "$spice_host" ] || spice_host="127.0.0.1"
	[ -n "$spice_port" ] || spice_port="$(random_port)"
	[ -n "$rtc" ] || rtc="-rtc base=localtime,clock=host"

	# Set option-defaults
	[ -n "$opt_ram" ] || opt_ram="1024M"
	[ -n "$opt_netrestrict" ] || opt_netrestrict="$(bool_to_on_off 1)"
	[ -n "$opt_dryrun" ] || opt_dryrun=0
	[ -n "$opt_spice" ] || opt_spice=1
	[ -n "$opt_mouse" ] || opt_mouse=usbtablet
	[ -n "$opt_usetap" ] || opt_usetap=0
	[ -n "$opt_screens" ] || opt_screens=1

	# Variable defaults
	local spice_opt=
	local usbdevice_opt=
	local pcidevice_opt=
	local net0_conf=
	local net1_conf=
	local screen_opt=
	kvm_opt=
	serial_opt=

	# Basic initialization
	share_init
	serial_init
	kvm_init

	# Parse command line options
	local end=0
	while [ $# -gt 0 -a $end -eq 0 ]; do
		case "$1" in
		-h|--help)
			usage
			exit 0
			;;
		-m|--ram)
			shift
			opt_ram="$1"
			;;
		-n|--net-restrict)
			shift
			opt_netrestrict="$(bool_to_on_off "$1")"
			;;
		--dry-run)
			opt_dryrun=1
			;;
		-s|--spice)
			shift
			opt_spice="$(bool_to_1_0 "$1")"
			;;
		-M|--mouse)
			shift
			opt_mouse="$1"
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
			pcidevice_opt="$pcidevice_opt -device vfio-pci,host=$dev"
			;;
		-P|--pci-device)
			shift
			local dev="$1"

			host_pci_prepare "$dev"
			pcidevice_opt="$pcidevice_opt -device vfio-pci,host=$dev"
			;;
		-T|--tap)
			opt_usetap=1
			;;
		-S|--screens)
			shift
			opt_screens="$1"
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

	[ $opt_spice -ne 0 ] && {
		spice_opt="-spice addr=${spice_host},port=${spice_port},"
		spice_opt="${spice_opt}disable-ticketing,"
		spice_opt="${spice_opt}agent-mouse=off,"
		spice_opt="${spice_opt}disable-copy-paste,"
		spice_opt="${spice_opt}seamless-migration,"
		spice_opt="${spice_opt}plaintext-channel=main,plaintext-channel=display,"
		spice_opt="${spice_opt}plaintext-channel=cursor,plaintext-channel=inputs,"
		spice_opt="${spice_opt}plaintext-channel=record,plaintext-channel=playback"
	}

	if [ "$opt_mouse" = "default" ]; then
		true # do nothing
	elif [ "$opt_mouse" = "usbtablet" ]; then
		usbdevice_opt="$usbdevice_opt -usbdevice tablet"
	elif [ "$opt_mouse" = "usbmouse" ]; then
		usbdevice_opt="$usbdevice_opt -usbdevice mouse"
	else
		die "Invalid mouse selection"
	fi

	net0_conf="-netdev user,id=net0,restrict=${opt_netrestrict},net=192.168.5.1/24,smb=${sharedir},smbserver=192.168.5.4"
	net0_conf="$net0_conf -device rtl8139,netdev=net0,mac=00:11:22:AA:BB:CC"
	if [ "$opt_usetap" -ne 0 ]; then
		net1_conf="-netdev tap,id=net1"
		net1_conf="$net1_conf -device rtl8139,netdev=net1,mac=00:11:22:AA:BB:CD"
	fi

	if [ "$opt_screens" = "1" ]; then
		local screen_opt=
	elif [ "$opt_screens" = "2" ]; then
		local screen_opt="-device qxl"
	else
		die "Invalid screen selection"
	fi

	run_qemu \
		-name "$(basename "$image")" \
		$kvm_opt \
		$spice_opt \
		-m "$opt_ram" \
		-drive file="$image",index=0,format="$image_format",discard=on,media=disk \
		-boot c \
		$net0_conf \
		$net1_conf \
		-usb \
		$usbdevice_opt \
		$serial_opt \
		$pcidevice_opt \
		-vga qxl \
		$screen_opt \
		$rtc \
		$qemu_opts \
		"$@"
	run_spice_client
	host_pci_restore_all
}
