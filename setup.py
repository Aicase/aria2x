"""
Aria2X - Windows 安装程序
运行: Aria2X_Setup.exe  →  图形向导安装
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def get_resource_dir():
    """获取资源目录（兼容 PyInstaller）"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.resolve()


APP_NAME = "Aria2X Downloader"
APP_VER = "1.0.0"


def find_app_exe():
    """查找要安装的 Aria2X.exe"""
    res = get_resource_dir()
    # PyInstaller 打包后嵌入的 exe
    candidates = [
        res / "Aria2X.exe",
        res / "assets" / "Aria2X.exe",
        Path(__file__).parent / "Aria2X.exe",
        Path(__file__).parent / "dist" / "Aria2X.exe",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 1_000_000:
            return str(c)
    return None


def install():
    """执行安装"""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    app_exe = find_app_exe()
    if not app_exe:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", "未找到 Aria2X.exe 主程序文件")
        return

    default_dir = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Aria2X"

    root = tk.Tk()
    root.title(f"{APP_NAME} 安装程序")
    root.geometry("520x440")
    root.resizable(False, False)
    root.configure(bg="#0d1525")

    # 居中
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 520) // 2
    y = (root.winfo_screenheight() - 440) // 2
    root.geometry(f"+{x}+{y}")

    install_dir = tk.StringVar(value=str(default_dir))
    mk_desktop = tk.BooleanVar(value=True)
    mk_start = tk.BooleanVar(value=True)

    s = ttk.Style()
    s.theme_use("clam")
    s.configure("TFrame", background="#0d1525")
    s.configure("TLabel", background="#0d1525", foreground="#dce4f0", font=("Segoe UI", 10))
    s.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#00d4aa")
    s.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#7088a8")
    s.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10)
    s.configure("Accent.TButton", background="#00d4aa", foreground="#000000")
    s.configure("TCheckbutton", background="#0d1525", foreground="#dce4f0")
    s.configure("TLabelframe", background="#0d1525", foreground="#00d4aa")
    s.configure("TEntry", fieldbackground="#060b14", foreground="#dce4f0")

    # 头部
    ttk.Label(root, text="⬇  Aria2X Downloader", style="Title.TLabel").pack(anchor="w", padx=32, pady=(32, 2))
    ttk.Label(root, text=f"版本 {APP_VER}  ·  轻量级全能下载器", style="Sub.TLabel").pack(anchor="w", padx=32)

    # 安装路径
    lf = ttk.LabelFrame(root, text=" 安装目录 ", padding=16)
    lf.pack(fill="x", padx=32, pady=(20, 12))
    path_row = ttk.Frame(lf)
    path_row.pack(fill="x")
    entry = ttk.Entry(path_row, textvariable=install_dir, font=("Consolas", 10))
    entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(path_row, text="浏览...", command=lambda: _browse(install_dir)).pack(side="right")

    # 选项
    of = ttk.LabelFrame(root, text=" 快捷方式 ", padding=16)
    of.pack(fill="x", padx=32, pady=8)
    ttk.Checkbutton(of, text="创建桌面快捷方式", variable=mk_desktop).pack(anchor="w")
    ttk.Checkbutton(of, text="创建开始菜单文件夹", variable=mk_start).pack(anchor="w", pady=6)

    # 底部
    bf = ttk.Frame(root)
    bf.pack(fill="x", padx=32, pady=24)
    ttk.Button(bf, text="取消", command=root.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(bf, text="安装", style="Accent.TButton", command=lambda: _do_install()).pack(side="right")

    def _browse(var):
        d = filedialog.askdirectory(initialdir=var.get())
        if d:
            var.set(d)

    def _do_install():
        dest = Path(install_dir.get())
        try:
            dest.mkdir(parents=True, exist_ok=True)

            # 复制主程序
            shutil.copy2(app_exe, str(dest / "Aria2X.exe"))

            # 复制图标
            icon_src = get_resource_dir() / "assets" / "icon.ico"
            if icon_src.exists():
                shutil.copy2(str(icon_src), str(dest / "icon.ico"))

            # 桌面快捷方式
            if mk_desktop.get():
                _create_shortcut(
                    str(dest / "Aria2X.exe"),
                    os.path.join(os.environ["USERPROFILE"], "Desktop", f"{APP_NAME}.lnk"),
                    str(dest),
                )

            # 开始菜单
            if mk_start.get():
                start_dir = os.path.join(
                    os.environ["APPDATA"],
                    "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
                )
                os.makedirs(start_dir, exist_ok=True)
                _create_shortcut(
                    str(dest / "Aria2X.exe"),
                    os.path.join(start_dir, f"{APP_NAME}.lnk"),
                    str(dest),
                )

            # 卸载程序
            _create_uninstaller(dest)

            # 注册卸载信息
            _register_uninstall(dest)

            messagebox.showinfo("安装完成", f"{APP_NAME} 已成功安装到:\n{dest}\n\n可以双击桌面快捷方式启动。")

            if messagebox.askyesno("启动", "是否立即启动 Aria2X?"):
                subprocess.Popen([str(dest / "Aria2X.exe")], cwd=str(dest))

            root.destroy()

        except Exception as ex:
            messagebox.showerror("安装失败", str(ex))

    root.mainloop()


def _create_shortcut(target, link_path, work_dir):
    """创建 .lnk 快捷方式"""
    try:
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(link_path)
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = work_dir
        shortcut.Description = APP_NAME
        icon = Path(work_dir) / "icon.ico"
        if icon.exists():
            shortcut.IconLocation = str(icon)
        shortcut.WindowStyle = 1
        shortcut.save()
    except Exception:
        # 回退: 创建 .bat
        bat_path = link_path.replace(".lnk", ".bat")
        with open(bat_path, "w", encoding="gbk") as f:
            f.write(f'@echo off\ncd /d "{work_dir}"\nstart "" "{target}"\n')


def _create_uninstaller(dest):
    """创建卸载脚本"""
    uninstall_bat = dest / "uninstall.bat"
    content = f'''@echo off
chcp 65001 >nul 2>&1
echo 正在卸载 {APP_NAME}...
echo.

:: 结束正在运行的进程
taskkill /f /im Aria2X.exe 2>nul

:: 删除快捷方式
del /f /q "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" 2>nul
del /f /q "%USERPROFILE%\\Desktop\\{APP_NAME}.bat" 2>nul
rmdir /s /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}" 2>nul

:: 删除注册表
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Aria2X" /f 2>nul

:: 删除安装目录
cd /
rmdir /s /q "{dest}" 2>nul

echo.
echo {APP_NAME} 已卸载完成。
echo.
pause
del "%~f0"
'''
    uninstall_bat.write_text(content, encoding="gbk")


def _register_uninstall(dest):
    """注册到 Windows 卸载列表"""
    try:
        import winreg
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Aria2X"
        )
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VER)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Aria2X")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(dest))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, str(dest / "uninstall.bat"))
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
    except Exception:
        pass


if __name__ == "__main__":
    install()
