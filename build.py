"""
Aria2X - 打包脚本
输出: Aria2X.exe (含 aria2c.exe)
"""
import sys, shutil, subprocess
from pathlib import Path
BASE = Path(__file__).parent.resolve()

def build():
    icon = BASE / "assets" / "icon.ico"
    icon_arg = [f"--icon={icon}"] if icon.exists() else []
    sep = ";"
    data = [f"--add-data={BASE/'src'/'web'/'index.html'}{sep}web"]
    aria2 = BASE / "assets" / "aria2c.exe"
    if aria2.exists():
        data.append(f"--add-data={aria2}{sep}assets")
        print(f"  aria2c.exe: ✓ ({aria2.stat().st_size/1024/1024:.1f} MB)")
    else:
        print("  aria2c.exe: ✗ (BT/Magnet 不可用)")

    tmp = BASE / "build" / "dist"
    args = [
        sys.executable, "-m", "PyInstaller", "src/main.py",
        "--name=Aria2X", "--onefile", "--windowed", "--clean", "--noconfirm",
        f"--distpath={tmp}", f"--workpath={BASE/'build'/'work'}", f"--specpath={BASE/'build'}",
        "--hidden-import=flask", "--hidden-import=werkzeug", "--hidden-import=webview",
        "--hidden-import=clr_loader", "--hidden-import=pythonnet",
        "--hidden-import=src.downloader", "--hidden-import=src.link_parser",
        "--hidden-import=src.server", "--hidden-import=src.aria2_engine",
        "--hidden-import=src.motrix", "--hidden-import=src.engines",
        "--hidden-import=src.miaochuan", "--hidden-import=src.torrent_creator",
        "--exclude-module=tkinter", "--exclude-module=matplotlib", "--exclude-module=numpy",
        "--exclude-module=pandas", "--optimize=2",
    ] + icon_arg + data

    print("=" * 50); print("  Aria2X Build"); print("=" * 50)
    subprocess.run(args, check=True)
    dest = BASE / "Aria2X.exe"
    src_exe = tmp / "Aria2X.exe"
    if src_exe.exists():
        if dest.exists(): dest.unlink()
        shutil.move(str(src_exe), str(dest))
        print(f"\n  ✓ {dest} ({dest.stat().st_size/1024/1024:.1f} MB)")
    else:
        print("\n  ✗ FAILED"); sys.exit(1)

if __name__ == "__main__":
    build()
