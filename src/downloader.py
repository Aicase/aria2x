"""
Aria2X - 多线程下载引擎
支持: 分片并发、断点续传、自动重试、速度限制、历史持久化
"""

import os
import re
import time
import json
import queue
import threading
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUEUED = "queued"


@dataclass
class DownloadTask:
    id: str
    url: str
    filename: str = ""
    save_path: str = ""
    total_size: int = -1
    downloaded: int = 0
    speed: int = 0
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    thread_count: int = 4
    connections: int = 0
    error: str = ""
    created_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 0          # 0=normal, 1=high
    category: str = ""         # video/music/doc/software/other
    _cancel: bool = field(default=False, repr=False)
    _pause: bool = field(default=False, repr=False)
    _chunks: list = field(default_factory=list, repr=False)

    @property
    def progress_pct(self): return int(self.progress * 100)


HISTORY_FILE = Path.home() / ".aria2x_history.json"
SETTINGS_FILE = Path.home() / ".aria2x_settings.json"


def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return []


def save_history(tasks: list):
    try:
        data = [t for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)]
        out = []
        for t in data[-200:]:  # keep last 200
            out.append({
                "id": t.id, "url": t.url[:200], "filename": t.filename,
                "save_path": t.save_path, "total_size": t.total_size,
                "status": t.status.value, "created_at": t.created_at,
                "completed_at": t.completed_at, "category": t.category,
            })
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except: pass


