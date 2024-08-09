#!/bin/sh
#
# Install prebuilt ESP32 Rust toolchain.
#
# Author: Michael Buesch <m@bues.ch>
#
# This code is Public Domain.
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
# RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
# USE OR PERFORMANCE OF THIS SOFTWARE.
#

die()
{
	echo "$*" >&2
	exit 1
}

show_help()
{
	echo "Usage: install_esp32_rust_toolchain.sh <OPTIONS> [INSTALLDIR]"
	echo
	echo "Options:"
	echo " -h|--help                     Print help."
	echo
	echo
	echo "Install toolchain to $HOME/rust-esp32-prebuilt-toolchain"
	echo "  ./install_esp32_rust_toolchain.sh"
	echo
	echo "Install toolchain to another destination"
	echo "  ./install_esp32_rust_toolchain.sh /home/user/directory"
}

parse_args()
{
	# Defaults:
	INSTALLDIR="$HOME/rust-esp32-prebuilt-toolchain"

	# Parse command line options
	while [ $# -ge 1 ]; do
		[ "$(printf '%s' "$1" | cut -c1)" != "-" ] && break

		case "$1" in
		-h|--help)
			show_help
			exit 0
			;;
		*)
			echo "Unknown option: $1"
			exit 1
			;;
		esac
		shift
	done

	if [ $# -ge 1 -a -n "$1" ]; then
		# User defined INSTALLDIR
		INSTALLDIR="$1"
	fi
}

checkprog()
{
	local prog="$1"
	which "$prog" >/dev/null ||\
		die "$prog is not installed. Please install it by use of the distribution package manager (apt, apt-get, rpm, etc...)"
}

check_environment()
{
	[ "$(id -u)" = "0" ] && die "Do not run this as root!"
	checkprog curl
	checkprog schedtool
	[ -e "$HOME/export-esp.sh" ] &&\
		die "There already is a '$HOME/export-esp.sh'. This program would overwrite it."
}

prepare()
{
	# Resolve paths.
	INSTALLDIR="$(realpath -m -s "$INSTALLDIR")"
	echo "INSTALLDIR=$INSTALLDIR"
	[ -n "$INSTALLDIR" ] || die "Failed to resolve install directory"
	echo

	# Set priority
	schedtool -D -n19 $$ || die "Failed to reduce process priority"

	# Create the install directory.
	mkdir -p "$INSTALLDIR" || die "Failed to create INSTALLDIR"

	# Unset flags
	unset CFLAGS
	unset CXXFLAGS
	unset CPPFLAGS
	unset CARGO_REGISTRIES_CRATES_IO_PROTOCOL
}

install_rust()
{
	echo "Installing Rust..."

	rm -rf "$INSTALLDIR/rust" || die "Failed to clean rust"
	mkdir -p "$INSTALLDIR/rust" || die "Failed to create rust directory"

	# Create activation script
	cat > "$INSTALLDIR/activate" <<EOF
if [ -z "\$RUST_ESP32_TOOLCHAIN_ACTIVE" ]; then
	unset CFLAGS
	unset CXXFLAGS
	unset CPPFLAGS
	export RUSTUP_HOME="$INSTALLDIR/rust/rustup"
	export CARGO_HOME="$INSTALLDIR/rust/cargo"
	export PATH="\$CARGO_HOME/bin:\$PATH"
	[ -f "$INSTALLDIR/rust/export-esp.sh" ] && . "$INSTALLDIR/rust/export-esp.sh"
	PS1="rust-esp32/\$PS1"
	export RUST_ESP32_TOOLCHAIN_ACTIVE=1
fi
EOF
	[ $? -eq 0 ] || die "Failed to create activate script"

	# Install stable
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		cd "$INSTALLDIR/rust" || die "Failed to switch to rust directory"
		curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > rustup-init.sh ||\
			die "Failed to fetch rustup-init"
		sh rustup-init.sh --default-toolchain stable --no-modify-path -y || die "rustup-init.sh failed"
	) || die

	# Install nightly
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		rustup toolchain install nightly || die "Failed to install rust-nightly"
	) || die
}

install_utils()
{
	echo "Installing utilities..."
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		cargo +stable install ldproxy || die "Failed to install ldproxy"
		cargo +stable install cargo-espmonitor || die "Failed to install cargo-espmonitor"
		cargo +stable install --locked --git https://github.com/esp-rs/espflash.git --rev 233490736646ca7bc29463a98df98d7ccf53439d cargo-espflash || die "Failed to install cargo-espflash"
		cargo +stable install cargo-generate || die "Failed to install cargo-generate"
		cargo +stable install cargo-cache || die "Failed to install cargo-cache"
		cargo +stable install cargo-audit || die "Failed to install cargo-audit"
		cargo +stable install cargo-edit || die "Failed to install cargo-edit"
		cargo +stable install --locked bacon || die "Failed to install bacon"
	) || die
}

install_espup()
{
	echo "Installing espup..."
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		cargo +stable install espup || die "Failed to install espup"
	) || die
}

install_esp_toolchain()
{
	echo "Installing ESP toolchain..."
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		rm -rf "$HOME/.espup"
		espup install || die "Failed to install esp toolchain"
		mv "$HOME/export-esp.sh" "$INSTALLDIR/rust/" || die "Failed to move export script"
	) || die
}

cargo_clean()
{
	echo "Cleaning up..."
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		cargo cache -a || die "Failed to autoclean the cargo cache"
	) || die
}

parse_args "$@"
check_environment
prepare
install_rust
install_utils
install_espup
install_esp_toolchain
cargo_clean

echo
echo
echo
echo "Successfully installed all tools to: $INSTALLDIR"
echo
