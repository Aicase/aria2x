"""
Aria2X - 一键构建
1. PyInstaller 打包主程序 → Aria2X.exe (项目根目录)
2. 把 Aria2X.exe + icon.ico 嵌入安装程序 → Aria2X_Setup.exe (项目根目录)
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).parent.resolve()


def step1_build_app():
    """打包主程序"""
    print("[1/2] 打包主程序 Aria2X.exe ...")
    subprocess.run([sys.executable, str(BASE / "build.py")], check=True)
    exe = BASE / "Aria2X.exe"
    if not exe.exists():
        print("✗ 主程序打包失败")
        sys.exit(1)
    print(f"  ✓ {exe} ({exe.stat().st_size/1024/1024:.1f} MB)\n")


def step2_build_setup():
    """打包安装程序（嵌入主程序）"""
    print("[2/2] 打包安装程序 Aria2X_Setup.exe ...")

    icon = BASE / "assets" / "icon.ico"
    app_exe = BASE / "Aria2X.exe"
    sep = ";"

    args = [
        sys.executable, "-m", "PyInstaller",
        str(BASE / "setup.py"),
        "--name=Aria2X_Setup",
        "--onefile",
        "--windowed",
        "--clean", "--noconfirm",
        f"--distpath={BASE}",
        f"--workpath={BASE / 'build' / 'setup_work'}",
        f"--specpath={BASE / 'build'}",
        f"--add-data={app_exe}{sep}.",           # 嵌入主程序
        f"--add-data={icon}{sep}assets",          # 嵌入图标
        "--hidden-import=winreg",
        "--hidden-import=pythoncom",
        "--hidden-import=win32com.client",
    ]

    subprocess.run(args, check=True)

    # 清理
    shutil.rmtree(BASE / "build" / "setup_work", ignore_errors=True)

    setup_exe = BASE / "Aria2X_Setup.exe"
    if setup_exe.exists():
        sz = setup_exe.stat().st_size / 1024 / 1024
        print(f"  ✓ {setup_exe} ({sz:.1f} MB)\n")
    else:
        print("✗ 安装程序打包失败")
        sys.exit(1)


def summary():
    """输出结果"""
    app = BASE / "Aria2X.exe"
    setup = BASE / "Aria2X_Setup.exe"

    print("=" * 50)
    print("  构建完成")
    print("=" * 50)
    if app.exists():
        print(f"  主程序:   Aria2X.exe ({app.stat().st_size/1024/1024:.1f} MB)")
    if setup.exists():
        print(f"  安装程序: Aria2X_Setup.exe ({setup.stat().st_size/1024/1024:.1f} MB)")
    print()


if __name__ == "__main__":
    # 清理旧产物
    for p in [BASE / "Aria2X.exe", BASE / "Aria2X_Setup.exe"]:
        if p.exists():
            p.unlink()
    shutil.rmtree(BASE / "build", ignore_errors=True)

    step1_build_app()
    step2_build_setup()
    summary()
