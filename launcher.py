"""Entry point for the packaged executable (PyInstaller). Same as `python -m worktrack`."""

from worktrack.app import main

if __name__ == "__main__":
    raise SystemExit(main())
