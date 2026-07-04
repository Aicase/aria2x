"""
Aria2X - Motrix Next 集成模块
检测已安装的 Motrix Next，优先使用其 aria2-next 引擎。
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


MOTRIX_VERSION = "3.9.6"
MOTRIX_URL = f"https://github.com/AnInsomniacy/motrix-next/releases/download/v{MOTRIX_VERSION}/MotrixNext_{MOTRIX_VERSION}_x64-setup.exe"
EXT_CHROME = "https://chromewebstore.google.com/detail/motrix-next/ofeajdebdjajhkmcmamagokecnbephhl"
EXT_FIREFOX = "https://addons.mozilla.org/firefox/addon/motrix-next-extension/"


class MotrixIntegration:
    """Motrix Next 检测与集成"""

    def __init__(self):
        self._refresh()

    def _refresh(self):
        self._exe = self._find_exe()
        self._engine = self._find_engine()

    @property
    def is_installed(self) -> bool:
        return self._exe is not None

    @property
    def has_engine(self) -> bool:
        return self._engine is not None

    @property
    def exe_path(self) -> str:
        return self._exe or ""

    @property
    def engine_path(self) -> str:
        return self._engine or ""

    @property
    def version(self) -> str:
        return MOTRIX_VERSION

    @property
    def download_url(self) -> str:
        return MOTRIX_URL

    @property
    def chrome_ext_url(self) -> str:
        return EXT_CHROME

    @property
    def firefox_ext_url(self) -> str:
        return EXT_FIREFOX

    def download_installer(self) -> bool:
        """应用内下载 Motrix Next 安装程序到临时目录并打开"""
        import tempfile
        import urllib.request
        dest = Path(tempfile.gettempdir()) / f"MotrixNext_{MOTRIX_VERSION}_Setup.exe"
        try:
            urllib.request.urlretrieve(MOTRIX_URL, str(dest))
            if dest.exists() and dest.stat().st_size > 1_000_000:
                subprocess.Popen([str(dest)], shell=True)
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _find_exe():
        """查找 Motrix Next 主程序"""
        candidates = []
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "motrix-next" / "Motrix Next.exe")
        candidates.extend([
            Path("C:/Program Files/Motrix Next/Motrix Next.exe"),
            Path("C:/Program Files (x86)/Motrix Next/Motrix Next.exe"),
        ])
        for c in candidates:
            if c.exists():
                return str(c)
        found = shutil.which("Motrix Next")
        return found

    @staticmethod
    def _find_engine():
        """查找 Motrix Next 内置的 aria2-next 引擎"""
        local = os.environ.get("LOCALAPPDATA", "")
        search_dirs = []
        if local:
            base = Path(local) / "Programs" / "motrix-next"
            if base.exists():
                search_dirs.append(base)
        for root in ["C:/Program Files/Motrix Next", "C:/Program Files (x86)/Motrix Next"]:
            b = Path(root)
            if b.exists():
                search_dirs.append(b)

        for d in search_dirs:
            for p in d.rglob("aria2*.exe"):
                try:
                    if p.stat().st_size > 1_000_000:
                        return str(p)
                except:
                    pass
        return None

    def launch(self) -> bool:
        """启动 Motrix Next"""
        if not self._exe:
            return False
        try:
            subprocess.Popen(
                [self._exe],
                cwd=str(Path(self._exe).parent),
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
            )
            return True
        except:
            return False

    def open_download_page(self):
        import webbrowser
        webbrowser.open(MOTRIX_URL)

    def open_ext_page(self, browser="chrome"):
        import webbrowser
        webbrowser.open(EXT_CHROME if browser == "chrome" else EXT_FIREFOX)
