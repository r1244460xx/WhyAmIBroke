import os
import sys
import streamlit.web.cli as stcli


def resolve_path(path):
    """Resolve file path whether running in normal Python or frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        basedir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    else:
        basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(basedir, path))


def main():
    # When running as a packaged binary, switch working dir to where the executable resides
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
        os.makedirs(os.path.join(exe_dir, "bills"), exist_ok=True)
        if exe_dir not in sys.path:
            sys.path.insert(0, exe_dir)

    app_path = resolve_path("app.py")

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        "--browser.serverAddress=localhost",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
