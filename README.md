# Tic Tac Toe vs a Cheating Phone - Android edition

Files
- `main.py`        Kivy touch UI (board, menus, dialogs, sound, vibration)
- `controller.py`  The game: turns, every cheat, achievements, snooze timer
- `game_core.py`   Rules, minimax AI, taunts, stats, synthesized sounds (from your desktop file)
- `buildozer.spec` Android build settings
- `test_controller.py`  Optional: simulates hundreds of games with no Kivy needed

## Try it on your PC first (mouse = finger; hold the button down for a long press)
    pip install kivy plyer
    python main.py

## Build the APK
Buildozer only runs on Linux. On Windows use WSL2:
1. PowerShell (admin):  `wsl --install -d Ubuntu`  then reboot and open Ubuntu.
2. In Ubuntu:
       sudo apt update
       sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool \
            pkg-config zlib1g-dev libncurses5-dev libffi-dev libssl-dev cmake
       pip3 install --user --upgrade buildozer cython==0.29.36
3. Copy this folder into Ubuntu's home (`cp -r /mnt/c/path/to/folder ~/tictactoe`), then:
       cd ~/tictactoe
       buildozer android debug
   The first build downloads the Android SDK/NDK and takes 20-40 minutes.
4. The APK appears in `bin/`. Copy it to your phone (`explorer.exe bin` opens it in Windows),
   open it, and allow "install unknown apps" when asked.
   Or with USB debugging on: `buildozer android deploy run`.

## Controls
| Desktop                  | Android                                              |
|--------------------------|------------------------------------------------------|
| Click a square           | Tap                                                  |
| Ctrl+Alt+click           | Hold a square about half a second (phone buzzes)     |
| File menu / Ctrl+N       | Menu button / New Game button                        |
| Play as / Difficulty / Cheating pills | Options button (big selectors)          |
| Stats window             | Menu > Stats & Achievements (scrolls)                |
| Outside-the-box O window | O appears in the margin around the board, screen shakes + buzz |
| Window minimised pauses snooze | App in background or any dialog open pauses snooze |
| Poke the monitor icon x10 | Same, tap it                                        |
| Close window             | Menu > Exit, or Back twice                           |

## Tweaks
- Lines look too thick/thin: change `GLOW_SCALE` at the top of `main.py`.
- Long-press time: `LONG_PRESS` in `main.py`.
- Stats are stored in the app's private folder (cleared if you uninstall).

## Build the APK with GitHub (no Linux needed)
1. Put these files in a GitHub repository (the `.github/workflows/build-apk.yml` file must keep that exact path).
2. Open the repo's **Actions** tab > **Build Android APK** > **Run workflow** (it also runs on every push).
3. When it finishes (about 30-45 min the first time, much faster after), open the run and download
   the **cheating-phone-apk** artifact at the bottom. Unzip it; the `.apk` inside is the app.
4. If the build fails, download the **build-log** artifact from the same page.
