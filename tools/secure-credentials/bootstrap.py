#!/usr/bin/env python3
"""Create a private, locked dependency environment for this utility."""
from __future__ import annotations

import argparse
import os
import shutil
# Only a just-created private virtual-environment interpreter receives fixed arguments.
import subprocess  # nosec B404
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(path, 0o700)


def main(argv=None) -> int:
    default = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "runtime" / "secure-credentials-venv"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=default)
    args = parser.parse_args(argv)
    private_directory(args.venv.parent)
    if not (args.venv / "bin" / "python").is_file():
        venv.EnvBuilder(with_pip=True, clear=False).create(args.venv)
    python = args.venv / "bin" / "python"
    # The executable is the just-created private virtual-environment Python.
    subprocess.run(  # nosec B603
        [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(ROOT / "requirements.lock")],
        check=True,
    )
    # The executable is the just-created private virtual-environment Python.
    purelib = subprocess.run(  # nosec B603
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    destination = Path(purelib) / "secure_credentials"
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(ROOT / "secure_credentials", destination)
    executable = args.venv / "bin" / "secure-credentials"
    executable.write_text(
        f"#!{python}\nfrom secure_credentials.cli import main\nraise SystemExit(main())\n"
    )
    executable.chmod(0o700)
    print(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
