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
        """查找 Motrix Next 主程序 — 注册表优先"""
        # 1. Windows 注册表（最可靠）
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                           r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                    try:
                        key = winreg.OpenKey(root, sub)
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                name = winreg.EnumKey(key, i)
                                app_key = winreg.OpenKey(key, name)
                                try:
                                    display, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                    if "motrix" in display.lower():
                                        loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                        if loc:
                                            candidates = [
                                                Path(loc) / "Motrix Next.exe",
                                                Path(loc) / "MotrixNext.exe",
                                            ]
                                            for c in candidates:
                                                if c.exists():
                                                    return str(c)
                                            # 搜索目录下所有 exe
                                            for f in Path(loc).rglob("Motrix*.exe"):
                                                return str(f)
                                except: pass
                                finally: winreg.CloseKey(app_key)
                            except: pass
                    except: pass
        except: pass

        # 2. 常见安装路径
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = []
        if local:
            candidates.append(Path(local) / "Programs" / "motrix-next" / "Motrix Next.exe")
        candidates.extend([
            Path("C:/Program Files/Motrix Next/Motrix Next.exe"),
            Path("C:/Program Files (x86)/Motrix Next/Motrix Next.exe"),
            Path("D:/Program Files/Motrix Next/Motrix Next.exe"),
            Path("D:/Downloads/MotrixNext/Motrix Next.exe"),  # 用户实际路径
        ])
        for c in candidates:
            if c.exists():
                return str(c)

        # 3. PATH 搜索
        return shutil.which("Motrix Next")

    @staticmethod
    def _find_engine():
        """查找 Motrix Next 内置的 aria2-next 引擎"""
        # 从已找到的安装目录搜索
        exe_path = MotrixIntegration._find_exe()
        if exe_path:
            base = Path(exe_path).parent
            for p in base.rglob("aria2*.exe"):
                try:
                    if p.stat().st_size > 500_000:
                        return str(p)
                except: pass

        # 扩展搜索
        for root in ["C:/Program Files/Motrix Next", "C:/Program Files (x86)/Motrix Next",
                     "D:/Program Files/Motrix Next", "D:/Downloads/MotrixNext"]:
            b = Path(root)
            if b.exists():
                for p in b.rglob("aria2*.exe"):
                    try:
                        if p.stat().st_size > 500_000:
                            return str(p)
                    except: pass
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
