#!/bin/sh
#
# AVR GCC toolchain install script.
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

BINUTILS_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/binutils/binutils-2.43.1.tar.xz"
BINUTILS_SHA256="13f74202a3c4c51118b797a39ea4200d3f6cfbe224da6d1d95bb938480132dfd"

GCC_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz"
GCC_SHA256="a7b39bc69cbf9e25826c5a60ab26477001f7c08d85cec04bc0e29cabed6f3cc9"

AVRLIBC_URL="https://github.com/avrdudes/avr-libc/releases/download/avr-libc-2_2_1-release/avr-libc-2.2.1.tar.bz2"
AVRLIBC_SHA256="006a6306cbbc938c3bdb583ac54f93fe7d7c8cf97f9cde91f91c6fb0273ab465"

AVRDUDE_URL="https://github.com/avrdudes/avrdude/releases/download/v8.0/avrdude-8.0.tar.gz"
AVRDUDE_SHA256="a689d70a826e2aa91538342c46c77be1987ba5feb9f7dab2606b8dae5d2a52d5"

GDB_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/gdb/gdb-15.1.tar.xz"
GDB_SHA256="38254eacd4572134bca9c5a5aa4d4ca564cbbd30c369d881f733fb6b903354f2"

AVRA_URL="https://github.com/Ro5bert/avra/archive/refs/tags/1.4.2.tar.gz"
AVRA_SHA256="cc56837be973d1a102dc6936a0b7235a1d716c0f7cd053bf77e0620577cff986"

SIMAVR_URL="https://github.com/buserror/simavr/archive/refs/tags/v1.7.tar.gz"
SIMAVR_SHA256="e7b3d5f0946e84fbe76a37519d0f146d162bbf88641ee91883b3970b02c77093"

die()
{
	echo "$*" >&2
	exit 1
}

show_help()
{
	echo "Usage: avr_gcc_rust_toolchain.sh <OPTIONS> [PREFIX]"
	echo
	echo "Options:"
	echo " -h|--help                     Print help."
	echo " -k|--keep-tmp                 Keep temporary build files."
	echo
	echo
	echo "Install toolchain to $HOME/usr/avr-gcc"
	echo "  ./build_avr_gcc_toolchain.sh"
	echo
	echo "Install toolchain to another destination"
	echo "  ./build_avr_gcc_toolchain.sh /home/user/directory"
}

parse_args()
{
	# Defaults:
	PREFIX="$HOME/usr/avr-gcc"
	KEEP_TMP=0

	# Parse command line options
	while [ $# -ge 1 ]; do
		[ "$(printf '%s' "$1" | cut -c1)" != "-" ] && break

		case "$1" in
		-h|--help)
			show_help
			exit 0
			;;
		-k|--keep-tmp)
			KEEP_TMP=1
			;;
		*)
			echo "Unknown option: $1"
			exit 1
			;;
		esac
		shift
	done

	if [ $# -ge 1 -a -n "$1" ]; then
		# User defined PREFIX
		PREFIX="$1"
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
	checkprog wget
	checkprog gcc
	checkprog make
	checkprog cmake
	checkprog nproc
	checkprog tar
	checkprog xz
	checkprog gunzip
	checkprog bunzip2
	checkprog schedtool
	checkprog sha256sum
}

check_shasum()
{
	local file="$1"
	local sum="$2"

	if ! [ "$(sha256sum -b "$file" | cut -f1 -d' ')" = "$sum" ]; then
		die "$file: Checksum check failed"
	fi
}

download()
{
	local url="$1"
	local sum="$2"

	DOWNLOAD_FILE="$(basename "$url")"
	if ! [ -e "$DOWNLOAD_FILE" ]; then
		echo "Downloading $DOWNLOAD_FILE ..."
		wget --quiet "$url" || die "download failed"
	fi
	check_shasum "$DOWNLOAD_FILE" "$sum" || die "checksum failed"
}

download_and_extract()
{
	local url="$1"
	local sum="$2"

	download "$url" "$sum" || die "download failed"
	case "$DOWNLOAD_FILE" in
		*.tar.xz)
			local extension=".tar.xz"
			;;
		*.tar.bz2)
			local extension=".tar.bz2"
			;;
		*.tar.gz)
			local extension=".tar.gz"
			;;
		*)
			die "Unknown archive extension: $DOWNLOAD_FILE"
			;;
	esac
	EXTRACT_DIR="$(basename "$DOWNLOAD_FILE" $extension)"
	echo "Extracting $DOWNLOAD_FILE ..."
	rm -rf "$EXTRACT_DIR"
	tar xf "$DOWNLOAD_FILE" || die "Failed to extract"
	[ -d "$EXTRACT_DIR" ] || die "Extracted directory not present"
}

remove_build_tmp()
{
	local builddir="$1"
	local logfile="$2"

	cd "$PREFIX/src" || die "cd failed"
	if [ $KEEP_TMP -eq 0 ]; then
		echo "Cleanup..."
		if [ -d "$builddir" ]; then
			rm -rf "$builddir" || die "Build cleanup failed"
		fi
		if [ -f "$logfile" ]; then
			rm "$logfile" || die "Log cleanup failed"
		fi
	fi
}

