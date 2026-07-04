"""
Aria2X - 多引擎下载管理器
支持: 原生HTTP(Python) / aria2c / curl / IDM / BitComet / Motrix Next
自动检测可用引擎，按优先级选择。
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class EngineInfo:
    """引擎信息"""
    key: str
    name: str
    version: str
    exe_path: str
    installed: bool
    supports: list  # 支持的协议: http, magnet, ed2k, thunder, torrent, json
    priority: int   # 越高越优先


class EngineManager:
    """多引擎管理器 — 自动检测系统上所有可用的下载引擎"""

    def __init__(self):
        self._engines = []
        self._detect_all()

    # ---- 检测 ----

    def _detect_all(self):
        self._engines = []
        self._detect_native_http()
        self._detect_aria2c()
        self._detect_curl()
        self._detect_idm()
        self._detect_bitcomet()
        self._detect_motrix()
        self._engines.sort(key=lambda e: -e.priority)

    def _detect_native_http(self):
        self._engines.append(EngineInfo(
            key="native_http", name="Python 原生引擎", version="1.0",
            exe_path=sys.executable, installed=True,
            supports=["http", "https", "ftp", "json"],
            priority=10,
        ))

    def _detect_aria2c(self):
        exe = self._find_exe("aria2c", ["assets/aria2c.exe"])
        if not exe:
            from src.aria2_engine import get_aria2_path
            exe = get_aria2_path()
        ver = ""
        if exe:
            try:
                r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5)
                ver = r.stdout.splitlines()[0] if r.stdout else ""
            except:
                pass
        self._engines.append(EngineInfo(
            key="aria2c", name="aria2c", version=ver, exe_path=exe or "",
            installed=bool(exe),
            supports=["http", "https", "ftp", "magnet", "torrent", "ed2k"],
            priority=20,
        ))

    def _detect_curl(self):
        exe = shutil.which("curl")
        ver = ""
        if exe:
            try:
                r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5)
                ver = r.stdout.splitlines()[0].split(" ")[1] if r.stdout else ""
            except:
                pass
        self._engines.append(EngineInfo(
            key="curl", name="cURL", version=ver, exe_path=exe or "",
            installed=bool(exe),
            supports=["http", "https", "ftp"],
            priority=15,
        ))

    def _detect_idm(self):
        """Internet Download Manager"""
        candidates = [
            Path("C:/Program Files (x86)/Internet Download Manager/IDMan.exe"),
            Path("C:/Program Files/Internet Download Manager/IDMan.exe"),
        ]
        exe = None
        for c in candidates:
            if c.exists():
                exe = str(c)
                break
        self._engines.append(EngineInfo(
            key="idm", name="Internet Download Manager", version="",
            exe_path=exe or "", installed=bool(exe),
            supports=["http", "https", "ftp"],
            priority=25,
        ))

    def _detect_bitcomet(self):
        """BitComet (彗星)"""
        candidates = [
            Path("C:/Program Files/BitComet/BitComet.exe"),
            Path("C:/Program Files (x86)/BitComet/BitComet.exe"),
        ]
        exe = None
        for c in candidates:
            if c.exists():
                exe = str(c)
                break
        self._engines.append(EngineInfo(
            key="bitcomet", name="BitComet 彗星", version="",
            exe_path=exe or "", installed=bool(exe),
            supports=["http", "https", "magnet", "torrent", "ed2k"],
            priority=18,
        ))

    def _detect_motrix(self):
        from src.motrix import MotrixIntegration
        m = MotrixIntegration()
        self._engines.append(EngineInfo(
            key="motrix", name="Motrix Next", version=m.version if m.is_installed else "",
            exe_path=m.exe_path, installed=m.is_installed,
            supports=["http", "https", "magnet", "torrent", "ed2k", "thunder"],
            priority=22,
        ))

    def _find_exe(self, name, local_paths):
        exe_name = name + (".exe" if sys.platform == "win32" else "")
        for p in local_paths:
            full = Path(__file__).resolve().parent.parent / p
            if full.exists():
                return str(full)
        return shutil.which(name)

    # ---- API ----

    def get_all(self) -> list:
        return self._engines

    def get_installed(self) -> list:
        return [e for e in self._engines if e.installed]

    def get_by_key(self, key: str) -> Optional[EngineInfo]:
        for e in self._engines:
            if e.key == key:
                return e
        return None

    def get_best_for(self, protocol: str) -> Optional[EngineInfo]:
        """获取最适合某协议的最高优先级引擎"""
        for e in sorted(self._engines, key=lambda x: -x.priority):
            if e.installed and protocol in e.supports:
                return e
        return None

    def download_with(self, key: str, url: str, save_dir: str, filename: str = "") -> bool:
        """使用指定引擎下载"""
        engine = self.get_by_key(key)
        if not engine or not engine.installed:
            return False

        if key == "idm":
            # IDMan.exe /d URL /p DIR /f FILENAME
            args = [engine.exe_path, "/d", url, "/p", save_dir]
            if filename:
                args += ["/f", filename]
            args.append("/n")
            subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS if sys.platform=="win32" else 0)
            return True

        if key == "bitcomet":
            subprocess.Popen([engine.exe_path, url],
                           creationflags=subprocess.DETACHED_PROCESS if sys.platform=="win32" else 0)
            return True

        if key == "motrix":
            from src.motrix import MotrixIntegration
            m = MotrixIntegration()
            return m.launch()

        if key == "curl":
            import threading
            def curl_dl():
                args = [engine.exe_path, "-L", "-o",
                       str(Path(save_dir) / (filename or "download")), url]
                subprocess.run(args, capture_output=True)
            threading.Thread(target=curl_dl, daemon=True).start()
            return True

        return False

    def to_api_response(self) -> dict:
        """API 可序列化的引擎列表"""
        return {
            "engines": [{
                "key": e.key, "name": e.name, "version": e.version,
                "installed": e.installed, "supports": e.supports, "priority": e.priority,
            } for e in self._engines],
            "count": len(self._engines),
            "installed_count": len([e for e in self._engines if e.installed]),
        }
