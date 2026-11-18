"""Entry point: ``python -m cppjudge`` or the ``cpp-helper`` script."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .branding import load_branding, resource_path
from .core.settings import load_settings
from .ui.main_window import CPP_SUFFIXES, MainWindow
from .ui.theme import apply_theme


def _first_source(args: list[str]) -> Path | None:
    for arg in args[1:]:
        if arg.startswith("-"):
            continue
        path = Path(arg).expanduser()
        if path.is_file():
            return path
        if path.suffix.lower() in CPP_SUFFIXES:
            return path if path.exists() else None
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    branding = load_branding()

    app = QApplication(args)
    app.setApplicationName(branding.app_name)
    app.setApplicationDisplayName(branding.app_name)
    app.setOrganizationName(branding.config_dir)

    settings = load_settings()
    apply_theme(app, settings.theme)

    window = MainWindow(settings)
    icon = resource_path("icon.svg")
    if icon.exists():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon)))
        window.setWindowIcon(QIcon(str(icon)))

    window.show()
    path = _first_source(args)
    if path is not None:
        window.open_path(path)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
