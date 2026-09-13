# -*- coding: utf-8 -*-
"""
网易云音乐爬虫 (Netease Cloud Music Crawler)
============================================

功能：
  search    按关键词搜索歌曲
  song      获取单曲详情
  lyric     获取歌词 (LRC)
  comments  获取单曲热门评论
  playlist  获取歌单详情及其歌曲列表
  download  下载歌曲音频 (mp3)，支持单曲/多曲/整张歌单

用法示例：
  netease_crawler.exe search 周杰伦 --limit 20
  netease_crawler.exe song 186016
  netease_crawler.exe lyric 186016
  netease_crawler.exe comments 186016 --limit 50
  netease_crawler.exe playlist 3778678
  netease_crawler.exe download 186016 210049 --bitrate 320000
  netease_crawler.exe download --playlist 3778678 --limit 20

说明：
  - 下载仅支持平台公开可试听/免费的歌曲，VIP 或版权受限歌曲会提示失败。
  - 请遵守平台服务条款与版权法规，仅用于个人学习、试听等正当用途。
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("缺少依赖 requests，请先执行: pip install requests")
    sys.exit(1)

BASE_URL = "https://music.163.com/api"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Accept": "application/json, text/plain, */*",
}

DEFAULT_COOKIE = "os=pc; appver=2.9.7; NMTID=00O2Z2KkQ0mW6p_3QnR0Rz0Tz000001"

LRC_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


# ---------------------------------------------------------------------------
# 网络层
# ---------------------------------------------------------------------------
def api_get(path, params, cookie="", retries=3):
    """请求网易云公开接口，失败自动重试。"""
    url = BASE_URL + path
    headers = dict(HEADERS)
    headers["Cookie"] = cookie or DEFAULT_COOKIE
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            data = resp.json()
            code = data.get("code", 200)
            if code == 200:
                return data
            if code == -460 or code == 403:
                raise RuntimeError("接口被风控拦截(请稍后重试或更换 Cookie)")
            raise RuntimeError(f"接口返回错误码 {code}")
        except (requests.RequestException, ValueError) as exc:
            last_err = exc
        except RuntimeError as exc:
            last_err = exc
        if attempt < retries - 1:
            time.sleep(1 + attempt)
    raise RuntimeError(f"请求失败: {path} -> {last_err}")


# ---------------------------------------------------------------------------
# 数据层
# ---------------------------------------------------------------------------
def search_songs(keyword, limit=20, offset=0, cookie=""):
    data = api_get(
        "/search/get/web",
        {"s": keyword, "type": 1, "limit": limit, "offset": offset},
        cookie,
    )
    result = data.get("result") or {}
    songs = [
        _normalize_song(s)
        for s in (result.get("songs") or [])
    ]
    return songs, result.get("songCount", 0)


def _normalize_song(s):
    # 搜索接口返回 artists/album/duration/popularity，详情接口返回 ar/al/dt/pop
    ar = s.get("ar") or s.get("artists") or []
    artists = " / ".join(a.get("name", "") for a in ar)
    al = s.get("al") or s.get("album") or {}
    album = al.get("name", "")
    return {
        "id": s.get("id", ""),
        "name": s.get("name", ""),
        "artists": artists,
        "album": album,
        "duration_ms": s.get("dt") or s.get("duration") or 0,
        "popularity": s.get("pop") or s.get("popularity") or 0,
    }


def song_detail(song_id, cookie=""):
    data = api_get("/song/detail", {"id": song_id, "ids": f"[{song_id}]"}, cookie)
    songs = data.get("songs") or []
    if not songs:
        raise RuntimeError(f"未找到歌曲: {song_id}")
    s = songs[0]
    info = _normalize_song(s)
    pub = s.get("publishTime") or 0
    info["publish_time"] = (
        datetime.fromtimestamp(pub / 1000).strftime("%Y-%m-%d") if pub else ""
    )
    return info


def fetch_lyric(song_id, cookie=""):
    data = api_get(
        "/song/lyric", {"id": song_id, "lv": 1, "kv": 1, "tv": -1}, cookie
    )
    lrc = (data.get("lrc") or {}).get("lyric") or ""
    tlyric = (data.get("tlyric") or {}).get("lyric") or ""
    return lrc, tlyric


def parse_lrc(text):
    """把 LRC 文本解析成 [(秒, 歌词)] 列表，按时间排序。"""
    lines = []
    for line in text.splitlines():
        tags = LRC_RE.findall(line)
        if not tags:
            continue
        content = LRC_RE.sub("", line).strip()
        for mm, ss, ms in tags:
            sec = int(mm) * 60 + int(ss)
            if ms:
                sec += int(ms.ljust(3, "0")[:3]) / 1000.0
            lines.append((round(sec, 3), content))
    lines.sort(key=lambda x: x[0])
    return lines


def fetch_comments(song_id, limit=20, offset=0, cookie=""):
    data = api_get(
        f"/v1/resource/comments/R_SO_4_{song_id}",
        {"limit": limit, "offset": offset},
        cookie,
    )
    comments = []
    for c in data.get("comments") or []:
        user = c.get("user") or {}
        ts = c.get("time") or 0
        comments.append({
            "user": user.get("nickname", ""),
            "content": c.get("content", "").replace("\n", " "),
            "likes": c.get("likedCount", 0),
            "time": (
                datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if ts else ""
            ),
        })
    return comments, data.get("total", 0)


def playlist_detail(pid, cookie=""):
    data = api_get("/v6/playlist/detail", {"id": pid}, cookie)
    pl = data.get("playlist") or {}
    if not pl:
        raise RuntimeError(f"未找到歌单: {pid}")
    info = {
        "id": pid,
        "name": pl.get("name", ""),
        "creator": (pl.get("creator") or {}).get("nickname", ""),
        "trackCount": pl.get("trackCount", 0),
        "playCount": pl.get("playCount", 0),
        "description": (pl.get("description") or "").replace("\n", " ")[:200],
    }
    tracks = [_normalize_song(t) for t in (pl.get("tracks") or [])]
    return info, tracks


def get_song_url(song_id, br=320000, cookie=""):
    """获取歌曲播放地址；版权/VIP 受限歌曲返回 None。"""
    data = api_get(
        "/song/enhance/player/url",
        {"ids": f"[{song_id}]", "br": br},
        cookie,
    )
    items = data.get("data") or []
    if not items:
        return None
    return items[0].get("url") or None


def sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return name or "unknown"


def _console_progress(done, total):
    pct = done * 100 // total if total else 100
    print(
        f"\r  下载中 {done / 1048576:.1f}/{total / 1048576:.1f} MB ({pct}%)",
        end="", flush=True,
    )


def download_song(song_id, br=320000, out_dir="music", cookie="",
                  progress=_console_progress, log=print):
    """下载歌曲。
    progress(done, total)：进度回调（传 None 关闭）；
    log(msg)：结果行输出。GUI 可传自定义回调。
    """
    info = song_detail(song_id, cookie)
    url = get_song_url(song_id, br, cookie)
    if not url:
        raise RuntimeError(
            f"《{info['name']}》(ID {song_id}) 受版权/VIP 限制，无法获取下载地址"
            "（可尝试 --cookie 登录后重试）"
        )
    ensure_dir(out_dir)
    ext = os.path.splitext(urlparse(url).path)[1] or ".mp3"
    fname = f"{sanitize_filename(info['artists'])} - {sanitize_filename(info['name'])}{ext}"
    fpath = os.path.join(out_dir, fname)
    headers = {k: v for k, v in HEADERS.items() if k != "Referer"}
    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length") or 0)
    done = 0
    last_print = 0.0
    with open(fpath, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            if not chunk:
                continue
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if progress and total and now - last_print >= 0.5:
                last_print = now
                progress(done, total)
    size_mb = done / 1048576
    if progress is not None and sys.stdout is not None:
        print()  # 结束 \r 进度行，换行（窗口模式下 stdout 为 None 则跳过）
    if log:
        log(f"  已下载: {fpath}（{size_mb:.1f} MB，{br // 1000}kbps）")
    return fpath


# ---------------------------------------------------------------------------
# 展示层
# ---------------------------------------------------------------------------
def _dw(s):
    """显示宽度（中文按 2 列计算）。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def _pad(s, w):
    s = str(s)
    return s + " " * max(0, w - _dw(s))


