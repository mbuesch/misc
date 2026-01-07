# List packages

adb shell pm list packages

adb shell pm list packages --show-versioncode

## List disabled packages

adb shell pm list packages -d

# Uninstall package

adb uninstall --user 0 $NAME

