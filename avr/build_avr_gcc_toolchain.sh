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

BINUTILS_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/binutils/binutils-2.45.tar.xz"
BINUTILS_SHA256="c50c0e7f9cb188980e2cc97e4537626b1672441815587f1eab69d2a1bfbef5d2"

GCC_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/gcc/gcc-15.2.0/gcc-15.2.0.tar.xz"
GCC_SHA256="438fd996826b0c82485a29da03a72d71d6e3541a83ec702df4271f6fe025d24e"

AVRLIBC_URL="https://github.com/avrdudes/avr-libc/releases/download/avr-libc-2_2_1-release/avr-libc-2.2.1.tar.bz2"
AVRLIBC_SHA256="006a6306cbbc938c3bdb583ac54f93fe7d7c8cf97f9cde91f91c6fb0273ab465"

AVRDUDE_URL="https://github.com/avrdudes/avrdude/releases/download/v8.1/avrdude-8.1.tar.gz"
AVRDUDE_SHA256="2d3016edd5281ea09627c20b865e605d4f5354fe98f269ce20522a5b910ab399"

GDB_URL="https://ftp-stud.hs-esslingen.de/pub/Mirrors/ftp.gnu.org/gdb/gdb-16.3.tar.xz"
GDB_SHA256="bcfcd095528a987917acf9fff3f1672181694926cc18d609c99d0042c00224c5"

AVRA_URL="https://github.com/Ro5bert/avra/archive/refs/tags/1.4.2.tar.gz"
AVRA_SHA256="cc56837be973d1a102dc6936a0b7235a1d716c0f7cd053bf77e0620577cff986"

SIMAVR_COMMIT="ec341062fa5d550410f14ae32f09f5e87d861b8b"
SIMAVR_URL="https://github.com/buserror/simavr/archive/$SIMAVR_COMMIT.tar.gz"
SIMAVR_SHA256="709be6451f91576015b402ce7fd650eb7b02d701ad8ab387003d642ee6fbb1b8"

DWDEBUG_COMMIT="a51e9cc342d2437052103169d9a5c81c4cf480cf"
DWDEBUG_URL="https://github.com/mbuesch/dwire-debug/archive/$DWDEBUG_COMMIT.tar.gz"
DWDEBUG_SHA256="54d617de19272cae1b86330f56bb04b01b90df9810b26fca4aa6e4576d2c33e6"

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
	echo "Install toolchain to $HOME/usr/avr"
	echo "  ./build_avr_gcc_toolchain.sh"
	echo
	echo "Install toolchain to another destination"
	echo "  ./build_avr_gcc_toolchain.sh /home/user/directory"
}

parse_args()
{
	# Defaults:
	PREFIX="$HOME/usr/avr"
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
	checkprog bunzip2
	checkprog cmake
	checkprog gcc
	checkprog gunzip
	checkprog make
	checkprog nproc
	checkprog schedtool
	checkprog sha256sum
	checkprog tar
	checkprog wget
	checkprog xz
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
	if ! [ -d "$EXTRACT_DIR" ]; then
		# Workaround for github tag tarballs.

		# Remove leading "v".
		EXTRACT_DIR="$(printf '%s' "$EXTRACT_DIR" | sed -e 's/^v\(.*\)/\1/')"

		# Find dir-prefix.
		for d in *-"$EXTRACT_DIR"; do
			if [ -d "$d" ]; then
				EXTRACT_DIR="$d"
			fi
			break
		done
	fi
	[ -d "$EXTRACT_DIR" ] || die "Extracted directory $EXTRACT_DIR not present"
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
	printf '\nbinutils:\n'
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
	printf '\ngcc:\n'
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
	printf '\navr-libc:\n'
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
	printf '\navrdude:\n'
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
	printf '\ngdb:\n'
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
	printf '\navra:\n'
	if [ -e "$PREFIX/bin/avra" ]; then
		echo "avra is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/avra" || die "mkdir failed"
		cd "$PREFIX/src/avra" || "cd failed"
		download_and_extract "$AVRA_URL" "$AVRA_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		local log="$PREFIX/src/avra/build.log"
		rm -f "$log"
		echo "Building..."
		make -j "$(nproc)" PREFIX="$PREFIX" >>"$log" 2>&1 || die "make failed"
		make PREFIX="$PREFIX" install >>"$log" 2>&1 || die "make install failed"
		remove_build_tmp "$PREFIX/src/avra/$EXTRACT_DIR" "$log"
	) || die
}

build_simavr()
{
	printf '\nsimavr:\n'
	if [ -e "$PREFIX/bin/simavr" ]; then
		echo "simavr is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/simavr" || die "mkdir failed"
		cd "$PREFIX/src/simavr" || "cd failed"
		download_and_extract "$SIMAVR_URL" "$SIMAVR_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		local log="$PREFIX/src/simavr/build.log"
		rm -f "$log"
		echo "Building..."
		make -j "$(nproc)" RELEASE=1 PREFIX="$PREFIX" DESTDIR="$PREFIX" \
			>>"$log" 2>&1 ||\
			die "make failed"
		make RELEASE=1 PREFIX="$PREFIX" DESTDIR="$PREFIX" install \
			>>"$log" 2>&1 ||\
			die "make install failed"
		remove_build_tmp "$PREFIX/src/simavr/$EXTRACT_DIR" "$log"
	) || die
}

build_dwdebug()
{
	printf '\ndwdebug:\n'
	if [ -e "$PREFIX/bin/dwdebug" ]; then
		echo "dwdebug is already installed."
		return
	fi

	(
		mkdir -p "$PREFIX/src/dwdebug" || die "mkdir failed"
		cd "$PREFIX/src/dwdebug" || "cd failed"
		download_and_extract "$DWDEBUG_URL" "$DWDEBUG_SHA256" || die "download failed"
		cd "$EXTRACT_DIR" || die "cd failed"
		local log="$PREFIX/src/dwdebug/build.log"
		rm -f "$log"
		echo "Building..."
		make -j1 dwdebug \
			>>"$log" 2>&1 ||\
			die "make failed"
		install -m755 ./dwdebug "$PREFIX/bin/"
			>>"$log" 2>&1 ||\
			die "install failed"
		remove_build_tmp "$PREFIX/src/dwdebug/$EXTRACT_DIR" "$log"
	) || die
}

basedir="$(realpath "$0" | xargs dirname)"
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
build_dwdebug

echo
echo
echo
echo "Successfully built and installed all tools to: $PREFIX"
echo
