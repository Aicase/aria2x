"""
Aria2X - 种子创建器
选择本地文件/目录 → 创建 .torrent 文件 → 生成磁力链接 → aria2c 做种
"""

import os
import sys
import json
import hashlib
import threading
from pathlib import Path
from typing import Optional, Callable


# ========== Bencode 编码器（最小实现） ==========

def _bencode(obj) -> bytes:
    """Bencode 编码：int → i42e, str/bytes → 4:spam, list → l...e, dict → d...e"""
    if isinstance(obj, int):
        return f"i{obj}e".encode()
    if isinstance(obj, (str, bytes)):
        s = obj if isinstance(obj, bytes) else obj.encode("utf-8")
        return f"{len(s)}:".encode() + s
    if isinstance(obj, list):
        parts = b"".join(_bencode(v) for v in obj)
        return b"l" + parts + b"e"
    if isinstance(obj, dict):
        keys = sorted(obj.keys(), key=lambda k: str(k) if isinstance(k, str) else k.decode() if isinstance(k, bytes) else k)
        parts = b""
        for k in keys:
            parts += _bencode(k) + _bencode(obj[k])
        return b"d" + parts + b"e"
    raise TypeError(f"Cannot bencode {type(obj)}")


# ========== 种子创建 ==========

PIECE_SIZE = 256 * 1024  # 256 KB per piece


def create_torrent(
    file_path: str,
    output_dir: str = None,
    tracker_urls: list = None,
    comment: str = "Created by Aria2X",
    piece_size: int = PIECE_SIZE,
    callback: Callable = None,
) -> dict:
    """
    从本地文件创建 .torrent 文件，生成磁力链接。

    返回: {
        "torrent_path": "path/to/file.torrent",
        "magnet": "magnet:?xt=urn:btih:...",
        "info_hash": "ABC123...",
        "file_name": "file.txt",
        "file_size": 12345,
        "piece_count": 10,
    }
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    is_single_file = path.is_file()
    files = []
    total_size = 0

    if is_single_file:
        files.append({"path": [path.name], "length": path.stat().st_size})
        total_size = path.stat().st_size
    else:
        # 目录
        for f in sorted(path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(path)
                files.append({"path": list(rel.parts), "length": f.stat().st_size})
                total_size += f.stat().st_size

    if total_size == 0:
        raise ValueError("文件大小为0或目录为空")

    # 计算 pieces (SHA1)
    pieces = []
    buf = bytearray()
    piece_idx = 0
    last_callback = 0

    if is_single_file:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(piece_size)
                if not chunk:
                    break
                buf.extend(chunk)
                while len(buf) >= piece_size or (len(buf) > 0 and len(chunk) == 0):
                    piece_data = bytes(buf[:piece_size]) if len(buf) >= piece_size else bytes(buf)
                    pieces.append(hashlib.sha1(piece_data).digest())
                    buf = buf[piece_size:] if len(buf) >= piece_size else bytearray()
                    piece_idx += 1
                    # 进度回调
                    if callback and piece_idx % 10 == 0:
                        cb_pct = min(int(piece_idx * piece_size / total_size * 100), 99)
                        if cb_pct > last_callback:
                            callback(cb_pct)
                            last_callback = cb_pct
        if buf:
            pieces.append(hashlib.sha1(bytes(buf)).digest())
    else:
        # 多文件目录
        for f_info in files:
            fp = path
            for part in f_info["path"]:
                fp = fp / part
            with open(fp, "rb") as f:
                while True:
                    chunk = f.read(piece_size)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    while len(buf) >= piece_size:
                        pieces.append(hashlib.sha1(bytes(buf[:piece_size])).digest())
                        buf = buf[piece_size:]
                        piece_idx += 1
                        if callback and piece_idx % 10 == 0:
                            callback(min(piece_idx * piece_size / total_size * 100, 99))
        if buf:
            pieces.append(hashlib.sha1(bytes(buf)).digest())

    pieces_combined = b"".join(pieces)

    # 构建 info 字典
    if is_single_file:
        info = {
            b"name": path.name,
            b"piece length": piece_size,
            b"pieces": pieces_combined,
            b"length": total_size,
        }
    else:
        info = {
            b"name": path.name,
            b"piece length": piece_size,
            b"pieces": pieces_combined,
            b"files": [{b"length": f["length"], b"path": [bytes(p, "utf-8") for p in f["path"]]} for f in files],
        }

    # 计算 info_hash (SHA1 of bencoded info)
    info_bencoded = _bencode(info)
    info_hash = hashlib.sha1(info_bencoded).hexdigest().upper()

    # 构建 torrent 字典
    announce = (tracker_urls[0] if tracker_urls else "udp://tracker.opentrackr.org:1337/announce")
    announce_list = [[url] for url in (tracker_urls or [])]
    torrent = {
        b"announce": announce.encode("utf-8"),
        b"info": info,
        b"created by": f"Aria2X {comment}".encode("utf-8"),
    }

    # 写入 .torrent 文件
    output_dir = Path(output_dir) if output_dir else path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    torrent_path = output_dir / f"{path.name}.torrent"

    with open(torrent_path, "wb") as f:
        f.write(_bencode(torrent))

    if callback:
        callback(100)

    # 生成磁力链接
    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={path.name}&xl={total_size}"
    if tracker_urls:
        for tr in tracker_urls:
            magnet += f"&tr={tr}"

    return {
        "torrent_path": str(torrent_path),
        "magnet": magnet,
        "info_hash": info_hash,
        "file_name": path.name,
        "file_size": total_size,
        "piece_count": len(pieces),
        "piece_size": piece_size,
    }


# ========== 做种管理 ==========

class Seeder:
    """管理 aria2c 做种进程"""

    def __init__(self, aria2_engine=None):
        self._engine = aria2_engine
        self._seeding_tasks = {}  # info_hash → {torrent_path, file_path, ...}

    def start_seeding(self, torrent_path: str, file_path: str) -> dict:
        """开始做种 — 将 torrent 文件添加到 aria2c"""
        if not self._engine:
            return {"error": "aria2c 引擎未启动"}
        if not self._engine.is_running:
            self._engine.start()

        try:
            import base64
            with open(torrent_path, "rb") as f:
                torrent_b64 = base64.b64encode(f.read()).decode()

            # 设置下载目录为文件所在目录
            file_dir = str(Path(file_path).parent)
            aria2 = self._engine._process
            if not aria2 or aria2.poll() is not None:
                return {"error": "aria2c 进程已退出"}

            # 用 RPC 添加 torrent，但设置 dir 让 aria2c 找到已有文件
            gid = self._engine._rpc_call("aria2.addTorrent", [torrent_b64, [], {"dir": file_dir, "seed-time": "0"}])

            info_hash = hashlib.sha1(torrent_b64.encode()).hexdigest()
            # 实际需要用文件内容算，但这里用文件名做 key
            task_key = str(Path(torrent_path).name)
            self._seeding_tasks[task_key] = {
                "gid": gid,
                "torrent_path": torrent_path,
                "file_path": file_path,
            }

            return {"gid": gid, "status": "seeding"}

        except Exception as e:
            return {"error": str(e)}

    def stop_seeding(self, task_key: str):
        if task_key in self._seeding_tasks:
            gid = self._seeding_tasks[task_key]["gid"]
            try:
                self._engine._rpc_call("aria2.remove", [gid])
            except:
                pass
            del self._seeding_tasks[task_key]
            return True
        return False

    def get_seeding_list(self) -> list:
        return [
            {"key": k, "torrent_path": v["torrent_path"], "file_path": v["file_path"]}
            for k, v in self._seeding_tasks.items()
        ]
