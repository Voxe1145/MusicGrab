# -*- coding: utf-8 -*-
"""
网易云音乐爬虫 - 图形界面版
============================
在命令行版核心（netease_crawler.py）之上提供图形界面：
搜索歌曲 -> 表格展示 -> 下载 / 看歌词 / 看评论 / 导出数据 / 批量下载歌单。

用法：
  python netease_crawler_gui.py
或直接运行打包后的 网易云音乐爬虫UI.exe

仅支持平台公开可试听/免费的歌曲下载，VIP 或版权受限歌曲会提示失败；
请遵守平台服务条款与版权法规，仅用于个人学习、试听等正当用途。
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import netease_crawler as nm

try:  # 高分屏清晰显示
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class NeteaseGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("网易云音乐爬虫")
        self.geometry("940x700")
        self.minsize(860, 600)
        self.q = queue.Queue()          # 工作线程 -> UI 线程消息队列
        self.songs = []                 # 当前搜索结果
        self.busy = False               # 是否有任务在跑

        self._build_ui()
        self.after(100, self._poll)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # 顶部搜索栏
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="关键词:").pack(side="left")
        self.kw_var = tk.StringVar()
        kw = ttk.Entry(top, textvariable=self.kw_var, width=26)
        kw.pack(side="left", padx=4)
        kw.bind("<Return>", lambda e: self.on_search())
        ttk.Label(top, text="数量:").pack(side="left")
        self.limit_var = tk.StringVar(value="30")
        ttk.Spinbox(top, from_=1, to=100, textvariable=self.limit_var,
                    width=5).pack(side="left", padx=4)
        self.search_btn = ttk.Button(top, text="搜  索", command=self.on_search)
        self.search_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(top, textvariable=self.status_var,
                  foreground="#555").pack(side="right")

        # 搜索结果表格
        mid = ttk.Frame(self, padding=(8, 0))
        mid.pack(fill="both", expand=True)
        cols = ("id", "name", "artists", "album", "duration", "pop")
        heads = {"id": "ID", "name": "歌曲", "artists": "歌手", "album": "专辑",
                 "duration": "时长", "pop": "热度"}
        widths = {"id": 90, "name": 210, "artists": 170, "album": 210,
                  "duration": 70, "pop": 60}
        self.tree = ttk.Treeview(mid, columns=cols, show="headings",
                                 selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.on_lyric())

        # 操作按钮
        btns = ttk.Frame(self, padding=(8, 6))
        btns.pack(fill="x")
        ttk.Button(btns, text="下载选中歌曲",
                   command=self.on_download).pack(side="left", padx=2)
        ttk.Button(btns, text="查看歌词",
                   command=self.on_lyric).pack(side="left", padx=2)
        ttk.Button(btns, text="查看评论",
                   command=self.on_comments).pack(side="left", padx=2)
        ttk.Separator(btns, orient="vertical").pack(side="left", padx=6, fill="y")
        ttk.Button(btns, text="导出 CSV",
                   command=lambda: self.on_export("csv")).pack(side="left", padx=2)
        ttk.Button(btns, text="导出 JSON",
                   command=lambda: self.on_export("json")).pack(side="left", padx=2)
        ttk.Button(btns, text="导出 XLSX",
                   command=lambda: self.on_export("xlsx")).pack(side="left", padx=2)
        ttk.Label(btns, text="（双击歌曲行可查看歌词）",
                  foreground="#888").pack(side="right")

        # 下载设置
        dl = ttk.LabelFrame(self, text="下载设置", padding=(8, 6))
        dl.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(dl, text="码率:").pack(side="left")
        self.br_var = tk.StringVar(value="320000")
        ttk.Combobox(dl, textvariable=self.br_var,
                     values=("320000", "192000", "128000"),
                     width=7, state="readonly").pack(side="left", padx=4)
        ttk.Label(dl, text="目录:").pack(side="left")
        self.dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "music"))
        ttk.Entry(dl, textvariable=self.dir_var, width=28).pack(side="left", padx=4)
        ttk.Button(dl, text="浏览", command=self._pick_dir).pack(side="left")
        ttk.Separator(dl, orient="vertical").pack(side="left", padx=10, fill="y")
        ttk.Label(dl, text="歌单ID:").pack(side="left")
        self.pid_var = tk.StringVar()
        ttk.Entry(dl, textvariable=self.pid_var, width=10).pack(side="left", padx=4)
        ttk.Label(dl, text="前N首(0=全部):").pack(side="left")
        self.plimit_var = tk.StringVar(value="0")
        ttk.Spinbox(dl, from_=0, to=1000, textvariable=self.plimit_var,
                    width=6).pack(side="left", padx=4)
        ttk.Button(dl, text="下载歌单", command=self.on_download_playlist).pack(side="left")

        # 日志区
        logf = ttk.LabelFrame(self, text="运行日志", padding=(8, 4))
        logf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_txt = tk.Text(logf, height=8, state="disabled", wrap="word",
                               font=("Consolas", 9))
        lvsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=lvsb.set)
        self.log_txt.pack(side="left", fill="both", expand=True)
        lvsb.pack(side="right", fill="y")
        self.log_txt.tag_configure("err", foreground="#c00")
        self.log_txt.tag_configure("ok", foreground="#070")

    # ------------------------------------------------------------- 工具方法
    def log(self, msg, tag=None):
        self.q.put(("log", msg, tag))

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or os.getcwd())
        if d:
            self.dir_var.set(d)

    def _selected_ids(self):
        ids = []
        for iid in self.tree.selection():
            vals = self.tree.item(iid, "values")
            if vals:
                try:
                    ids.append(int(vals[0]))
                except ValueError:
                    pass
        return ids

    def _fill_songs(self, songs):
        self.songs = songs
        self.tree.delete(*self.tree.get_children())
        for s in songs:
            dur = nm._fmt_duration(s["duration_ms"])
            self.tree.insert("", "end", values=(
                s["id"], s["name"], s["artists"], s["album"],
                dur, s["popularity"]))

    def _run(self, fn):
        """后台线程执行 fn，保持界面不卡死；任务进行中禁止并发。"""
        if self.busy:
            self.log("当前有任务在运行，请稍候...", "err")
            return
        self.busy = True
        self.search_btn.config(state="disabled")
        self.status_var.set("运行中...")
        threading.Thread(target=fn, daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, msg, tag = item
                    self.log_txt.config(state="normal")
                    self.log_txt.insert("end", msg + "\n", tag or ())
                    self.log_txt.see("end")
                    self.log_txt.config(state="disabled")
                elif kind == "songs":
                    _, songs, total = item
                    self._fill_songs(songs)
                    self.status_var.set(f"搜索完成：共 {total} 条")
                elif kind == "textwin":
                    _, title, text = item
                    self._show_text_window(title, text)
                elif kind == "err":
                    _, msg = item
                    self.log(msg, "err")
                    self.busy = False
                    self.search_btn.config(state="normal")
                    self.status_var.set("出错")
                elif kind == "done":
                    self.busy = False
                    self.search_btn.config(state="normal")
                    self.status_var.set("就绪")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _show_text_window(self, title, text):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("600x540")
        t = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 10))
        t.insert("1.0", text)
        t.config(state="disabled")
        sb = ttk.Scrollbar(win, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6)

    # ------------------------------------------------------------- 业务功能
    def on_search(self):
        kw = self.kw_var.get().strip()
        if not kw:
            self.log("请输入搜索关键词", "err")
            return
        try:
            limit = int(self.limit_var.get())
        except ValueError:
            limit = 30

        def work():
            try:
                self.log(f"正在搜索「{kw}」...")
                songs, total = nm.search_songs(kw, limit)
                self.q.put(("songs", songs, total))
                self.log(f"搜索完成：显示 {len(songs)} 条", "ok")
            except Exception as exc:
                self.q.put(("err", f"搜索失败: {exc}"))
            finally:
                self.q.put(("done",))

        self._run(work)

    def on_download(self):
        ids = self._selected_ids()
        if not ids:
            self.log("请先在结果列表中选择要下载的歌曲（可多选）", "err")
            return
        self._download_ids(ids, f"下载选中歌曲（{len(ids)} 首）")

    def on_download_playlist(self):
        try:
            pid = int(self.pid_var.get().strip())
        except ValueError:
            self.log("请输入歌单 ID", "err")
            return
        try:
            plimit = int(self.plimit_var.get())
        except ValueError:
            plimit = 0

        def work():
            try:
                self.log(f"正在获取歌单 {pid} ...")
                info, tracks = nm.playlist_detail(pid, "")
                self.log(f"歌单《{info['name']}》共 {info['trackCount']} 首，"
                         f"本次获取到 {len(tracks)} 首", "ok")
                ids = [t["id"] for t in tracks]
                if plimit and len(ids) > plimit:
                    ids = ids[:plimit]
                    self.log(f"按设置仅下载前 {plimit} 首")
                if not ids:
                    self.log("歌单为空或全部受版权限制", "err")
                    return
                self._do_download(ids, f"下载歌单《{info['name']}》")
            except Exception as exc:
                self.q.put(("err", f"获取歌单失败: {exc}"))
            finally:
                self.q.put(("done",))

        self._run(work)

    def _download_ids(self, ids, title):
        try:
            br = int(self.br_var.get())
        except ValueError:
            br = 320000
        out = self.dir_var.get().strip() or "music"

        def work():
            try:
                self.q.put(("log", f"{title}：共 {len(ids)} 首", None))
                ok = fail = 0
                for i, sid in enumerate(ids, 1):
                    self.q.put(("log", f"[{i}/{len(ids)}] 歌曲 {sid} ...", None))
                    try:
                        nm.download_song(
                            sid, br, out, "",
                            progress=None,
                            log=lambda m, s=sid: self.q.put(
                                ("log", f"    {m}", "ok")),
                        )
                        ok += 1
                    except Exception as exc:
                        self.q.put(("log", f"    跳过: {exc}", "err"))
                        fail += 1
                self.q.put(("log", f"下载完成：成功 {ok} 首，失败/跳过 {fail} 首",
                            None))
            except Exception as exc:
                self.q.put(("err", f"下载出错: {exc}"))
            finally:
                self.q.put(("done",))

        self._run(work)

    def on_lyric(self):
        ids = self._selected_ids()
        if not ids:
            self.log("请先选择一首歌曲（双击也可触发）", "err")
            return
        sid = ids[0]

        def work():
            try:
                lrc, tly = nm.fetch_lyric(sid, "")
                lines = nm.parse_lrc(lrc)
                text = "\n".join(
                    f"[{int(t // 60):02d}:{t % 60:05.2f}] {tx}"
                    for t, tx in lines)
                if not text:
                    text = "（无歌词，可能受版权限制，可用 --cookie 后重试）"
                if tly.strip():
                    text += "\n\n---------- 翻译 ----------\n" + tly
                self.q.put(("textwin", f"歌词 - 歌曲 {sid}", text))
            except Exception as exc:
                self.q.put(("err", f"获取歌词失败: {exc}"))
            finally:
                self.q.put(("done",))

        self._run(work)

    def on_comments(self):
        ids = self._selected_ids()
        if not ids:
            self.log("请先选择一首歌曲", "err")
            return
        sid = ids[0]

        def work():
            try:
                comments, total = nm.fetch_comments(sid, 30, 0, "")
                lines = [
                    f"{i}. {c['user']}   赞 {c['likes']}   {c['time']}\n"
                    f"   {c['content']}"
                    for i, c in enumerate(comments, 1)
                ]
                text = (f"歌曲 {sid} 评论共 {total} 条，显示前 {len(comments)} 条：\n\n"
                        + "\n\n".join(lines))
                self.q.put(("textwin", f"评论 - 歌曲 {sid}", text))
            except Exception as exc:
                self.q.put(("err", f"获取评论失败: {exc}"))
            finally:
                self.q.put(("done",))

        self._run(work)

    def on_export(self, fmt):
        if not self.songs:
            self.log("当前没有可导出的搜索结果（请先搜索）", "err")
            return
        out = os.path.join(os.getcwd(), "output")
        nm.ensure_dir(out)
        headers = ["id", "name", "artists", "album", "duration_ms", "popularity"]
        rows = [[s[h] for h in headers] for s in self.songs]
        try:
            path = os.path.join(out, f"search_results.{fmt}")
            if fmt == "csv":
                nm.write_csv(path, headers, rows)
            elif fmt == "json":
                nm.write_json(path, [dict(zip(headers, r)) for r in rows])
            else:
                nm.write_xlsx(path, headers, rows)
            self.log(f"已导出 {len(rows)} 条: {path}", "ok")
        except Exception as exc:
            self.log(f"导出失败: {exc}", "err")


def main():
    if "--smoke" in sys.argv:
        # 自检模式：短暂打开窗口后退出，并写入标记文件（供打包后验证）
        app = NeteaseGui()
        app.after(1200, app.destroy)
        app.mainloop()
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        with open(os.path.join(base, "smoke_ok.txt"), "w", encoding="utf-8") as f:
            f.write("ok")
        sys.exit(0)
    app = NeteaseGui()
    app.mainloop()


if __name__ == "__main__":
    main()