prepare()
{
	# Resolve paths.
	PREFIX="$(realpath -m -s "$PREFIX")"
	echo "PREFIX=$PREFIX"
	[ -n "$PREFIX" ] || die "Failed to resolve install prefix"
	export PATH="$PREFIX/bin:$PATH"
	echo

	# Set priority
	schedtool -D -n19 $$ || die "Failed to reduce process priority"

	# Create the build directories.
	mkdir -p "$PREFIX" "$PREFIX/src" || die "Failed to create PREFIX"

	# Unset environment
	unset CFLAGS
	unset CXXFLAGS
	unset CPPFLAGS
	unset MAKEFLAGS
	unset DESTDIR
}

build_binutils()
{
	if [ -e "$PREFIX/bin/avr-ld" ]; then
		echo "binutils are already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/binutils" || die "mkdir failed"
		cd "$PREFIX/src/binutils" || "cd failed"
		download_and_extract "$BINUTILS_URL" "$BINUTILS_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		mkdir mybuild || die "mkdir failed"
		cd mybuild || die "cd failed"
		local log="$PREFIX/src/binutils/build.log"
		rm -f "$log"
		echo "Building..."
		../configure \
			--prefix="$PREFIX" \
			--target=avr \
			--disable-nls \
			>>"$log" 2>&1 ||\
			die "configure failed"
		make -j "$(nproc)" >>"$log" 2>&1 || die "make failed"
		make install >>"$log" 2>&1 || die "make install failed"
		remove_build_tmp "$PREFIX/src/binutils/$EXTRACT_DIR" "$log"
	) || die
}

build_gcc()
{
	if [ -e "$PREFIX/bin/avr-gcc" ]; then
		echo "gcc is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/gcc" || die "mkdir failed"
		cd "$PREFIX/src/gcc" || "cd failed"
		download_and_extract "$GCC_URL" "$GCC_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		mkdir mybuild || die "mkdir failed"
		cd mybuild || die "cd failed"
		local log="$PREFIX/src/gcc/build.log"
		rm -f "$log"
		echo "Building..."
		../configure \
			--prefix="$PREFIX" \
			--target=avr \
			--enable-languages=c,c++ \
			--disable-nls \
			--disable-libssp \
			--with-dwarf2 \
			>>"$log" 2>&1 ||\
			die "configure failed"
		make -j "$(nproc)" >>"$log" 2>&1 || die "make failed"
		make install >>"$log" 2>&1 || die "make install failed"
		remove_build_tmp "$PREFIX/src/gcc/$EXTRACT_DIR" "$log"
	) || die
}

build_avrlibc()
{
	if [ -e "$PREFIX/avr/include/stdlib.h" ]; then
		echo "avr-libc is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/avrlibc" || die "mkdir failed"
		cd "$PREFIX/src/avrlibc" || "cd failed"
		download_and_extract "$AVRLIBC_URL" "$AVRLIBC_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		local log="$PREFIX/src/avrlibc/build.log"
		rm -f "$log"
		echo "Building..."
		./configure \
			--prefix="$PREFIX" \
			--build="$(./config.guess)" \
			--host=avr \
			>>"$log" 2>&1 ||\
			die "configure failed"
		make -j "$(nproc)" >>"$log" 2>&1 || die "make failed"
		make install >>"$log" 2>&1 || die "make install failed"
		remove_build_tmp "$PREFIX/src/avrlibc/$EXTRACT_DIR" "$log"
	) || die
}

build_avrdude()
{
	if [ -e "$PREFIX/bin/avrdude" ]; then
		echo "avrdude is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/avrdude" || die "mkdir failed"
		cd "$PREFIX/src/avrdude" || "cd failed"
		download_and_extract "$AVRDUDE_URL" "$AVRDUDE_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		local log="$PREFIX/src/avrdude/build.log"
		rm -f "$log"
		echo "Building..."
		./build.sh \
			-f "-DCMAKE_INSTALL_PREFIX=$PREFIX" \
			-j "$(nproc)" \
			>>"$log" 2>&1 ||\
			die "configure failed"
		cmake --build build_linux --target install \
			>>"$log" 2>&1 ||\
			die "make install failed"
		remove_build_tmp "$PREFIX/src/avrdude/$EXTRACT_DIR" "$log"
	) || die
}

build_gdb()
{
	if [ -e "$PREFIX/bin/avr-gdb" ]; then
		echo "avr-gdb is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/gdb" || die "mkdir failed"
		cd "$PREFIX/src/gdb" || "cd failed"
		download_and_extract "$GDB_URL" "$GDB_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		mkdir mybuild || die "mkdir failed"
		cd mybuild || die "cd failed"
		local log="$PREFIX/src/gdb/build.log"
		rm -f "$log"
		echo "Building..."
		../configure \
			--prefix="$PREFIX" \
			--target=avr \
			>>"$log" 2>&1 ||\
			die "configure failed"
		make -j "$(nproc)" >>"$log" 2>&1 || die "make failed"
		make install >>"$log" 2>&1 || die "make install failed"
		remove_build_tmp "$PREFIX/src/gdb/$EXTRACT_DIR" "$log"
	) || die
}

build_avra()
{
	true #TODO
}

build_simavr()
{
	true #TODO
}

parse_args "$@"
check_build_environment
prepare
build_binutils
build_gcc
build_avrlibc
build_avrdude
build_gdb
build_avra
build_simavr

echo
echo
echo
echo "Successfully built and installed all tools to: $PREFIX"
echo
