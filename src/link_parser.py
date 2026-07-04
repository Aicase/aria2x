"""
Aria2X - 链接解析器
解析各种下载链接格式，提取元信息。
支持: HTTP/HTTPS/FTP, Magnet(含Hash自动补全), ED2K, Thunder, Torrent, Metalink
"""

import re
import base64
import hashlib
from urllib.parse import urlparse, unquote
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LinkType(Enum):
    HTTP = "http"
    HTTPS = "https"
    FTP = "ftp"
    MAGNET = "magnet"
    MAGNET_HASH = "magnet_hash"  # 裸 Hash，自动补全为 magnet
    ED2K = "ed2k"
    THUNDER = "thunder"
    TORRENT = "torrent"
    METALINK = "metalink"
    UNKNOWN = "unknown"


@dataclass
class ParsedLink:
    raw: str
    type: LinkType
    url: str = ""
    filename: str = ""
    size_hint: str = ""
    name_hint: str = ""
    hash_value: str = ""
    trackers: list = field(default_factory=list)
    is_valid: bool = False
    error: str = ""


def parse_link(text: str) -> ParsedLink:
    text = text.strip()
    if not text:
        return ParsedLink(raw=text, type=LinkType.UNKNOWN, error="空链接")

    # magnet:?xt=urn:btih:...
    if text.startswith("magnet:"):
        return _parse_magnet(text)

    # 裸 BT Hash (40位十六进制，自动补全)
    if re.match(r'^[a-fA-F0-9]{40}$', text):
        return _parse_magnet_hash(text)

    # 裸 BT Hash (32位十六进制)
    if re.match(r'^[a-fA-F0-9]{32}$', text):
        return _parse_magnet_hash(text)

    # ed2k://|file|...
    if text.startswith("ed2k://"):
        return _parse_ed2k(text)

    # thunder://...
    if text.startswith("thunder://"):
        return _parse_thunder(text)

    # metalink (XML)
    if text.strip().startswith("<metalink") or text.strip().startswith("<?xml"):
        return _parse_metalink(text)

    # .torrent
    if text.endswith(".torrent") and not text.startswith(("http://", "https://")):
        return ParsedLink(raw=text, type=LinkType.TORRENT, url=text,
                         filename=text.split("/")[-1].split("\\")[-1], is_valid=True)

    # HTTP/HTTPS/FTP
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https", "ftp"):
        return _parse_http(text, parsed)

    # 尝试加 https://
    if "." in text and not text.startswith(("http://", "https://")):
        text = "https://" + text
        return _parse_http(text, urlparse(text))

    return ParsedLink(raw=text, type=LinkType.UNKNOWN, error="无法识别的链接格式")


def parse_links(text: str) -> list[ParsedLink]:
    lines = text.strip().splitlines()
    results = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            results.append(parse_link(line))
    return results


def _parse_http(url: str, parsed) -> ParsedLink:
    filename = ""
    path = unquote(parsed.path)
    if path and "/" in path:
        filename = path.split("/")[-1]
    return ParsedLink(raw=url, type=LinkType(parsed.scheme), url=url,
                     filename=filename or "download", is_valid=True)


def _parse_magnet_hash(hash_str: str) -> ParsedLink:
    """裸 BT Hash → 自动补全为完整 magnet 链接"""
    magnet = f"magnet:?xt=urn:btih:{hash_str.upper()}"
    result = ParsedLink(
        raw=hash_str, type=LinkType.MAGNET_HASH,
        url=magnet, filename=hash_str[:12],
        hash_value=hash_str.upper(), is_valid=True,
    )
    return result


def _parse_magnet(text: str) -> ParsedLink:
    result = ParsedLink(raw=text, type=LinkType.MAGNET, url=text)
    xt = re.search(r'xt=urn:btih:([a-fA-F0-9]+)', text)
    if xt:
        result.hash_value = xt.group(1).upper()
    dn = re.search(r'dn=([^&]+)', text)
    if dn:
        result.name_hint = unquote(dn.group(1))
        result.filename = result.name_hint
    xl = re.search(r'xl=(\d+)', text)
    if xl:
        result.size_hint = _format_size(int(xl.group(1)))
    result.trackers = re.findall(r'tr=([^&]+)', text)
    result.is_valid = bool(result.hash_value)
    if not result.is_valid:
        result.error = "磁力链接格式无效（缺少 btih 哈希）"
    return result


def _parse_ed2k(text: str) -> ParsedLink:
    result = ParsedLink(raw=text, type=LinkType.ED2K, url=text)
    match = re.match(r'ed2k://\|file\|([^|]+)\|(\d+)\|([a-fA-F0-9]+)\|', text)
    if match:
        result.filename = match.group(1)
        result.size_hint = _format_size(int(match.group(2)))
        result.hash_value = match.group(3).upper()
        result.is_valid = True
    else:
        result.error = "ED2K 链接格式无效"
    return result


def _parse_thunder(text: str) -> ParsedLink:
    result = ParsedLink(raw=text, type=LinkType.THUNDER)
    encoded = text.replace("thunder://", "").rstrip("/")
    try:
        decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
        url_match = re.search(r'(?:AA|ZZ)?(https?://[^\s]+?)(?:AA|ZZ)?$', decoded)
        if url_match:
            result.url = url_match.group(1)
            inner = parse_link(result.url)
            result.filename = inner.filename
            result.url = inner.url
            result.is_valid = True
        else:
            result.error = "迅雷链接解码失败"
    except Exception as e:
        result.error = f"迅雷链接解码失败: {e}"
    return result


def _parse_metalink(text: str) -> ParsedLink:
    """解析 Metalink XML"""
    result = ParsedLink(raw=text, type=LinkType.METALINK, url=text)
    try:
        # 提取文件名
        fn = re.search(r'<file\s+name="([^"]+)"', text)
        if not fn:
            fn = re.search(r"<file\s+name='([^']+)'", text)
        if fn:
            result.filename = fn.group(1)

        # 提取大小
        sz = re.search(r'<size>(\d+)</size>', text)
        if sz:
            result.size_hint = _format_size(int(sz.group(1)))
            result.is_valid = True

        # 提取第一个 URL
        url = re.search(r'<url[^>]*>([^<]+)</url>', text)
        if url:
            result.url = url.group(1).strip()
            if not result.filename and result.url:
                result.filename = result.url.split("/")[-1]

        # 提取 hash
        h = re.search(r'<hash\s+type="([^"]+)"[^>]*>([^<]+)</hash>', text)
        if h:
            result.hash_value = h.group(2).strip()
        else:
            h = re.search(r"<hash\s+type='([^']+)'[^>]*>([^<]+)</hash>", text)
            if h:
                result.hash_value = h.group(2).strip()

        if not result.is_valid and not result.url:
            result.error = "Metalink 格式无效"

    except Exception as e:
        result.error = f"Metalink 解析失败: {e}"

    return result


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
