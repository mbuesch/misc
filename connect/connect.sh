#!/bin/sh
#
# Network connection script
#
# Copyright (c) 2012 Michael Buesch <m@bues.ch>
# Licensed under GNU GPL version 2 or later.
#

scriptdir="$(dirname "$0")"
[ "$(echo "$scriptdir" | cut -c1)" = '/' ] || scriptdir="$PWD/$scriptdir"

vpndir="$scriptdir/vpn"
dundir="$scriptdir/dun"


debug()
{
	[ -n "$opt_debug" ] && echo "$*"
}

info()
{
	echo "$*"
}

info_n()
{
	echo -n "$*"
}

warn()
{
	echo "Warning: $*" >&2
}

error()
{
	echo "ERROR: $*" >&2
}

die()
{
	error "$*"
	cleanup_handler
	exit 1
}

# $1=program_name
have_program()
{
	which "$1" >/dev/null 2>&1
}

# $1=option
check_bool_opt()
{
	local option="$1"

	[ "$option" = "1" -o \
	  "$option" = "on" -o \
	  "$option" = "true" ]
}

rfcomm()
{
	# Force rfcomm into line buffered stdout
	stdbuf -oL rfcomm "$@"
}

# Start bluetooth-agent.
# Returns the PID of bluetooth-agent
# $1=passkey (optional. Defaults to 1234)
bluetooth_agent_start()
{
	local passkey="$1"
	local pid=

	[ -n "$passkey" ] || passkey="1234"
	info "Starting bluetooth agent with passkey '$passkey'"
	bluetoothctl << EOF
power on
discoverable off
pairable on
agent on
default-agent
EOF
#	bluetooth-agent "$passkey" &
	pid=$!
	sleep 1
	return $pid
}

# $1=apn
make_chatscript()
{
	local apn="$1"

	cat << EOF
TIMEOUT		120
ABORT		'BUSY'
ABORT		'ERROR'
ABORT		'NO CARRIER'
''		'ATE1'
OK		AT+CGDCONT=1,"IP","${apn}"
OK		ATD*99#
CONNECT		\\d\\c
EOF
}

random_byte()
{
	hexdump -n1 -e'/1 "%u"' /dev/urandom
}

random_hex_byte()
{
	hexdump -n1 -e'/1 "%02X"' /dev/urandom
}

random_word()
{
	hexdump -n2 -e'/2 "%u"' /dev/urandom
}

random_macaddr()
{
	# Clear local-admin and mcast bits
	echo -n "$(printf '%02X' $(($(random_byte) & ~3))):"
	echo -n "$(random_hex_byte):$(random_hex_byte):"
	echo -n "$(random_hex_byte):$(random_hex_byte):"
	echo -n "$(random_hex_byte)"
}

get_default_route_ipaddr()
{
	ip route show | grep '^default' | awk '{print $3;}'
}

get_default_route_if()
{
	ip route show | grep '^default' | awk '{print $5;}'
}

get_unused_tun_device()
{
	for i in $(seq 0 99); do
		local tun="tun$i"
		ip link show dev "$tun" >/dev/null 2>&1 || {
			echo -n "$tun"
			return
		}
	done
}

# $1=basename
get_unused_dev_node()
{
	local base="$1"

	for i in $(seq 0 99); do
		local dev="/dev/$base$i"
		[ -e "$dev" ] || {
			echo -n "$dev"
			return
		}
	done
}

string_is_false()
{
	local str="$1"

	[ -z "$str" -o "$str" = "0" -o \
	  "$str" = "off" -o "$str" = "no" -o \
	  "$str" = "false" ]
}

# $1=pid
pid_is_alife()
{
	local pid="$1"

	[ -n "$pid" -a -d "/proc/$pid" ]
}

# $1=type, $2=name, $3=PID, $4=ready_callback, $5=timeout_decisec
wait_pid_alife_and_callback()
{
	local type="$1"
	local name="$2"
	local pid="$3"
	local ready_callback="$4"
	local timeout_decisec="$5"

	info_n "Waiting for '$name' '$type'..."
	local i=0
	while true; do
		sleep 0.1
		pid_is_alife "$pid" || {
			cat "$logfile"
			die "'$name' '$type' died"
		}
		eval "$ready_callback" && break
		i="$(expr $i + 1)"
		[ $i -ge $timeout_decisec ] && {
			cat "$logfile"
			die "'$name' '$type' timeout"
		}
		[ "$(expr $i % 10)" -eq 0 ] && info_n "."
	done
	info ""
}