def print_songs(songs):
    if not songs:
        print("（无结果）")
        return
    headers = ["ID", "歌曲", "歌手", "专辑", "时长", "热度"]
    rows = [
        [str(s["id"]), s["name"], s["artists"], s["album"],
         _fmt_duration(s["duration_ms"]), str(s["popularity"])]
        for s in songs
    ]
    widths = [max(_dw(h), *( _dw(r[i]) for r in rows )) for i, h in enumerate(headers)]
    print(" | ".join(_pad(h, widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(_pad(r[i], widths[i]) for i in range(len(headers))))


def print_comments(comments):
    if not comments:
        print("（无评论）")
        return
    for i, c in enumerate(comments, 1):
        print(f"[{i}] {c['user']}  赞{c['likes']}  {c['time']}")
        print(f"    {c['content']}")


def print_lyrics(lines, max_lines=40):
    if not lines:
        print("（无歌词）")
        return
    for t, text in lines[:max_lines]:
        mm = int(t // 60)
        ss = t - mm * 60
        print(f"[{mm:02d}:{ss:05.2f}] {text}")
    if len(lines) > max_lines:
        print(f"...（共 {len(lines)} 行，完整内容已保存到文件）")


def _fmt_duration(ms):
    if not ms:
        return ""
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# 导出层
# ---------------------------------------------------------------------------
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def write_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_xlsx(path, headers, rows):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise RuntimeError("缺少 openpyxl，无法导出 xlsx（可改用 --export csv/json）")
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def export_table(out_dir, name, headers, rows, mode):
    if mode in ("none",):
        return
    kinds = ["csv", "json", "xlsx"] if mode == "all" else [mode]
    for kind in kinds:
        path = os.path.join(out_dir, f"{name}.{kind}")
        if kind == "csv":
            write_csv(path, headers, rows)
        elif kind == "json":
            write_json(path, [dict(zip(headers, r)) for r in rows])
        else:
            write_xlsx(path, headers, rows)
        print(f"  已导出: {path}")


# ---------------------------------------------------------------------------
# 命令分发
# ---------------------------------------------------------------------------
def cmd_search(args):
    songs, total = search_songs(args.keyword, args.limit, args.offset, args.cookie)
    print(f"搜索“{args.keyword}”：共 {total} 条结果，显示前 {len(songs)} 条\n")
    print_songs(songs)
    if songs and args.export != "none":
        headers = ["id", "name", "artists", "album", "duration_ms", "popularity"]
        rows = [[s[h] for h in headers] for s in songs]
        ensure_dir(args.output)
        export_table(args.output, f"search_{args.keyword}", headers, rows, args.export)


def cmd_song(args):
    info = song_detail(args.id, args.cookie)
    print("单曲详情：")
    for k, v in info.items():
        if k == "duration_ms":
            v = _fmt_duration(v)
        print(f"  {k}: {v}")
    if args.export != "none":
        ensure_dir(args.output)
        export_table(args.output, f"song_{args.id}",
                     list(info.keys()), [list(info.values())], args.export)


def cmd_lyric(args):
    lrc, tlyric = fetch_lyric(args.id, args.cookie)
    lines = parse_lrc(lrc)
    print(f"歌词（{len(lines)} 行）：\n")
    print_lyrics(lines)
    if not lines:
        return
    ensure_dir(args.output)
    lrc_path = os.path.join(args.output, f"lyric_{args.id}.lrc")
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lrc)
    print(f"  已导出: {lrc_path}")
    if tlyric:
        tlyric_path = os.path.join(args.output, f"lyric_{args.id}_translation.txt")
        with open(tlyric_path, "w", encoding="utf-8") as f:
            f.write(tlyric)
        print(f"  已导出: {tlyric_path}")


def cmd_comments(args):
    comments, total = fetch_comments(args.id, args.limit, args.offset, args.cookie)
    print(f"歌曲 {args.id} 评论共 {total} 条，显示 {len(comments)} 条\n")
    print_comments(comments)
    if comments and args.export != "none":
        headers = ["user", "content", "likes", "time"]
        rows = [[c[h] for h in headers] for c in comments]
        ensure_dir(args.output)
        export_table(args.output, f"comments_{args.id}", headers, rows, args.export)


def cmd_playlist(args):
    info, tracks = playlist_detail(args.id, args.cookie)
    if args.limit and len(tracks) > args.limit:
        tracks = tracks[: args.limit]
    print(f"歌单：{info['name']}（创建者 {info['creator']}，共 {info['trackCount']} 首）")
    if info["description"]:
        print(f"简介：{info['description']}")
    print(f"本次获取到 {len(tracks)} 首\n")
    print_songs(tracks)
    if tracks and args.export != "none":
        headers = ["id", "name", "artists", "album", "duration_ms", "popularity"]
        rows = [[t[h] for h in headers] for t in tracks]
        ensure_dir(args.output)
        export_table(args.output, f"playlist_{args.id}", headers, rows, args.export)
        write_json(os.path.join(args.output, f"playlist_{args.id}_info.json"), info)
        print(f"  已导出: {os.path.join(args.output, f'playlist_{args.id}_info.json')}")


def cmd_download(args):
    ids = list(args.ids or [])
    if args.playlist:
        info, tracks = playlist_detail(args.playlist, args.cookie)
        if args.limit and len(tracks) > args.limit:
            tracks = tracks[: args.limit]
        print(f"从歌单《{info['name']}》批量下载 {len(tracks)} 首...")
        ids.extend(t["id"] for t in tracks)
    if not ids:
        raise RuntimeError("请提供歌曲 ID，或使用 --playlist 指定歌单 ID")
    ok = fail = 0
    for i, sid in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] 歌曲 {sid}:")
        try:
            download_song(sid, args.bitrate, args.output, args.cookie)
            ok += 1
        except RuntimeError as exc:
            print(f"  跳过: {exc}")
            fail += 1
        if i < len(ids):
            time.sleep(1)
    print(f"\n完成: 成功 {ok} 首，失败/跳过 {fail} 首")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="netease_crawler",
        description="网易云音乐爬虫：搜索歌曲 / 歌曲详情 / 歌词 / 评论 / 歌单",
        epilog="示例: netease_crawler.exe search 周杰伦 --limit 20",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="命令", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output", default="output", help="导出目录（默认 output）")
    common.add_argument(
        "--export", default="all", choices=["csv", "json", "xlsx", "all", "none"],
        help="导出格式（默认 all）",
    )
    common.add_argument("--cookie", default="", help="可选：登录后的 Cookie")

    p = sub.add_parser("search", parents=[common], help="按关键词搜索歌曲")
    p.add_argument("keyword", help="搜索关键词")
    p.add_argument("--limit", type=int, default=20, help="返回数量（默认 20）")
    p.add_argument("--offset", type=int, default=0, help="偏移（默认 0）")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("song", parents=[common], help="获取单曲详情")
    p.add_argument("id", type=int, help="歌曲 ID")
    p.set_defaults(func=cmd_song)

    p = sub.add_parser("lyric", parents=[common], help="获取歌词 LRC")
    p.add_argument("id", type=int, help="歌曲 ID")
    p.set_defaults(func=cmd_lyric)

    p = sub.add_parser("comments", parents=[common], help="获取单曲评论")
    p.add_argument("id", type=int, help="歌曲 ID")
    p.add_argument("--limit", type=int, default=20, help="返回数量（默认 20）")
    p.add_argument("--offset", type=int, default=0, help="偏移（默认 0）")
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser("playlist", parents=[common], help="获取歌单详情与歌曲")
    p.add_argument("id", type=int, help="歌单 ID")
    p.add_argument("--limit", type=int, default=0,
                   help="最多输出/导出前 N 首（默认全部）")
    p.set_defaults(func=cmd_playlist)

    p = sub.add_parser(
        "download", help="下载歌曲（单曲或歌单，mp3）")
    p.add_argument("ids", type=int, nargs="*", help="一个或多个歌曲 ID")
    p.add_argument("--playlist", type=int, default=0, help="歌单 ID，批量下载歌单内歌曲")
    p.add_argument("--limit", type=int, default=0,
                   help="批量下载前 N 首（配合 --playlist，默认全部）")
    p.add_argument("--bitrate", type=int, default=320000,
                   choices=[128000, 192000, 320000],
                   help="码率：128000 标准 / 192000 高品 / 320000 无损级（默认 320000）")
    p.add_argument("--output", default="music", help="下载目录（默认 music）")
    p.add_argument("--cookie", default="", help="可选：登录后的 Cookie")
    p.set_defaults(func=cmd_download)

    return parser


def _setup_stdio():
    """管道/重定向输出时强制 UTF-8，避免 PowerShell、文件重定向中文乱码；
    在真实控制台(TTY)中保持系统默认编码，cmd 下正常显示中文。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            if not stream.isatty() and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(130)


if __name__ == "__main__":
    main()
