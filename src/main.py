"""
Aria2X Downloader v1.0 - 稳定版入口
Flask 后台 + Chrome/Edge App 模式窗口（非浏览器，无地址栏/标签栏）
"""

import sys
import os
import atexit
import logging
import socket
import subprocess
import time
import threading

if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_log_file = os.path.join(os.environ.get('TEMP', '.'), 'aria2x.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler(_log_file, encoding='utf-8')])
log = logging.getLogger("Aria2X")

from src.server import create_app, ServerThread

PORT = 18888
APP_URL = f"http://127.0.0.1:{PORT}"


def find_browser():
    """查找可用的浏览器（支持 App 模式）"""
    candidates = [
        # Chrome
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
        # Edge (Chromium)
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        os.path.expandvars("%PROGRAMFILES(x86)%/Microsoft/Edge/Application/msedge.exe"),
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def is_port_in_use(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        r = s.connect_ex(("127.0.0.1", port))
        s.close()
        return r == 0
    except:
        return False


def kill_old(port):
    if not is_port_in_use(port):
        return True
    log.info(f"Port {port} in use, killing old instance")
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
        time.sleep(2)
        return not is_port_in_use(port)
    except:
        return not is_port_in_use(port)


def main():
    log.info("=== Aria2X starting ===")

    if not kill_old(PORT):
        log.error("Cannot free port")
        sys.exit(1)

    app, engine = create_app()
    server = ServerThread(app, PORT)

    _cleaned = False

    def cleanup():
        nonlocal _cleaned
        if _cleaned:
            return
        _cleaned = True
        log.info("Cleaning up...")
        try: server.shutdown()
        except: pass
        try: engine.stop()
        except: pass

    atexit.register(cleanup)
    server.start()

    # 等 Flask 就绪
    for i in range(30):
        time.sleep(0.3)
        try:
            import urllib.request
            urllib.request.urlopen(f"{APP_URL}/api/stats", timeout=1)
            break
        except:
            if i == 29:
                log.error("Flask failed to start")
                sys.exit(1)
    log.info(f"Flask ready on :{PORT}")

    # 下载完成通知
    engine.on_complete = lambda task: log.info(f"Download complete: {task.filename}")

    # 打开浏览器 App 模式窗口
    browser = find_browser()
    if browser:
        log.info(f"Using browser: {browser}")
        # App 模式：无地址栏，无标签栏，像原生窗口一样
        subprocess.Popen(
            [browser, f"--app={APP_URL}", "--new-window",
             "--window-size=1080,720", "--user-data-dir=" + os.path.join(
                 os.environ.get("TEMP", "."), "aria2x_browser_profile")],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    else:
        # 回退：普通浏览器
        log.info("No Chrome/Edge found, opening default browser")
        import webbrowser
        webbrowser.open(APP_URL)

    # 保持运行直到 Flask 线程退出
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
