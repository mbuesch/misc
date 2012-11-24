# example VPN config script

vpn_prepare()
{
	example_ipaddr=192.168.0.1
	example_openvpn_port=1194
	example_openvpn_tundev="$(get_unused_tun_device)"
	[ -n "$example_openvpn_tundev" ] || die "Failed to get TUN device"
	example_openvpn_ca="/etc/openvpn/keys/example-ca.crt"
	example_openvpn_cert="/etc/openvpn/keys/example.crt"
	example_openvpn_key="/etc/openvpn/keys/example.key"
	example_openvpn_pid=
	example_openvpn_log="$(mktemp /tmp/example.openvpn.log.XXXXXX)"
	[ -w "$example_openvpn_log" ] || die "Failed to create example log"
}

vpn_stop()
{
	openvpn_kill "example" "$example_openvpn_pid" \
		"$example_openvpn_log"
	example_openvpn_pid=
}

vpn_start()
{
	openvpn --client \
		--dev "$example_openvpn_tundev" \
		--proto tcp \
		--remote "$example_ipaddr" "$example_openvpn_port" \
		--nobind \
		--ca "$example_openvpn_ca" \
		--cert "$example_openvpn_cert" \
		--key "$example_openvpn_key" \
		--remote-cert-tls server \
		--cipher BF-CBC \
		--keysize 128 \
		--auth SHA1 \
		--comp-lzo \
		--persist-key \
		--persist-tun \
		--verb 4 \
		--log "$example_openvpn_log" &
	example_openvpn_pid=$!

	openvpn_wait_connect "example" "$example_openvpn_pid" \
		"$example_openvpn_log"
}

vpn_destroy()
{
	rm -f "$example_openvpn_log"
}
