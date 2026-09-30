"""Entry script for PyInstaller and for `python run_kmuted.py`."""

from kmuted.app import main

if __name__ == "__main__":
    raise SystemExit(main())