# $1=type, $2=name, $3=PID, $4=dead_callback, $5=timeout_decisec
wait_pid_dead_or_callback()
{
	local type="$1"
	local name="$2"
	local pid="$3"
	local dead_callback="$4"
	local timeout_decisec="$5"

	info_n "Waiting for '$name' '$type' (pid $pid) to die..."
	local i=0
	while true; do
		sleep 0.1
		pid_is_alife "$pid" || break
		eval "$dead_callback" && break
		i="$(expr $i + 1)"
		[ $i -ge $timeout_decisec ] && {
			cat "$logfile"
			die "'$name' '$type' timeout"
		}
		[ "$(expr $i % 10)" -eq 0 ] && info_n "."
	done
	info ""
}

# $1=type, $2=name, $3=PID, $4=logfile, $5=log_regex, $6=timeout_decisec
wait_pid_alife_and_logmsg()
{
	local type="$1"
	local name="$2"
	local pid="$3"
	local logfile="$4"
	local log_regex="$5"
	local timeout_decisec="$6"

	ready_callback() {
		grep -qe "$log_regex" "$logfile"
	}

	wait_pid_alife_and_callback "$type" "$name" "$pid" \
		ready_callback "$timeout_decisec"
}

# $1=type, $2=name, $3=PID, $4=logfile, $5=log_regex, $6=timeout_decisec
wait_pid_dead_or_logmsg()
{
	local type="$1"
	local name="$2"
	local pid="$3"
	local logfile="$4"
	local log_regex="$5"
	local timeout_decisec="$6"

	dead_callback() {
		grep -qe "$log_regex" "$logfile"
	}

	wait_pid_dead_or_callback "$type" "$name" "$pid" \
		dead_callback "$timeout_decisec"
}

# $1=hcidev
hci_dev_up()
{
	local hcidev="$1"

	hciconfig "$hcidev" up ||\
		die "Failed to bring bluetooth device '$hcidev' up"
}

# $1=hcidev
hci_dev_down()
{
	local hcidev="$1"

	hciconfig "$hcidev" down ||\
		warn "Failed to bring bluetooth device '$hcidev' down"
}

# $1=name, $2=PID, $3=logfile
openvpn_wait_connect()
{
	wait_pid_alife_and_logmsg "OpenVPN" "$1" "$2" "$3" \
		"Initialization Sequence Completed" 900
}

# $1=name, $2=PID, $3=logfile
openvpn_wait_disconnect()
{
	wait_pid_dead_or_logmsg "OpenVPN" "$1" "$2" "$3" \
		"received, process exiting" 300
}

# $1=name, $2=PID, $3=logfile
rfcomm_wait_connect()
{
	wait_pid_alife_and_logmsg "rfcomm" "$1" "$2" "$3" \
		"Connected /dev/rfcomm" 600
	sleep 0.5
}

# $1=name, $2=PID, $3=logfile
rfcomm_wait_disconnect()
{
	wait_pid_dead_or_logmsg "rfcomm" "$1" "$2" "$3" \
		"Disconnected" 300
}

# $1=name, $2=PID, $3=logfile
pppd_wait_connect()
{
	wait_pid_alife_and_logmsg "pppd" "$1" "$2" "$3" \
		"local  IP address" 1000
	sleep 0.5
}

# $1=name, $2=PID, $3=logfile
pppd_wait_disconnect()
{
	wait_pid_dead_or_logmsg "pppd" "$1" "$2" "$3" \
		"Connection terminated" 300
}

# $1=pid
kill_pid()
{
	local pid="$1"

	pid_is_alife "$pid" || return
	kill -TERM "$pid" >/dev/null 2>&1
}

# $1=type, $2=name, $3=PID, $4=wait_callback, $5=logfile
generic_kill_with_logfile()
{
	local type="$1"
	local name="$2"
	local pid="$3"
	local wait_callback="$4"
	local logfile="$5"

	[ -z "$pid" ] && return

	debug "Killing '$name' '$type' daemon..."
	kill_pid "$pid"
	eval "$wait_callback"
	truncate -s 0 "$logfile" || \
		die "Failed to truncate '$type' '$name' logfile"
}

