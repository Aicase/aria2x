<p align="center">
  <img src="assets/icon.ico" width="72" alt="Aria2X">
</p>
<h1 align="center">Aria2X Downloader</h1>
<p align="center">
  <strong>轻量级全能桌面下载器</strong><br>
  纯 Python 多线程引擎 · 原生窗口 · 双引擎(内置aria2c) · P2P做种
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12%2B-green?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/engine-aria2c%2BPython-orange" alt="Engine">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
  <img src="https://img.shields.io/badge/release-v1.0.0-brightgreen" alt="Release">
</p>

---

## 功能特性

### 下载能力

- **双引擎架构** — Python 原生多线程 HTTP 引擎 + 内置 aria2c.exe
- **全格式支持** — HTTP/HTTPS/FTP、Magnet(含Hash自动补全)、ED2K、Thunder、Metalink
- **多线程分片** — 可配置 1-16 线程并发，支持 Range 断点续传
- **BT 下载** — 内置 aria2c，支持 torrent 和磁力链接
- **自动重试** — 失败 3 次指数退避重试
- **速度限制** — 可配置 0-10MB/s 限速

### 分享能力

- **创建种子** — 选择本地文件 → 自动生成 .torrent 文件
- **生成磁力链接** — 自动计算 info_hash，生成可分享的磁力链接
- **做种** — 内置 aria2c 做种，可配置做种时间和比率
- **一键复制** — 磁力链接一键复制到剪贴板

### 桌面体验

- **原生窗口** — pywebview + WebView2，非浏览器
- **低对比度简约 UI** — 4 套主题 (Slate/Graphite/Paper/Moss)
- **系统托盘** — 最小化到托盘后台运行
- **系统通知** — 下载完成 Windows 通知
- **剪贴板监听** — 自动检测复制的下载链接
- **拖拽添加** — 拖 .torrent 文件或链接到窗口

### 多引擎生态

- **6 引擎自动检测** — Python原生 / aria2c / cURL / IDM / BitComet 彗星 / Motrix Next
- **IDM 集成** — 检测 Internet Download Manager，一键调用
- **Motrix Next 集成** — 应用内下载安装，优先使用 aria2-next 引擎

### 其他

- **秒传 JSON** — 解析百度网盘秒传格式
- **下载历史** — 持久化保存，重启不丢
- **批量操作** — 全部暂停/恢复/清除已完成
- **代理支持** — HTTP 代理配置

---

## 安装

### 方案一：一键安装（推荐）

下载 [Aria2X_Setup.exe](https://github.com/Aicase/aria2x/releases/latest) → 双击安装 → 选择目录 → 完成

### 方案二：便携版

下载 [Aria2X.exe](https://github.com/Aicase/aria2x/releases/latest) → 双击即用（无需安装）

---

## 开发

```bash
# 克隆仓库
git clone https://github.com/Aicase/aria2x.git
cd aria2x

# 安装依赖
pip install -r requirements.txt

# 下载 aria2c.exe（BT/磁力必需，HTTP 可选）
python download_aria2.py

# 运行
python src/main.py

# 构建
python build.py              # → Aria2X.exe (根目录)
python setup.py --build      # → Aria2X_Setup.exe
# 或一步到位:
python release.py            # → 主程序 + 安装程序
```

---

## 项目结构

```
aria2x/
├── src/
│   ├── main.py              # 入口：pywebview 窗口 + Flask 后台
│   ├── server.py            # REST API（多引擎统一管理）
│   ├── downloader.py        # Python 多线程 HTTP 引擎
│   ├── link_parser.py       # 全格式链接解析器
│   ├── aria2_engine.py      # aria2c 进程管理 + RPC
│   ├── engines.py           # 6引擎自动检测管理器
│   ├── torrent_creator.py   # 种子创建 + 磁力链接生成
│   ├── motrix.py            # Motrix Next 集成
│   ├── miaochuan.py         # 秒传 JSON 解析
│   └── web/
│       └── index.html       # 前端 SPA
├── assets/
│   └── icon.ico
├── download_aria2.py        # aria2c 下载脚本
├── build.py                 # 单独打包主程序
├── setup.py                 # 安装向导
├── release.py               # 一键构建（主程序+安装程序）
├── requirements.txt
└── README.md
```

---

## 支持格式速查

粘贴以下任意格式开始下载：

| 格式 | 示例 |
|------|------|
| HTTP 直链 | `https://example.com/file.zip` |
| 裸BT Hash | `366ADAA52FB3639B17D73718DD5F9E3EE9477B40` |
| Magnet | `magnet:?xt=urn:btih:ABC...&dn=name` |
| ED2K | `ed2k://\|file\|name\|size\|hash\|/` |
| Thunder | `thunder://QUFodHRw...` |
| Metalink | `<metalink>...<file name="x"><url>http://...</url></file></metalink>` |
| 秒传JSON | `{"scriptVersion":"...","files":[{...}]}` |

---

## 许可

MIT License — 自由使用、修改、分发。
