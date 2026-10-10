[app]
title = Tic Tac Toe vs a Cheating Phone
package.name = tictactoecheatingphone
package.domain = org.hostiletictactoe
source.dir = .
source.include_exts = py
source.exclude_patterns = test_*.py, smoke_*.py
version = 1.4.1
requirements = python3,kivy==2.3.0,plyer,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = VIBRATE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
# Pinned so the build is reproducible: newer python-for-android builds Python 3.14,
# which Kivy 2.3.0 can't compile against.
p4a.branch = v2024.01.21
android.ndk = 25b

[buildozer]
log_level = 2
warn_on_root = 1
