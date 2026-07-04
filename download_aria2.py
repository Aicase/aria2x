"""
Aria2X - aria2c 下载脚本
运行此脚本自动下载 aria2c.exe 到 assets/ 目录。
"""
import urllib.request
import zipfile
import io
import os
from pathlib import Path

ARIA2_URL = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
ASSETS = Path(__file__).parent / "assets"


def main():
    ASSETS.mkdir(exist_ok=True)
    dest = ASSETS / "aria2c.exe"

    if dest.exists():
        print(f"aria2c.exe already exists ({dest.stat().st_size / 1024:.0f} KB)")
        return

    print(f"Downloading aria2 from {ARIA2_URL}...")
    data = urllib.request.urlopen(ARIA2_URL, timeout=120).read()
    print(f"Downloaded {len(data) / 1024:.0f} KB, extracting...")

    zf = zipfile.ZipFile(io.BytesIO(data))
    for name in zf.namelist():
        if name.endswith("aria2c.exe"):
            with open(dest, "wb") as f:
                f.write(zf.read(name))
            print(f"✓ {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
            return

    print("✗ aria2c.exe not found in archive")


if __name__ == "__main__":
    main()
