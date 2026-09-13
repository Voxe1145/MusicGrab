# 网易云音乐爬虫 (Netease Cloud Music Crawler)

一个命令行 + 图形界面网易云音乐爬虫：支持搜索歌曲、获取详情 / 歌词 / 评论 / 歌单，**并可直接下载歌曲 mp3**（单曲 / 多曲 / 整张歌单），数据可导出 CSV / JSON / Excel，已打包为 Windows 单文件 exe（无需安装 Python 即可运行）。

> 下载仅支持平台公开可试听 / 免费的歌曲，VIP 或版权受限歌曲会提示失败；
>
> 请遵守平台服务条款与版权法规，仅用于个人学习、试听等正当用途。

## 两种使用方式

### 1. 图形界面（推荐，双击即用）

双击 `网易云音乐爬虫UI.exe` 即可打开界面：

* 顶部输入关键词、设置数量，点击「搜索」——结果展示在表格中

* 选中歌曲后：**下载选中歌曲** / **查看歌词**（双击行）/ **查看评论**

* **导出 CSV / JSON / XLSX**：一键导出当前搜索结果到 `output\` 目录

* 底部下载设置：选择码率（320000 / 192000 / 128000）、下载目录（可浏览选择）

* **下载歌单**：输入歌单 ID 和「前N首」（0=全部），一键批量下载

* 所有网络请求在后台线程执行，界面不卡死；运行日志实时显示在底部

### 2. 命令行

```
网易云音乐爬虫.exe 命令 [参数]
```

## 快速开始



```
网易云音乐爬虫.exe 命令 \[参数]
```

## 命令一览



| 命令         | 作用         | 示例                                         |
| ---------- | ---------- | ------------------------------------------ |
| `search`   | 按关键词搜索歌曲   | `网易云音乐爬虫.exe search 周杰伦 --limit 20`        |
| `song`     | 获取单曲详情     | `网易云音乐爬虫.exe song 186016`                  |
| `lyric`    | 获取歌词 (LRC) | `网易云音乐爬虫.exe lyric 186016`                 |
| `comments` | 获取单曲热门评论   | `网易云音乐爬虫.exe comments 186016 --limit 50`   |
| `playlist` | 获取歌单详情与歌曲  | `网易云音乐爬虫.exe playlist 3778678 --limit 100` |
| `download` | 下载歌曲 mp3      | `网易云音乐爬虫.exe download 186016 210049`       |

## 下载功能

```
# 下载单曲（文件名自动为“歌手 - 歌名.mp3”）
网易云音乐爬虫.exe download 186016

# 一次下载多首
网易云音乐爬虫.exe download 186016 210049 287398

# 指定码率（128000 标准 / 192000 高品 / 320000 无损级，默认 320000）
网易云音乐爬虫.exe download 287398 --bitrate 320000

# 批量下载整张歌单（可加 --limit 限制数量）
网易云音乐爬虫.exe download --playlist 3778678 --limit 20

# 指定下载目录（默认 music\）
网易云音乐爬虫.exe download 287398 --output D:\音乐
```

下载说明：

* 下载前自动获取歌曲信息，保存为 `歌手 - 歌名.mp3`

* **VIP / 版权受限歌曲**（如部分热门歌手）无法获取下载地址，会显示跳过原因，不影响后续歌曲

* 批量下载每首歌之间自动间隔 1 秒，避免触发风控

## 通用参数（放在子命令后）



| 参数                | 说明                                                     |
| ----------------- | ------------------------------------------------------ |
| `--output DIR`    | 导出 / 下载目录（默认 `output`；download 默认 `music`）        |
| `--export TYPE`   | 导出格式：`csv` / `json` / `xlsx` / `all` / `none`，默认 `all`（download 无效） |
| `--cookie COOKIE` | 可选，传入登录后的 Cookie（部分受限歌曲的歌词 / 评论需要）                     |
| `--limit N`       | 返回数量（search/comments 默认 20，playlist/download 默认全部） |
| `--offset N`      | 分页偏移（search/comments）                                  |
| `--bitrate N`     | 下载码率（仅 download）：128000 / 192000 / 320000            |

## 示例输出



```
网易云音乐爬虫.exe search 周杰伦 --limit 5 --export none

搜索“周杰伦”：共 278 条结果，显示前 5 条

ID         | 歌曲       | 歌手         | 专辑    | 时长 | 热度

\-----------+------------+--------------+---------+------+-----

186016     | 晴天       | 周杰伦       | 叶惠美   | 4:29 | 100.0

...
```

## 导出文件

默认导出到 `output/` 目录：



* `search_关键词.csv / .json / .xlsx` — 搜索结果

* `song_歌曲ID.csv / .json / .xlsx` — 单曲详情

* `lyric_歌曲ID.lrc` — 标准 LRC 歌词；`lyric_歌曲ID_translation.txt` — 翻译歌词

* `comments_歌曲ID.csv / .json / .xlsx` — 评论（用户、内容、点赞数、时间）

* `playlist_歌单ID.csv / .json / .xlsx` + `playlist_歌单ID_info.json` — 歌单歌曲与歌单信息

CSV 使用 UTF-8 with BOM 编码，Excel 可直接打开不乱码。

## 如何找歌曲 ID

网页版打开歌曲 / 歌单页面，URL 中的数字即为 ID：

`https://music.163.com/#/song?id=186016` → ID 为 `186016`

## 源码运行（开发用）



```
pip install -r requirements.txt

python netease\_crawler.py search 周杰伦 --limit 20
```

## 重新打包 exe



```
pip install pyinstaller

pyinstaller -F -n 网易云音乐爬虫 netease\_crawler.py --clean --noconfirm

pyinstaller -F -w -n 网易云音乐爬虫UI netease\_crawler\_gui.py --clean --noconfirm
```

产物位于 `dist/网易云音乐爬虫.exe`（命令行版）与 `dist/网易云音乐爬虫UI.exe`（图形界面版）。

## 常见问题



* **接口被风控（错误码 -460/403）**：请求过于频繁导致，稍等几分钟重试；或使用 `--cookie` 传入登录 Cookie。

* **某首歌歌词 / 评论为空**：部分版权受限内容需要登录才能获取，传入 Cookie 后重试。

* **杀毒软件误报**：PyInstaller 单文件 exe 偶尔会被误报，添加信任即可；也可直接用源码运行。