# $1=name, $2=PID, $3=logfile
openvpn_kill()
{
	local name="$1"
	local pid="$2"
	local logfile="$3"

	wait_callback() {
		openvpn_wait_disconnect "$name" "$pid" "$logfile"
	}

	generic_kill_with_logfile "OpenVPN" "$name" "$pid" \
		wait_callback "$logfile"
}

# $1=name, $2=PID
bluetooth_agent_kill()
{
	local name="$1"
	local pid="$2"

	debug "Killing '$name' bluetooth-agent..."
	kill_pid "$pid"
}

# $1=name, $2=PID, $3=logfile
rfcomm_kill()
{
	local name="$1"
	local pid="$2"
	local logfile="$3"

	wait_callback() {
		rfcomm_wait_disconnect "$name" "$pid" "$logfile"
	}

	generic_kill_with_logfile "rfcomm" "$name" "$pid" \
		wait_callback "$logfile"
}

# $1=name, $2=PID, $3=logfile
pppd_kill()
{
	local name="$1"
	local pid="$2"
	local logfile="$3"

	wait_callback() {
		pppd_wait_disconnect "$name" "$pid" "$logfile"
	}

	generic_kill_with_logfile "pppd" "$name" "$pid" \
		wait_callback "$logfile"
}

wlan_macaddr_spoof()
{
	[ "$opt_wlanif" = "none" ] && return
	[ -n "$opt_macspoof" ] && string_is_false "$opt_macspoof" && return

	local macaddr=
	if [ -f "$opt_macspoof" ]; then
		[ -r "$opt_macspoof" ] || \
			die "Can't read MAC-spoof file '$opt_macspoof'"
		local count="$(wc -w "$opt_macspoof" | awk '{print $1;}')"
		[ -z "$count" -o "$count" = "0" ] && \
			die "No MAC-addresses in '$opt_macspoof'"
		local picked="$(($(random_word) % $count + 1))"
		macaddr="$(cat "$opt_macspoof" | tr '\n' ' ' | awk '{print $'$picked';}')"
	elif [ -n "$opt_macspoof" ]; then
		macaddr="$opt_macspoof"
	else
		macaddr="$(random_macaddr)"
	fi
	[ -n "$macaddr" ] || die "Failed to pick a MAC-address from '$opt_macspoof'"

	info "Spoofing MAC address '$macaddr'"
	ip link set down dev "$opt_wlanif" || \
		die "Failed to bring '$opt_wlanif' down"
	ip link set address "$macaddr" dev "$opt_wlanif" || \
		die "Failed to set MAC address '$macaddr' on '$opt_wlanif'"
}

wlan_connect()
{
	[ "$opt_wlanif" = "none" -o "$opt_wlanif" = "-" ] && return

	debug "Shutting down system wpa_supplicant..."
	(
		local wpa_funcs="/etc/wpa_supplicant/functions.sh"
		[ -f "$wpa_funcs" ] && {
			. "$wpa_funcs"
			kill_wpa_cli
			kill_wpa_supplicant
		}
	)
	pkill wpa_supplicant

	wlan_macaddr_spoof

	info "Connecting WLAN..."

	wpa_supplicant_pidfile="/var/run/wpa_supplicant-connect-$opt_wlanif.pid"
	wpa_supplicant -B -Dnl80211 \
		-i "$opt_wlanif" -c "$opt_suppconf" \
		-P "$wpa_supplicant_pidfile"

	ready_callback() {
		wpa_cli -i "$opt_wlanif" status | \
			grep -qe 'wpa_state=COMPLETED'
	}

	sleep 0.5
	wait_pid_alife_and_callback "WLAN" "$opt_wlanif" \
		"$(cat "$wpa_supplicant_pidfile")" ready_callback 600

	local ps="off"
	check_bool_opt "$opt_powersave" && ps="on"
	iw dev "$opt_wlanif" set power_save "$ps" || \
		warn "Failed to turn power saving on '$opt_wlanif' $ps"
}

wlan_disconnect()
{
	[ "$opt_wlanif" = "none" -o "$opt_wlanif" = "-" ] && return

	debug "Disconnecting WLAN..."

	[ -z "$wpa_supplicant_pidfile" ] && return
	local pid="$(cat "$wpa_supplicant_pidfile")"
	kill_pid "$pid"
	wpa_supplicant_pidfile=

	dead_callback() {
		! wpa_cli -i "$opt_wlanif" status >/dev/null 2>&1
	}

	wait_pid_dead_or_callback "WLAN" "$opt_wlanif" \
		"$pid" dead_callback 300
}

