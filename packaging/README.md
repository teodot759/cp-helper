# Packaging

Optional. You do not need this to run from source — `./run.sh` is enough.

Both artifacts come from `cpp-helper.spec` (`--onedir`, windowed).

## Linux

```bash
packaging/build-linux.sh            # dist/CppHelper/CppHelper
packaging/build-linux.sh appimage   # + dist/CppHelper-x86_64.AppImage
```

The AppImage step needs `appimagetool` on `PATH`; without it the script
prepares `build/AppDir` and stops. Test the bundle on a machine with **no Qt
installed** — that is the point of bundling.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
```

- `dist\CppHelper\CppHelper.exe` is the portable bundle.
- If Inno Setup 6 is installed, `dist\installer\CppHelper-Setup.exe` is also
  produced: per-user, no admin prompt.

Test on a clean Windows VM **without MSYS2**. Compiler detection should find a
WinLibs/MinGW install through `PATH`, the registry, or `Browse…`.

## Notes

- `--onedir` is deliberate: faster startup and far fewer antivirus false
  positives than `--one-file`.
- Qt modules the app never imports are excluded in the spec. It also drops the
  virtual-keyboard plugin (which would pull all of Qt Quick) and the GTK3
  platform theme (which would pull a second 31 MB copy of ICU).
- Measured on Linux with PySide6 6.12: **~135 MB** unpacked, **43 MB** as a
  `tar.zst`. The floor is `libicudata` (~31 MB, a hard dependency of Qt6Core).
- PySide6 is LGPL; dynamic linking through PyInstaller satisfies the licence.
- Do not ship Flatpak/Snap: the sandbox cannot see the host's compiler.
