"""Copy app setup into a disposable checkout; callers supply an isolated HOME."""

from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parents[3]


def copy_app_setup(checkout):
    for directory in ("lib", "apps", "scripts/setup"):
        shutil.copytree(REPO / directory, checkout / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