dhcp_connect()
{
	[ -n "$opt_nodhcp" ] && return

	info "Configuring DHCP..."

	dhclient_pidfile="/var/run/dhclient-$opt_wlanif.pid"
	dhclient -v -4 -pf "$dhclient_pidfile" "$opt_wlanif" 2>&1 |\
		grep -Ee '(^DHCP)|(^bound to)'
}

dhcp_disconnect()
{
	[ -n "$opt_nodhcp" ] && return

	debug "Killing DHCP..."

	[ -z "$dhclient_pidfile" ] && return
	kill_pid "$(cat "$dhclient_pidfile")"
	dhclient_pidfile=
}

resolver_adjust()
{
	if [ -n "$opt_resolver" ]; then
		# Static resolver specified.

		have_program resolvconf && {
			resolvconf --updates-are-enabled && {
				info "Disabling resolvconf updates"
				resolvconf --disable-updates
			}
		}

		debug "Setting resolver to '$opt_resolver'..."
		echo "nameserver $opt_resolver" > /etc/resolv.conf ||\
			die "Failed to set resolver to '$opt_resolver'"
	else
		# No static resolver specified.

		have_program resolvconf && {
			resolvconf --updates-are-enabled || {
				info "Enabling resolvconf updates"
				resolvconf --enable-updates
			}
		}
	fi
}

source_config() # $1=basedir, $2=script_name
{
	local basedir="$1"
	local name="$2"
	local script="$scriptdir/$basedir/$name.sh"

	[ -f "$script" ] || \
		die "No config for '$basedir/$name'"
	. "$script" || \
		die "Config '$basedir/$name' returned an error."
}

vpn_connect()
{
	[ -z "$opt_vpns" ] && return

	for vpn_name in $opt_vpns; do
		info "Connecting VPN '$vpn_name'..."

		# Define defaults
		vpn_prepare() { true; }
		vpn_start() { die "No vpn_start() callback in '$vpn_name'"; }
		vpn_routing_setup() { true; }

		# Source the config
		source_config vpn "$vpn_name"

		# Perform the configuration
		vpn_prepare
		vpn_start
		vpn_routing_setup
	done
}

vpn_disconnect()
{
	[ -z "$opt_vpns" ] && return

	for vpn_name in $(echo $opt_vpns | tac -s' '); do
		debug "Disconnecting VPN '$vpn_name'..."

		# Define defaults
		vpn_stop() { true; }
		vpn_routing_cleanup() { true; }
		vpn_destroy() { true; }

		# Source the config
		source_config vpn "$vpn_name"

		# Perform cleanup
		vpn_routing_cleanup
		vpn_stop
		vpn_destroy
	done
}

dun_connect()
{
	[ -z "$opt_duns" ] && return

	for dun_name in $opt_duns; do
		info "Connecting DUN '$dun_name'..."

		# Define defaults
		dun_prepare() { true; }
		dun_start() { die "No dun_start() callback in '$dun_name'"; }
		dun_routing_setup() { true; }

		# Source the config
		source_config dun "$dun_name"

		# Perform the configuration
		dun_prepare
		dun_start
		dun_routing_setup
	done
}

dun_disconnect()
{
	[ -z "$opt_duns" ] && return

	for dun_name in $(echo $opt_duns | tac -s' '); do
		debug "Disconnecting DUN '$dun_name'..."

		# Define defaults
		dun_stop() { true; }
		dun_routing_cleanup() { true; }
		dun_destroy() { true; }

		# Source the config
		source_config dun "$dun_name"

		# Perform cleanup
		dun_routing_cleanup
		dun_stop
		dun_destroy
	done
}

stop_nm()
{
	systemctl status network-manager.service |\
	  grep -qe 'Active: active (running)' && {
		debug "Stopping network-manager..."
		systemctl stop network-manager.service
		sleep 1
	}
}

wait_loop()
{
	info "Connections up and running. [Press ^C to abort]"
	# Wait for signal
	while true; do
		sleep 60
		#TODO check connection
	done
}

