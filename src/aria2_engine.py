"""
Aria2X - aria2c 引擎管理器
内嵌 aria2c.exe，通过 RPC 管理 BT/Magnet/ED2K 下载。
"""

import os
import sys
import json
import time
import socket
import shutil
import subprocess
import urllib.request
import threading
from pathlib import Path


def get_aria2_path():
    """查找 aria2c.exe（优先 Motrix Next 的 aria2-next 引擎）"""
    # 1. Motrix Next 内置 aria2-next（修复版 fork，最佳）
    try:
        from src.motrix import MotrixIntegration
        motrix = MotrixIntegration()
        if motrix.has_engine:
            return motrix.engine_path
    except:
        pass

    # 2. 打包后 _MEIPASS/assets
    if getattr(sys, 'frozen', False):
        p = Path(sys._MEIPASS) / "assets" / "aria2c.exe"
        if p.exists(): return str(p)
    # 3. 开发模式 src/../assets
    p = Path(__file__).resolve().parent.parent / "assets" / "aria2c.exe"
    if p.exists(): return str(p)
    # 3. PATH
    found = shutil.which("aria2c")
    if found: return found
    return None


def is_aria2_available():
    return get_aria2_path() is not None


class Aria2Engine:
    """aria2c 进程 + RPC 客户端"""

    RPC_PORT = 6800
    RPC_SECRET = "aria2x"

    def __init__(self):
        self._process = None
        self._running = False
        self._rpc_url = f"http://127.0.0.1:{self.RPC_PORT}/jsonrpc"
        self._lock = threading.Lock()
        self.seed_time = 0       # 做种时间（分钟），0=不做种
        self.seed_ratio = 1.0    # 做种比率，达到后停止

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def start(self, seed_time=0, seed_ratio=1.0):
        if self.is_running: return True
        self.seed_time = seed_time
        self.seed_ratio = seed_ratio
        exe = get_aria2_path()
        if not exe: return False

        data_dir = Path.home() / ".aria2x_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        dl_dir = Path.home() / "Downloads" / "Aria2X"
        dl_dir.mkdir(parents=True, exist_ok=True)
        session = data_dir / "aria2.session"
        if not session.exists(): session.write_text("")

        conf_args = [
            exe,
            f"--enable-rpc=true",
            f"--rpc-listen-port={self.RPC_PORT}",
            "--rpc-allow-origin-all=true",
            "--rpc-listen-all=false",
            f"--dir={dl_dir}",
            "--continue=true",
            "--max-concurrent-downloads=5",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=10M",
            "--disk-cache=32M",
            "--file-allocation=trunc",
            "--enable-dht=true",
            "--bt-enable-lpd=true",
            "--enable-peer-exchange=true",
            "--bt-max-peers=100",
            f"--seed-time={self.seed_time}",
            f"--seed-ratio={self.seed_ratio}",
            "--bt-tracker=udp://tracker.opentrackr.org:1337/announce,udp://open.demonii.com:1337/announce,udp://tracker.openbittorrent.com:6969/announce",
            f"--save-session={session}",
            "--save-session-interval=30",
            f"--input-file={session}",
            "--log-level=warn",
            "--quiet",
        ]

        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(conf_args, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, creationflags=flags)
        except:
            return False

        # 等 RPC 就绪
        for _ in range(20):
            time.sleep(0.5)
            if self._check_rpc(): return True
        return False

    def stop(self):
        if not self.is_running: return
        try:
            self._rpc_call("aria2.shutdown")
        except: pass
        try:
            self._process.wait(timeout=5)
        except:
            self._process.terminate()
            try: self._process.wait(timeout=3)
            except: self._process.kill()
        self._process = None

    def _check_rpc(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            r = sock.connect_ex(("127.0.0.1", self.RPC_PORT))
            sock.close()
            return r == 0
        except: return False

    def _rpc_call(self, method, params=None):
        if params is None: params = []
        params = [f"token:{self.RPC_SECRET}"] + params
        payload = {"jsonrpc": "2.0", "id": "aria2x", "method": method, "params": params}
        req = urllib.request.Request(self._rpc_url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if "error" in data: raise Exception(data["error"].get("message", ""))
            return data.get("result")

    # ---- Public API ----

    def add_uri(self, url, options=None):
        opts = options or {}
        return self._rpc_call("aria2.addUri", [[url], opts])

    def add_torrent(self, torrent_path):
        import base64
        with open(torrent_path, "rb") as f:
            torrent_b64 = base64.b64encode(f.read()).decode()
        return self._rpc_call("aria2.addTorrent", [torrent_b64, [], {}])

    def add_metalink(self, metalink_b64):
        return self._rpc_call("aria2.addMetalink", [metalink_b64])

    def pause(self, gid):
        return self._rpc_call("aria2.pause", [gid])

    def unpause(self, gid):
        return self._rpc_call("aria2.unpause", [gid])

    def remove(self, gid):
        return self._rpc_call("aria2.remove", [gid])

    def get_status(self, gid):
        return self._rpc_call("aria2.tellStatus", [gid])

    def get_active(self):
        return self._rpc_call("aria2.tellActive")

    def get_waiting(self, offset=0, num=50):
        return self._rpc_call("aria2.tellWaiting", [offset, num])

    def get_stopped(self, offset=0, num=50):
        return self._rpc_call("aria2.tellStopped", [offset, num])

    def get_stats(self):
        try:
            return self._rpc_call("aria2.getGlobalStat")
        except: return None

    def get_all_tasks(self):
        tasks = []
        for method, args in [("aria2.tellActive", []),
                             ("aria2.tellWaiting", [0, 50]),
                             ("aria2.tellStopped", [0, 50])]:
            try:
                result = self._rpc_call(method, args)
                if result:
                    for t in result:
                        tasks.append({
                            "id": t.get("gid", ""),
                            "url": t.get("files", [{}])[0].get("uris", [{}])[0].get("uri", "") if t.get("files") else "",
                            "filename": (t.get("bittorrent", {}).get("info", {}).get("name") or
                                        (t.get("files", [{}])[0].get("path", "").split("/")[-1] if t.get("files") else t.get("gid",""))),
                            "total_size": int(t.get("totalLength", 0)),
                            "downloaded": int(t.get("completedLength", 0)),
                            "speed": int(t.get("downloadSpeed", 0)),
                            "status": t.get("status", "unknown"),
                            "progress": int(t.get("completedLength", 0)) / max(int(t.get("totalLength", 1)), 1),
                            "progress_pct": int(int(t.get("completedLength", 0)) / max(int(t.get("totalLength", 1)), 1) * 100),
                            "engine": "aria2",
                        })
            except: pass
        return tasks