class DownloadEngine:
    """多线程下载引擎 — 持久化 + 重试 + 限速 + 队列"""

    def __init__(self, max_concurrent=5, speed_limit=0):
        self.max_concurrent = max_concurrent
        self.speed_limit = speed_limit  # KB/s, 0=unlimited
        self._tasks = {}
        self._task_queue = queue.PriorityQueue()
        self._running = False
        self._lock = threading.RLock()
        self.on_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self._load_persisted()

    def _load_persisted(self):
        """加载历史记录"""
        for h in load_history():
            tid = h.get("id", "")
            if tid and tid not in self._tasks:
                t = DownloadTask(
                    id=tid, url=h.get("url",""), filename=h.get("filename",""),
                    save_path=h.get("save_path",""), total_size=h.get("total_size",-1),
                    status=TaskStatus(h.get("status","completed")),
                    created_at=h.get("created_at",0), completed_at=h.get("completed_at",0),
                    category=h.get("category",""),
                )
                self._tasks[tid] = t

    # ---- Public API ----

    def add_task(self, url, save_dir=None, filename=None, threads=4, priority=0, category=""):
        import hashlib
        tid = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
        with self._lock:
            task = DownloadTask(
                id=tid, url=url, filename=filename or "", save_path=save_dir or "",
                thread_count=threads, created_at=time.time(), priority=priority, category=category,
            )
            self._tasks[tid] = task
        self._task_queue.put((-priority, tid))  # negative for max-heap
        return tid

    def start(self):
        self._running = True
        threading.Thread(target=self._scheduler, daemon=True).start()

    def stop(self):
        self._running = False
        with self._lock:
            for t in self._tasks.values():
                t._cancel = True
            save_history(list(self._tasks.values()))

    def pause(self, tid):
        with self._lock:
            if tid in self._tasks: self._tasks[tid]._pause = True

    def resume(self, tid):
        with self._lock:
            if tid in self._tasks:
                t = self._tasks[tid]
                t._pause = False
                if t.status in (TaskStatus.PAUSED, TaskStatus.FAILED):
                    t.status = TaskStatus.PENDING
                    t.retry_count = 0
                    self._task_queue.put((-t.priority, tid))

    def cancel(self, tid):
        with self._lock:
            if tid in self._tasks:
                self._tasks[tid]._cancel = True
                self._tasks[tid].status = TaskStatus.CANCELLED

    def delete(self, tid):
        with self._lock:
            self._tasks.pop(tid, None)

    def clear_completed(self):
        with self._lock:
            done = [tid for tid, t in self._tasks.items()
                   if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)]
            for tid in done:
                self._tasks.pop(tid, None)
            save_history(list(self._tasks.values()))

    def pause_all(self):
        with self._lock:
            for t in self._tasks.values():
                if t.status in (TaskStatus.DOWNLOADING, TaskStatus.PENDING):
                    t._pause = True
                    t.status = TaskStatus.PAUSED

    def resume_all(self):
        with self._lock:
            for tid, t in list(self._tasks.items()):
                if t.status == TaskStatus.PAUSED:
                    self.resume(tid)

    def set_priority(self, tid, priority):
        with self._lock:
            if tid in self._tasks:
                self._tasks[tid].priority = priority

    def get_task(self, tid):
        with self._lock: return self._tasks.get(tid)

    def get_all_tasks(self):
        with self._lock: return sorted(self._tasks.values(), key=lambda t: (-t.priority, t.created_at))

    def get_active_tasks(self):
        with self._lock: return [t for t in self._tasks.values() if t.status == TaskStatus.DOWNLOADING]

    def get_history(self):
        return load_history()

    def get_stats(self):
        with self._lock:
            active = sum(1 for t in self._tasks.values() if t.status == TaskStatus.DOWNLOADING)
            total_speed = sum(t.speed for t in self._tasks.values() if t.status == TaskStatus.DOWNLOADING)
            completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
            waiting = sum(1 for t in self._tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED))
            return {"active": active, "speed": total_speed, "completed": completed,
                    "failed": failed, "waiting": waiting, "total": len(self._tasks)}

    # ---- Scheduler ----

    def _scheduler(self):
        while self._running:
            active = sum(1 for t in self._tasks.values() if t.status == TaskStatus.DOWNLOADING)
            if active < self.max_concurrent:
                try:
                    _, tid = self._task_queue.get(timeout=1)
                    with self._lock:
                        task = self._tasks.get(tid)
                    if task and task.status == TaskStatus.PENDING:
                        threading.Thread(target=self._download_task, args=(task,), daemon=True).start()
                except queue.Empty:
                    pass
            else:
                time.sleep(0.5)
            # 定期持久化
            if int(time.time()) % 30 == 0:
                save_history(list(self._tasks.values()))

    # ---- Download ----

    def _download_task(self, task: DownloadTask):
        task.status = TaskStatus.DOWNLOADING
        for attempt in range(task.max_retries + 1):
            if task._cancel: return
            try:
                info = self._fetch_info(task.url)
                task.total_size = info.get("size", -1)
                if not task.filename:
                    task.filename = self._extract_filename(task.url, info.get("filename", ""))
                if not task.save_path:
                    task.save_path = str(Path.home() / "Downloads")
                full_path = Path(task.save_path) / task.filename
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # 已存在且完整
                if full_path.exists() and task.total_size > 0 and full_path.stat().st_size == task.total_size:
                    task.downloaded = task.total_size
                    task.progress = 1.0
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = time.time()
                    self._notify(task)
                    return

                # 分片 or 直接下载
                if task.total_size > 1024*1024 and info.get("resume"):
                    self._download_chunked(task, full_path)
                else:
                    self._download_direct(task, full_path)

                if task._cancel:
                    task.status = TaskStatus.CANCELLED
                    return
                if task._pause:
                    task.status = TaskStatus.PAUSED
                    return

                # 验证
                if full_path.exists() and (task.total_size < 0 or full_path.stat().st_size >= task.total_size * 0.99):
                    task.downloaded = full_path.stat().st_size
                    task.progress = 1.0
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = time.time()
                    self._notify(task)
                    return
                elif not task._pause:
                    raise Exception("下载不完整")

            except Exception as e:
                if task._cancel: return
                if attempt < task.max_retries:
                    task.retry_count = attempt + 1
                    time.sleep(2 * (attempt + 1))  # 指数退避
                    continue
                task.status = TaskStatus.FAILED
                task.error = str(e)
                if self.on_error: self.on_error(task)
                return

    def _fetch_info(self, url):
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Aria2X/1.0")
            with urllib.request.urlopen(req, timeout=15) as resp:
                size = int(resp.headers.get("Content-Length", -1))
                resume = resp.headers.get("Accept-Ranges", "") == "bytes"
                cd = resp.headers.get("Content-Disposition", "")
                fn = ""
                if cd:
                    m = re.search(r'filename[*]?=["\']?([^"\';\n\r]*)', cd)
                    if m: fn = m.group(1)
                return {"size": size, "resume": resume, "filename": fn}
        except:
            return {"size": -1, "resume": False, "filename": ""}

    def _extract_filename(self, url, cd_fn=""):
        from urllib.parse import urlparse, unquote
        if cd_fn: return unquote(cd_fn)
        path = urlparse(url).path
        name = path.split("/")[-1]
        return unquote(name) if name else f"download_{int(time.time())}"

    def _download_direct(self, task, path):
        req = urllib.request.Request(task.url)
        req.add_header("User-Agent", "Aria2X/1.0")
        # 断点续传
        if path.exists() and path.stat().st_size > 0:
            req.add_header("Range", f"bytes={path.stat().st_size}-")
            mode = "ab"
            task.downloaded = path.stat().st_size
        else:
            mode = "wb"

        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(path, mode) as f:
                chunk_size = 64 * 1024
                last_update = time.time()
                bytes_since = 0
                while True:
                    if task._cancel or task._pause: return
                    chunk = resp.read(chunk_size)
                    if not chunk: break
                    f.write(chunk)
                    task.downloaded += len(chunk)
                    bytes_since += len(chunk)
                    if task.total_size > 0:
                        task.progress = task.downloaded / task.total_size
                    now = time.time()
                    if now - last_update >= 0.5:
                        task.speed = int(bytes_since / (now - last_update))
                        # 限速
                        if self.speed_limit > 0 and task.speed > self.speed_limit * 1024:
                            time.sleep((bytes_since / (self.speed_limit * 1024)) - (now - last_update))
                        bytes_since = 0
                        last_update = now

    def _download_chunked(self, task, path):
        if task.total_size <= 0:
            return self._download_direct(task, path)
        chunk_size = max(task.total_size // task.thread_count, 1024 * 1024)
        chunks = []
        for i in range(task.thread_count):
            start = i * chunk_size
            end = start + chunk_size - 1 if i < task.thread_count - 1 else task.total_size - 1
            if start < task.total_size:
                chunks.append((start, end))

        task.connections = len(chunks)
        results = [0] * len(chunks)
        threads = []
        errors = []

        def _dl_chunk(idx, start, end):
            if task._cancel or task._pause: return
            try:
                req = urllib.request.Request(task.url)
                req.add_header("User-Agent", "Aria2X/1.0")
                req.add_header("Range", f"bytes={start}-{end}")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                    results[idx] = len(data)
                    with open(path, "r+b") as f:
                        f.seek(start)
                        f.write(data)
                    with self._lock:
                        task.downloaded += len(data)
                        task.progress = task.downloaded / task.total_size
            except Exception as e:
                errors.append(str(e))

        if not path.exists():
            with open(path, "wb") as f:
                f.seek(task.total_size - 1)
                f.write(b"\0")

        last_update = time.time()
        last_dl = task.downloaded
        for i, (s, e) in enumerate(chunks):
            t = threading.Thread(target=_dl_chunk, args=(i, s, e))
            t.start()
            threads.append(t)

        while any(t.is_alive() for t in threads):
            if task._cancel or task._pause: return
            time.sleep(0.5)
            now = time.time()
            if now - last_update >= 0.5:
                task.speed = int((task.downloaded - last_dl) / (now - last_update))
                if self.speed_limit > 0 and task.speed > self.speed_limit * 1024:
                    time.sleep(0.3)
                last_dl = task.downloaded
                last_update = now

        if errors:
            raise Exception("; ".join(errors[:3]))

    def _notify(self, task):
        save_history(list(self._tasks.values()))
        if self.on_complete: self.on_complete(task)
