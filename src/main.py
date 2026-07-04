"""
Aria2X Downloader v1.0 - 应用入口
pywebview 原生窗口 + 系统托盘 + 通知
"""

import sys
import os

# === 修复 WebView2 递归崩溃 ===
# 禁用无障碍功能避免 "maximum recursion depth / Empty.Empty.Empty" 崩溃
os.environ["WEBVIEW2_DISABLE_ACCESSIBILITY"] = "1"
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-features=msWebView2Accelerator,msWebView2Accessibility"

import atexit
import logging
import socket

if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_log_file = os.path.join(os.environ.get('TEMP', '.'), 'aria2x.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler(_log_file, encoding='utf-8')])
log = logging.getLogger("Aria2X")

import webview
from src.server import create_app, ServerThread

PORT = 18888


def is_port_in_use(port):
    """检查端口是否被占用"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        return result == 0
    except:
        return False


def kill_old_instance(port):
    """如果端口被占用，尝试杀掉占用进程"""
    if not is_port_in_use(port):
        return True
    log.info(f"Port {port} in use, trying to kill old instance...")
    try:
        if sys.platform == "win32":
            import subprocess
            # 找到占用端口的 PID
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        log.info(f"Killing PID {pid}")
                        subprocess.run(["taskkill", "/F", "/PID", pid],
                                       capture_output=True, timeout=5)
            import time
            time.sleep(2)
            return not is_port_in_use(port)
    except Exception as e:
        log.info(f"kill_old_instance: {e}")
    return not is_port_in_use(port)


class JsBridge:
    """JS ↔ Python 原生 API 桥接 — 所有方法都在 webview 线程中调用"""

    def __init__(self):
        self.window = None

    def pick_folder(self, initial_dir=""):
        try:
            result = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initial_dir if initial_dir else None,
            )
            if result and len(result) > 0:
                return result[0]
        except Exception as e:
            log.info(f"pick_folder: {e}")
        return ""

    def pick_file(self, initial_dir=""):
        """原生文件选择对话框 — 用于做种选择文件"""
        try:
            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=initial_dir if initial_dir else None,
            )
            if result and len(result) > 0:
                return result[0]
        except Exception as e:
            log.info(f"pick_file: {e}")
        return ""

    def open_folder(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
        except Exception as e:
            log.info(f"open_folder: {e}")
        return ""

    def minimize_to_tray(self):
        if self.window:
            self.window.hide()
        return ""

    def notify(self, title, message):
        """系统通知 — 用 subprocess 不阻塞"""
        try:
            if sys.platform == "win32":
                import subprocess
                ps = (
                    'Add-Type -AssemblyName System.Windows.Forms;'
                    f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                    '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                    f'$n.BalloonTipTitle="{title}";'
                    f'$n.BalloonTipText="{message}";'
                    '$n.Visible=$true;'
                    '$n.ShowBalloonTip(3000);'
                    'Start-Sleep -Seconds 4;'
                    '$n.Dispose()'
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        except:
            pass
        return ""


def main():
    log.info("=== Aria2X starting ===")

    # 单实例检查 + 清理旧进程
    if not kill_old_instance(PORT):
        log.error("Cannot free port, aborting")
        # 用 MessageBox 提示用户
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "Aria2X 已经在运行中，请先关闭再启动。", "Aria2X", 0x40
            )
        except:
            pass
        sys.exit(1)

    app, engine = create_app()
    server = ServerThread(app, PORT)
    bridge = JsBridge()

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
        log.info("Cleanup done.")

    atexit.register(cleanup)

    server.start()

    # 等 Flask 就绪
    import time
    for i in range(30):
        time.sleep(0.3)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/stats", timeout=1)
            break
        except:
            if i == 29:
                log.error("Flask failed to start")
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0, "服务器启动失败，请检查端口是否被占用。", "Aria2X", 0x10
                    )
                except:
                    pass
                sys.exit(1)
    log.info(f"Flask ready on :{PORT}")

    # 下载完成通知
    engine.on_complete = lambda task: bridge.notify("Aria2X 下载完成", task.filename)

    url = f"http://127.0.0.1:{PORT}"

    window = webview.create_window(
        title="Aria2X Downloader",
        url=url,
        width=1080,
        height=720,
        min_size=(800, 500),
        text_select=False,
        frameless=False,
        easy_drag=False,
        js_api=bridge,
    )
    bridge.window = window

    def on_closing():
        log.info("Window closing")
        cleanup()

    window.events.closing += on_closing

    # 不再启动后台剪贴板线程 — 改为前端 JS 定时通过 API 检查
    # 避免 tkinter 线程安全问题和 evaluate_js 死锁

    try:
        webview.start(debug=False)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
