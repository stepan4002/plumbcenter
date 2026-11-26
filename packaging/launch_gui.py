"""PyInstaller entry point for PlumbCenter (windowed exe)."""
import sys

from plumbcenter.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
