"""
Aria2X - 秒传 JSON 解析器
解析百度网盘/阿里云盘等秒传 JSON，提取文件元信息用于后续下载。
支持格式: {"scriptVersion":"...","totalFilesCount":N,"totalSize":N,"formattedTotalSize":"...","files":[{...}]}
"""

import json
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MiaochuanFile:
    """秒传 JSON 中的单个文件"""
    index: int
    path: str
    size: int
    etag: str = ""
    md5: str = ""
    formatted_size: str = ""
    is_valid: bool = False

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def directory(self) -> str:
        return str(Path(self.path).parent)


@dataclass
class MiaochuanPackage:
    """秒传 JSON 包"""
    script_version: str = ""
    total_files: int = 0
    total_size: int = 0
    formatted_total_size: str = ""
    files: list = field(default_factory=list)
    raw_json: str = ""
    is_valid: bool = False
    error: str = ""

    @staticmethod
    def parse(text: str) -> "MiaochuanPackage":
        """解析秒传 JSON 文本"""
        result = MiaochuanPackage(raw_json=text)

        # 提取 JSON（可能被包裹在代码块或其他文本中）
        json_text = text.strip()
        # 尝试从 markdown 代码块中提取
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            json_text = m.group(1).strip()

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            result.error = f"JSON 解析错误: {e}"
            return result

        if not isinstance(data, dict):
            result.error = "不是有效的 JSON 对象"
            return result

        result.script_version = data.get("scriptVersion", "")
        result.total_files = int(data.get("totalFilesCount", 0))
        result.total_size = int(data.get("totalSize", 0))
        result.formatted_total_size = data.get("formattedTotalSize", "")

        raw_files = data.get("files", [])
        if not isinstance(raw_files, list):
            result.error = "files 字段不是数组"
            return result

        for i, f in enumerate(raw_files):
            mf = MiaochuanFile(
                index=i,
                path=f.get("path", ""),
                size=int(f.get("size", 0)),
                etag=f.get("etag", ""),
                md5=f.get("md5", f.get("md5s", "")),
                formatted_size=MiaochuanPackage._fmt(int(f.get("size", 0))),
            )
            mf.is_valid = bool(mf.path and mf.size > 0)
            result.files.append(mf)

        result.is_valid = result.total_files > 0 and len(result.files) > 0
        if not result.is_valid:
            result.error = "没有找到有效的文件条目"

        return result

    @staticmethod
    def _fmt(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def to_summary(self) -> dict:
        """转为 API 可序列化的摘要"""
        return {
            "script_version": self.script_version,
            "total_files": self.total_files,
            "total_size": self.total_size,
            "formatted_total_size": self.formatted_total_size or self._fmt(self.total_size),
            "file_count": len(self.files),
            "files": [{
                "index": f.index,
                "path": f.path,
                "filename": f.filename,
                "size": f.size,
                "formatted_size": f.formatted_size or self._fmt(f.size),
                "etag": f.etag,
                "md5": f.md5,
                "is_valid": f.is_valid,
            } for f in self.files],
            "is_valid": self.is_valid,
            "error": self.error,
        }
