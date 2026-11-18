"""PyInstaller entry point.

The package uses relative imports, so ``__main__.py`` cannot be handed to
PyInstaller as a script. This thin wrapper imports the package properly.
"""

from cppjudge.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
