#!/bin/sh

basedir="$(dirname "$0")"
[ "$(echo "$basedir" | cut -c1)" = '/' ] || basedir="$PWD/$basedir"


project="timeshift"
builddir="$basedir/build-android"
appbuilddir="$builddir/app"
venvdir="$builddir/venv"
sysrootdir="$builddir/sysroot"
sysrootconfig="$basedir/sysroot.json"
plugindir="$basedir/sysroot-plugins"
sourcedir="$basedir/sources"
qtinstalldir="$HOME/Qt/5.12.2"
target="android-32"

export ANDROID_NDK_PLATFORM=android-21
export ANDROID_NDK_ROOT="$HOME/Android/Sdk/ndk-bundle"
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"


die()
{
	echo "$*" >&2
	exit 1
}

info()
{
	echo "--- $*"
}

mkdir -p "$builddir" || die "Failed to create builddir."

if ! [ -d "$venvdir" ]; then
	virtualenv "$venvdir" || die "Failed to create virtualenv."
fi

(
	info "Setting up virtualenv"
	. "$venvdir/bin/activate" || die "Failed to activate virtualenv."
	pip3 install pyqtdeploy || die "Failed to install pyqtdeploy."
	pip3 install PyQt5 || die "Failed to install PyQt5."

	info "Building sysroot"
	if ! [ -d "$sysrootdir" ]; then
		mkdir -p "$sysrootdir" || die "Failed to create sysrootdir."
		pyqtdeploy-sysroot \
			--target "$target" \
			--sysroot "$sysrootdir" \
			--source-dir "$sourcedir" \
			--source-dir "$qtinstalldir" \
			--plugin-dir "$plugindir" \
			"$sysrootconfig" ||\
			die "Failed to build sysroot."
	fi

	info "App pyqtdeploy"
	rm -rf "$appbuilddir"
	pyqtdeploy-build \
		--target "$target" \
		--sysroot "$sysrootdir" \
		--build-dir "$appbuilddir" \
		"$project.pdy" ||\
		die "Failed to pyqtdeploy-build."
	cd "$appbuilddir" || die "Failed to enter appbuilddir."

	info "Building app"
	"$sysrootdir/host/bin/qmake" || die "qmake failed."
	make || die "make failed."
	make INSTALL_ROOT="$project" install || die "make install failed."
	"$sysrootdir/host/bin/androiddeployqt" \
		--gradle \
		--input "android-lib$project.so-deployment-settings.json" \
		--output "$project" ||\
		die "androiddeployqt failed."
	cp "$appbuilddir/$project/build/outputs/apk/debug/$project-debug.apk" \
		"$basedir/$project.apk" ||\
		die "Failed to copy apk."

	echo "Android package built:  $project.apk"
) || die
