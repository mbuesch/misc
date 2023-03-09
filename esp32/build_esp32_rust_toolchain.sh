#!/bin/sh
#
# ESP32 Rust toolchain install script.
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


XTENSA_CLANG_URL="https://github.com/espressif/llvm-project/releases/download/esp-15.0.0-20221201/llvm-esp-15.0.0-20221201-linux-amd64.tar.xz"
XTENSA_CLANG_SHA256="839e5adfa7f44982e8a2d828680f6e4aa435dcd3d1df765e02f015b04286056f"


die()
{
	echo "$*" >&2
	exit 1
}

show_help()
{
	echo "Usage: build_esp32_rust_toolchain.sh <OPTIONS> [INSTALLDIR]"
	echo
	echo "Options:"
	echo " -h|--help                     Print help."
	echo
	echo
	echo "Install toolchain to $HOME/rust-esp32-xtensa-toolchain"
	echo "  ./build_esp32_rust_toolchain.sh"
	echo
	echo "Install toolchain to another destination"
	echo "  ./build_esp32_rust_toolchain.sh /home/user/directory"
}

parse_args()
{
	# Defaults:
	INSTALLDIR="$HOME/rust-esp32-xtensa-toolchain"

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

check_build_environment()
{
	[ "$(id -u)" = "0" ] && die "Do not run this as root!"
	checkprog curl
	checkprog wget
	checkprog gcc
	checkprog make
	checkprog nproc
	checkprog tar
	checkprog git
	checkprog schedtool
	checkprog sha256sum
	checkprog python3
	checkprog help2man # for crosstool-ng
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

	# Create the build directories.
	mkdir -p "$INSTALLDIR" || die "Failed to create INSTALLDIR"

	# Unset flags
	unset CFLAGS
	unset CXXFLAGS
	unset CPPFLAGS
}

build_python2()
{
	if [ -d "$INSTALLDIR/python2" ]; then
		echo "Python2 is already built."
		return
	fi

	echo "Building Python2..."
	rm -rf "$INSTALLDIR/python2" "$INSTALLDIR/python2-src" || die "Failed to clean Python2"
	mkdir -p "$INSTALLDIR/python2" "$INSTALLDIR/python2-src" || die "Failed to create Python2 directory"
	cd "$INSTALLDIR/python2-src" || die "Failed to switch to Python2 src directory"
	wget "https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tar.xz"
	[ "$(sha256sum -b "Python-2.7.18.tar.xz" | cut -f1 -d' ')" = "b62c0e7937551d0cc02b8fd5cb0f544f9405bafc9a54d3808ed4594812edef43" ] ||\
		die "Python2 checksum failed"
	tar xf "Python-2.7.18.tar.xz" || die "Failed to extract Python2"
	cd "Python-2.7.18" || die "Failed to switch to Python2 source"
	./configure --prefix="$INSTALLDIR/python2" || die "Failed to configure Python2"
	make -j "$(nproc)" || die "Failed to make Python2"
	make -j "$(nproc)" install || die "Failed to install Python2"
}

build_xtensa_crosstoolng()
{
	if [ -d "$INSTALLDIR/crosstool-ng" ]; then
		echo "Xtensa toolchain is already built."
		return
	fi

	echo "Building Xtensa toolchain..."
	local oldpath="$PATH"
	export PATH="$INSTALLDIR/python2/bin:$PATH"

	rm -rf "$INSTALLDIR/crosstool-ng" || die "Failed to clean crosstool-ng"
	mkdir -p "$INSTALLDIR/crosstool-ng" || die "Failed to create crosstool-ng directory"
	cd "$INSTALLDIR/crosstool-ng" || die "Failed to switch to crosstool-ng directory"
	git clone --depth 1 "https://github.com/espressif/crosstool-NG.git"
	cd "$INSTALLDIR/crosstool-ng/crosstool-NG" || die "Failed to switch to crosstool-ng src"
	git submodule update --init --depth 1 || die "Failed to clone crosstool-ng submodules"
	./bootstrap || die "Crosstool-ng bootstrap failed"
	./configure --enable-local || die "Crosstool-ng configure failed"
	make -j "$(nproc)" || die "Crosstool-ng make failed"
	cp ./samples/xtensa-esp32-elf/crosstool.config ./.config || die "Crosstool-ng config copy failed"
	./ct-ng upgradeconfig || die "Crosstool-ng upgradeconfig failed"
	./ct-ng oldconfig || die "Crosstool-ng oldconfig failed"
	make -r -j "$(nproc)" -f ./ct-ng build || die "Crosstool-ng build failed"

	export PATH="$oldpath"
}

download_xtensa_clang()
{
	if [ -d "$INSTALLDIR/xtensa-clang" ]; then
		echo "Xtensa clang is already downloaded."
		return
	fi

	echo "Downloading and installing xtensa clang..."
	rm -rf "$INSTALLDIR/xtensa-clang" || die "Failed to clean xtensa-clang"
	mkdir -p "$INSTALLDIR/xtensa-clang" || die "Failed to create xtensa-clang directory"
	cd "$INSTALLDIR/xtensa-clang" || die "Failed to switch to xtensa-clang directory"
	wget "$XTENSA_CLANG_URL" || die "Failed to download xtensa-clang"
	local file="$(basename "$XTENSA_CLANG_URL")"
	[ "$(sha256sum -b "$file" | cut -f1 -d' ')" = "$XTENSA_CLANG_SHA256" ] ||\
		die "xtensa-clang checksum failed"
	tar xf "$file" || die "Failed to extract xtensa-clang"
}

build_rust()
{
	echo "Building Rust toolchain..."

	rm -rf "$INSTALLDIR/rust" || die "Failed to clean rust"
	mkdir -p "$INSTALLDIR/rust" || die "Failed to create rust directory"

	# Create activation script
	cat > "$INSTALLDIR/activate" <<EOF
if [ -z "\$RUST_ESP32_XTENSA_TOOLCHAIN_ACTIVE" ]; then
	unset CFLAGS
	unset CXXFLAGS
	unset CPPFLAGS
	export RUSTUP_HOME="$INSTALLDIR/rust/rust-install/rustup"
	export CARGO_HOME="$INSTALLDIR/rust/rust-install/cargo"
	export PATH="\$CARGO_HOME/bin:$INSTALLDIR/crosstool-ng/crosstool-NG/builds/xtensa-esp32-elf/bin:\$PATH"
	export LIBCLANG_PATH="$INSTALLDIR/xtensa-clang/esp-clang/lib"
	PS1="rust-esp32/\$PS1"
	export RUST_ESP32_XTENSA_TOOLCHAIN_ACTIVE=1
fi
EOF
	[ $? -eq 0 ] || die "Failed to create activate script"

	# Install nightly
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		cd "$INSTALLDIR/rust" || die "Failed to switch to rust directory"
		curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > rustup-init.sh ||\
			die "Failed to fetch rustup-init"
		sh rustup-init.sh --default-toolchain nightly --no-modify-path -y || die "rustup-init.sh failed"
		cargo install ldproxy || die "Failed to install ldproxy"
		cargo install cargo-espmonitor || die "Failed to install cargo-espmonitor"
		cargo install cargo-espflash || die "Failed to install cargo-espflash"
		cargo install cargo-generate || die "Failed to install cargo-generate"
	) || die
	# Build rust esp32 compiler
	(
		. "$INSTALLDIR/activate" || die "Failed to activate rust environment"
		mkdir -p "$INSTALLDIR/rust/rust-esp32" || die "Failed to create rust esp32 directory"
		cd "$INSTALLDIR/rust/rust-esp32" || die "Failed to switch to rust esp32 directory"
		git clone --depth 1 "https://github.com/esp-rs/rust" || die "Failed to clone rust esp32"
		cd "$INSTALLDIR/rust/rust-esp32/rust" || die "Failed to switch to rust esp32 source directory"
		git submodule update --init --depth 1 || die "Failed to clone rust esp32 submodules"
		./configure --experimental-targets=Xtensa || die "Failed to configure rust esp32"
		./x.py build --stage 2 || die "Failed to build rust esp32"
		rustup toolchain link esp "$INSTALLDIR/rust/rust-esp32/rust/build/x86_64-unknown-linux-gnu/stage2" ||\
			die "Failed to link rust esp32 toolchain"
	) || die
}

parse_args "$@"
check_build_environment
prepare
build_python2
build_xtensa_crosstoolng
download_xtensa_clang
build_rust

echo
echo
echo
echo "Successfully built and installed all tools to: $INSTALLDIR"
echo
