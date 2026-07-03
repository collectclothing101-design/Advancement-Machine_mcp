#!/usr/bin/env python3
import subprocess, sys, os, platform

REQUIRED = ["requests", "colorama"]

def check_python():
    if sys.version_info < (3, 9):
        print("[!] requires Python >= 3.9")
        sys.exit(1)

def install_deps(venv: bool = False):
    if venv:
        if not os.path.exists(".venv"):
            subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
        pip = os.path.join(".venv", "bin", "pip") if platform.system() != "Windows" else os.path.join(".venv", "Scripts", "pip.exe")
    else:
        pip = sys.executable + " -m pip"

    for pkg in REQUIRED:
        ret = subprocess.run(f"{pip} install {pkg}", shell=True)
        if ret.returncode != 0:
            print(f"[!] Failed to install {pkg}")

if __name__ == "__main__":
    check_python()
    use_venv = "--venv" in sys.argv
    install_deps(use_venv)
    print("[+] 's framework ready. Call base_command.py from your entry point.")