cleanup_handler()
{
	debug "Cleanup..."

	vpn_disconnect
	dhcp_disconnect
	wlan_disconnect
	dun_disconnect

	exit 0
}

usage()
{
	echo "connect.sh [OPTIONS]"
	echo
	echo "Options:"
	echo " -w|--wlanif IF       WLAN interface (default wlan0)"
	echo " -m|--macspoof MAC/FILE/no Use MAC address or FILE."
	echo " -p|--powersave on/off  Turn WLAN power-saving on/off."
	echo " -S|--suppconf FILE   WPA-supplicant config"
	echo " -D|--nodhcp          Don't configure DHCP"
	echo " -R|--resolver IP     Resolver IP address (default dhcp or 127.0.0.1)"
	echo " -u|--dun NAME        Connect Dial Up Network NAME"
	echo " -V|--vpn NAME        Connect to VPN"
	echo " -P|--httpproxy IP:PORT[:AUTH:PASS]  Use HTTP proxy"
	echo " -d|--debug           Enable debug messages"
	echo " -h|--help            Show this help text"
}

parse_args()
{
	while [ $# -ne 0 ]; do
		case "$1" in
		-S|--suppconf)
			shift
			local path="$1"
			[ -n "$path" ] || die "-S|--suppconf needs an argument"
			opt_suppconf="$path"
			;;
		-w|--wlanif)
			shift
			local name="$1"
			[ -n "$name" ] || die "-w|--wlanif needs an argument"
			opt_wlanif="$name"
			;;
		-m|--macspoof)
			shift
			local path="$1"
			[ -n "$path" ] || die "-m|--macspoof needs an argument"
			opt_macspoof="$path"
			;;
		-p|--powersave)
			shift
			local ps="$1"
			[ -n "$ps" ] || die "-p|--powersave needs an argument"
			opt_powersave="$ps"
			;;
		-R|--resolver)
			shift
			local res="$1"
			[ -n "$res" ] || die "-R|--resolver needs an argument"
			opt_resolver="$res"
			;;
		-u|--dun)
			shift
			local name="$1"
			[ -n "$name" ] || die "-u|--dun needs an argument"
			opt_duns="$opt_duns $name"
			;;
		-V|--vpn)
			shift
			local name="$1"
			[ -n "$name" ] || die "-V|--vpn needs an argument"
			opt_vpns="$opt_vpns $name"
			;;
		-P|--httpproxy)
			shift
			local conf="$1"
			[ -n "$conf" ] || die "-P|--httpproxy needs an argument"
			opt_httpproxy_host="$(echo "$conf" | cut -d':' -f1)"
			opt_httpproxy_port="$(echo "$conf" | cut -d':' -f2)"
			opt_httpproxy_auth="$(echo "$conf" | cut -d':' -f3)"
			opt_httpproxy_pass="$(echo "$conf" | cut -d':' -f4)"
			[ -n "$opt_httpproxy_host" -a \
			  -n "$opt_httpproxy_port" ] || \
				die "-P|--httpproxy needs HOST:PORT"
			;;
		-D|--nodhcp)
			opt_nodhcp=1
			;;
		-d|--debug)
			opt_debug=1
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			die "Unknown option: $1"
			;;
		esac
		shift
	done
}

opt_debug=
opt_vpns=
opt_wlanif="wlan0"
opt_macspoof=
opt_powersave="on"
opt_suppconf="/etc/wpa_supplicant/wpa_supplicant.conf"
opt_duns=
opt_nodhcp=
opt_resolver=
opt_httpproxy_host=
opt_httpproxy_port=
opt_httpproxy_auth=
opt_httpproxy_pass=
parse_args "$@"

[ -n "$opt_duns" ] && {
	# DUN implies no WLAN and no DHCP
	opt_wlanif=none
	opt_nodhcp=1
}

[ -z "$opt_resolver" -a -n "$opt_nodhcp" ] && {
	# Default resolver to localhost
	opt_resolver="127.0.0.1"
}

TRAPPED_SIGS="INT TERM"
trap cleanup_handler $TRAPPED_SIGS

while true; do
	stop_nm
	wlan_connect
	dun_connect
	resolver_adjust
	dhcp_connect
	vpn_connect

	wait_loop

	trap true $TRAPPED_SIGS
	cleanup_handler
	trap cleanup_handler $TRAPPED_SIGS
done
exit 1
