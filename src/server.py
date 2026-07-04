"""
Aria2X - Flask 后端服务器
统一管理纯 Python 引擎 (HTTP) + aria2c 引擎 (BT/Magnet/ED2K)
"""

import os
import sys
import json
import time
import socket
import threading
import subprocess
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

from src.downloader import DownloadEngine, TaskStatus, load_history, save_history, SETTINGS_FILE
from src.link_parser import parse_link, LinkType
from src.aria2_engine import Aria2Engine, is_aria2_available, get_aria2_path
from src.motrix import MotrixIntegration
from src.engines import EngineManager
from src.miaochuan import MiaochuanPackage
from src.torrent_creator import create_torrent, Seeder


def get_web_dir():
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        for c in [base / "web", base / "src" / "web", base]:
            if (c / "index.html").exists(): return c
        for p in base.rglob("index.html"): return p.parent
        return base / "web"
    return Path(__file__).resolve().parent / "web"


def create_app():
    app = Flask(__name__, static_folder=None)
    engine = DownloadEngine(max_concurrent=5)
    engine.start()
    aria2 = Aria2Engine()

    web_dir = get_web_dir()

    def get_settings():
        defaults = {
            "save_dir": str(Path.home() / "Downloads"), "threads": 4,
            "max_concurrent": 5, "theme": "slate", "speed_limit": 0,
            "modes": {"http": True, "magnet": True, "ed2k": True, "thunder": True},
            "proxy": {"enabled": False, "host": "127.0.0.1", "port": 7890, "type": "http"},
            "clipboard_watch": True, "notify_complete": True, "minimize_to_tray": True,
            "seed_time": 0, "seed_ratio": 1.0,
        }
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                return {**defaults, **saved}
            except Exception:
                # 文件损坏，删除并返回默认值
                try:
                    SETTINGS_FILE.unlink()
                except:
                    pass
        return defaults

    def save_settings(data):
        if not isinstance(data, dict):
            data = {}
        cur = get_settings()
        cur.update(data)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cur, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ---- Page ----
    @app.route("/")
    def index():
        return send_from_directory(str(web_dir), "index.html")

    # ---- Parse ----
    @app.route("/api/parse", methods=["POST"])
    def api_parse():
        text = request.get_json().get("text", "").strip()
        if not text: return jsonify({"error": "空"}), 400
        results = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                p = parse_link(line)
                results.append({
                    "raw": p.raw, "type": p.type.value,
                    "url": p.url or p.raw, "filename": p.filename,
                    "size_hint": p.size_hint, "is_valid": p.is_valid, "error": p.error,
                })
        return jsonify({"links": results, "count": len(results)})

    # ---- Download ----
    @app.route("/api/download", methods=["POST"])
    def api_download():
        data = request.get_json()
        url = data.get("url", "").strip()
        save_dir = data.get("save_dir", str(Path.home() / "Downloads"))
        filename = data.get("filename", "")
        threads = data.get("threads", 4)
        category = data.get("category", "")
        settings = get_settings()

        if not url: return jsonify({"error": "链接为空"}), 400

        # 支持自定义 headers
        headers = data.get("headers", {})
        if headers:
            # 将带自定义 header 的请求转入 aria2c
            if not is_aria2_available():
                return jsonify({"error": "自定义 Header 下载需要 aria2c.exe"}), 400
            if not aria2.is_running:
                aria2.start()
            opts = {"dir": save_dir, "header": [f"{k}: {v}" for k, v in headers.items()]}
            if filename: opts["out"] = filename
            try:
                gid = aria2.add_uri(url, opts)
                return jsonify({"task_id": gid, "engine": "aria2", "status": "added"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        parsed = parse_link(url)

        # BT/Magnet/ED2K/Metalink/CURL → aria2c 引擎
        if parsed.type in (LinkType.MAGNET, LinkType.MAGNET_HASH, LinkType.ED2K, LinkType.METALINK, LinkType.CURL):
            if not is_aria2_available():
                return jsonify({"error": "BT/Magnet/ED2K 需要 aria2c.exe，请放到 assets/ 目录"}), 400
            if not aria2.is_running:
                aria2.start(get_settings().get("seed_time", 0),
                           get_settings().get("seed_ratio", 1.0))
            opts = {"dir": save_dir}
            if filename: opts["out"] = filename
            try:
                gid = aria2.add_uri(parsed.url or url, opts)
                return jsonify({"task_id": gid, "engine": "aria2", "status": "added"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # Thunder → 解码后走 HTTP
        dl_url = parsed.url or url

        # HTTP → 纯 Python 引擎
        tid = engine.add_task(url=dl_url, save_dir=save_dir, filename=filename or parsed.filename,
                              threads=threads, category=category)
        return jsonify({"task_id": tid, "engine": "python", "status": "added"})

    # ---- Tasks ----
    @app.route("/api/tasks", methods=["GET"])
    def api_tasks():
        tasks = []
        # Python 引擎任务
        for t in engine.get_all_tasks():
            tasks.append({
                "id": t.id, "url": t.url[:100], "filename": t.filename,
                "save_path": t.save_path, "total_size": t.total_size,
                "downloaded": t.downloaded, "speed": t.speed,
                "status": t.status.value, "progress": t.progress,
                "progress_pct": t.progress_pct, "connections": t.connections,
                "error": t.error, "engine": "python", "category": t.category,
                "retry_count": t.retry_count, "priority": t.priority,
            })
        # aria2 引擎任务
        if aria2.is_running:
            try:
                for t in aria2.get_all_tasks():
                    t["engine"] = "aria2"
                    tasks.append(t)
            except: pass
        return jsonify({"tasks": tasks})

    @app.route("/api/tasks/<tid>/pause", methods=["POST"])
    def api_pause(tid):
        engine.pause(tid)
        if aria2.is_running:
            try: aria2.pause(tid)
            except: pass
        return jsonify({"status": "paused"})

    @app.route("/api/tasks/<tid>/resume", methods=["POST"])
    def api_resume(tid):
        engine.resume(tid)
        if aria2.is_running:
            try: aria2.unpause(tid)
            except: pass
        return jsonify({"status": "resumed"})

    @app.route("/api/tasks/<tid>", methods=["DELETE"])
    def api_delete(tid):
        engine.cancel(tid)
        engine.delete(tid)
        if aria2.is_running:
            try: aria2.remove(tid)
            except: pass
        return jsonify({"status": "deleted"})

    @app.route("/api/tasks/batch", methods=["POST"])
    def api_batch():
        action = request.get_json().get("action", "")
        if action == "pause_all": engine.pause_all()
        elif action == "resume_all": engine.resume_all()
        elif action == "clear_completed": engine.clear_completed()
        return jsonify({"status": "ok"})

    @app.route("/api/tasks/<tid>/priority", methods=["POST"])
    def api_priority(tid):
        p = request.get_json().get("priority", 0)
        engine.set_priority(tid, p)
        return jsonify({"status": "ok"})

    # ---- History ----
    @app.route("/api/history", methods=["GET"])
    def api_history():
        return jsonify({"history": engine.get_history()})

    @app.route("/api/history", methods=["DELETE"])
    def api_clear_history():
        from src.downloader import HISTORY_FILE
        if HISTORY_FILE.exists(): HISTORY_FILE.unlink()
        return jsonify({"status": "cleared"})

    # ---- Stats ----
    @app.route("/api/stats", methods=["GET"])
    def api_stats():
        stats = engine.get_stats()
        if aria2.is_running:
            try:
                a2s = aria2.get_stats()
                if a2s:
                    stats["speed"] += int(a2s.get("downloadSpeed", 0))
                    stats["active"] += int(a2s.get("numActive", 0))
            except: pass
        stats["aria2_available"] = is_aria2_available()
        stats["aria2_running"] = aria2.is_running
        return jsonify(stats)

    # ---- Settings ----
    @app.route("/api/settings", methods=["GET", "POST"])
    def api_settings():
        if request.method == "GET":
            return jsonify(get_settings())
        else:
            save_settings(request.get_json())
            return jsonify({"status": "saved"})

    # ---- Open folder ----
    @app.route("/api/open_folder", methods=["POST"])
    def api_open_folder():
        path = request.get_json().get("path", "")
        if not path:
            path = get_settings().get("save_dir", str(Path.home() / "Downloads"))
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return jsonify({"status": "ok"})

    # ---- Clipboard ----
    _last_clip = ""

    @app.route("/api/clipboard", methods=["GET"])
    def api_clipboard():
        nonlocal _last_clip
        try:
            # Windows: 用 ctypes 读剪贴板，不用 tkinter
            if sys.platform == "win32":
                import ctypes
                import ctypes.wintypes as w
                CF_UNICODETEXT = 13
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                if not user32.OpenClipboard(0):
                    return jsonify({"text": "", "is_link": False})
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        return jsonify({"text": "", "is_link": False})
                    ptr = kernel32.GlobalLock(handle)
                    if not ptr:
                        return jsonify({"text": "", "is_link": False})
                    try:
                        text = ctypes.wstring_at(ptr)
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()

                text = text.strip()
                if not text or text == _last_clip or len(text) > 2000:
                    return jsonify({"text": "", "is_link": False})

                # 检查是否是链接
                if text.startswith(("http://", "https://", "magnet:", "ed2k://", "thunder://")):
                    _last_clip = text
                    return jsonify({"text": text[:500], "is_link": True, "url": text})
                return jsonify({"text": "", "is_link": False})
            return jsonify({"text": "", "is_link": False})
        except Exception:
            return jsonify({"text": "", "is_link": False})

    # ---- Engine status ----
    @app.route("/api/engine/aria2", methods=["POST"])
    def api_aria2_control():
        action = request.get_json().get("action", "")
        if action == "start":
            s = get_settings()
            return jsonify({"running": aria2.start(s.get("seed_time",0), s.get("seed_ratio",1.0))})
        if action == "stop": aria2.stop(); return jsonify({"running": False})
        if action == "status": return jsonify({"available": is_aria2_available(), "running": aria2.is_running})
        return jsonify({"error": "unknown"}), 400

    # ---- Motrix Next ----
    @app.route("/api/motrix", methods=["GET"])
    def api_motrix_status():
        m = MotrixIntegration()
        return jsonify({
            "installed": m.is_installed,
            "has_engine": m.has_engine,
            "exe_path": m.exe_path,
            "engine_path": m.engine_path,
            "version": "3.9.6",
            "download_url": m.download_url,
            "chrome_ext": m.chrome_ext_url,
            "firefox_ext": m.firefox_ext_url,
        })

    @app.route("/api/motrix/launch", methods=["POST"])
    def api_motrix_launch():
        m = MotrixIntegration()
        ok = m.launch()
        return jsonify({"launched": ok, "installed": m.is_installed})

    @app.route("/api/motrix/download", methods=["POST"])
    def api_motrix_download():
        """应用内下载 Motrix Next 安装程序"""
        m = MotrixIntegration()
        ok = m.download_installer()
        return jsonify({"started": ok, "installed": m.is_installed})

    # ---- 引擎管理 ----
    _engine_mgr = EngineManager()

    @app.route("/api/engines", methods=["GET"])
    def api_engines():
        return jsonify(_engine_mgr.to_api_response())

    @app.route("/api/engines/download", methods=["POST"])
    def api_engine_download():
        data = request.get_json()
        key = data.get("engine", "")
        url = data.get("url", "")
        save_dir = data.get("save_dir", str(Path.home() / "Downloads"))
        filename = data.get("filename", "")
        ok = _engine_mgr.download_with(key, url, save_dir, filename)
        return jsonify({"started": ok})

    # ---- 秒传 JSON ----
    @app.route("/api/miaochuan/parse", methods=["POST"])
    def api_miaochuan_parse():
        text = request.get_json().get("text", "")
        if not text.strip():
            return jsonify({"error": "请输入秒传 JSON 内容"}), 400
        pkg = MiaochuanPackage.parse(text)
        return jsonify(pkg.to_summary())

    # ---- 种子创建 + 做种 ----
    _seeder = Seeder(aria2)

    @app.route("/api/torrent/create", methods=["POST"])
    def api_torrent_create():
        """选择本地文件 → 创建 .torrent → 生成磁力链接"""
        data = request.get_json()
        file_path = data.get("file_path", "")
        if not file_path or not Path(file_path).exists():
            return jsonify({"error": "文件不存在"}), 400

        output_dir = data.get("output_dir") or str(Path(file_path).parent)
        trackers = data.get("trackers", [
            "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.demonii.com:1337/announce",
            "udp://tracker.openbittorrent.com:6969/announce",
        ])

        try:
            result = create_torrent(file_path, output_dir=output_dir, tracker_urls=trackers)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/torrent/seed", methods=["POST"])
    def api_torrent_seed():
        """开始做种 — 把 .torrent 提交给 aria2c"""
        data = request.get_json()
        torrent_path = data.get("torrent_path", "")
        file_path = data.get("file_path", "")

        if not is_aria2_available():
            return jsonify({"error": "aria2c 不可用，请确保 assets/aria2c.exe 存在"}), 400

        if not aria2.is_running:
            s = get_settings()
            aria2.start(s.get("seed_time", 60), s.get("seed_ratio", 0.0))

        result = _seeder.start_seeding(torrent_path, file_path)
        return jsonify(result)

    @app.route("/api/torrent/seeding", methods=["GET"])
    def api_torrent_seeding_list():
        return jsonify({"seeding": _seeder.get_seeding_list()})

    @app.route("/api/torrent/stop", methods=["POST"])
    def api_torrent_stop():
        key = request.get_json().get("key", "")
        ok = _seeder.stop_seeding(key)
        return jsonify({"stopped": ok})

    # 种子分享信息（手动构造的磁力链接）
    @app.route("/api/torrent/magnet", methods=["POST"])
    def api_torrent_magnet():
        """手动输入文件信息生成磁力链接"""
        data = request.get_json()
        name = data.get("name", "").strip()
        size = data.get("size", 0)
        info_hash = data.get("info_hash", "").strip()
        trackers = data.get("trackers", [])
        if not name or not info_hash:
            return jsonify({"error": "名称和 info_hash 不能为空"}), 400
        magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={name}"
        if size > 0:
            magnet += f"&xl={size}"
        for tr in trackers:
            magnet += f"&tr={tr}"
        return jsonify({"magnet": magnet})

    # ---- aria2c 命令行下载 ----
    @app.route("/api/aria2/command", methods=["POST"])
    def api_aria2_command():
        """直接执行 aria2c 命令行（支持自定义 header、cookie 等）"""
        command = request.get_json().get("command", "").strip()
        if not command:
            return jsonify({"error": "请输入 aria2c 命令"}), 400

        if not is_aria2_available():
            return jsonify({"error": "aria2c 不可用"}), 400

        # 替换命令中的 'aria2c' 为实际路径
        import shlex
        try:
            parts = shlex.split(command)
        except:
            parts = command.split()

        if not parts:
            return jsonify({"error": "命令为空"}), 400

        # 找到并替换 aria2c 路径
        exe = get_aria2_path()
        parts[0] = exe
        parts.append("--enable-rpc=false")  # 确保不冲突

        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.Popen(
                parts,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            return jsonify({"status": "started", "pid": proc.pid, "command": " ".join(parts)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/aria2/command/copy", methods=["GET"])
    def api_aria2_copy_command():
        """生成可复制的 aria2c 命令（含路径）"""
        url = request.args.get("url", "")
        filename = request.args.get("filename", "download")
        headers = request.args.get("headers", "")
        exe = get_aria2_path() or "aria2c"

        cmd = f'{exe} "{url}" --out "{filename}"'
        if headers:
            for h in headers.split(";"):
                h = h.strip()
                if h:
                    cmd += f' --header "{h}"'

        cmd += " --continue=true --max-connection-per-server=16 --split=16"

        return jsonify({"command": cmd})

    # ---- 原生文件选择器（服务端打开对话框） ----
    @app.route("/api/pick_file", methods=["POST"])
    def api_pick_file():
        """打开原生文件选择对话框，返回选中路径"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(title="选择文件")
            root.destroy()
            return jsonify({"path": path or ""})
        except Exception as e:
            return jsonify({"path": "", "error": str(e)})

    @app.route("/api/pick_folder", methods=["POST"])
    def api_pick_folder():
        """打开原生文件夹选择对话框"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="选择目录")
            root.destroy()
            return jsonify({"path": path or ""})
        except Exception as e:
            return jsonify({"path": "", "error": str(e)})

    return app, engine


class ServerThread(threading.Thread):
    """Flask 后台线程"""

    def __init__(self, app, port=18888):
        super().__init__(daemon=True)
        self.app = app
        self.port = port
        self.server = None
        self._done = False

    def run(self):
        from werkzeug.serving import make_server
        import socket
        srv = make_server("127.0.0.1", self.port, self.app, threaded=True)
        srv.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server = srv
        try:
            self.server.serve_forever()
        except:
            pass

    def shutdown(self):
        if self._done:
            return
        self._done = True
        if self.server:
            try:
                self.server.shutdown()
            except:
                pass
            try:
                self.server.server_close()
            except:
                pass
            self.server = None
