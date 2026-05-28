"""
B站 UP主「沙雕Mars」《关于我转生变成流汗黄豆》系列视频采集 & 分析脚本

数据源：UP主的B站合集频道 (channel_id=28754)，55集一次性拉取
功能：
  1. 从合集频道获取全部 55 集视频
  2. 自动分季/分篇章
  3. 每集获取详情、弹幕、弹幕密度统计、热门评论
  4. 输出 JSON + Markdown 大纲
  5. --analyze 分析已采集数据

使用：
  pip install bilibili-api-python python-dotenv yt-dlp
  python bili_scraper.py              # 采集元数据 + 弹幕 + 评论
  python bili_scraper.py --analyze    # 分析已采集数据
"""

import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from bilibili_api import sync, user, video, comment
from bilibili_api.comment import CommentResourceType

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

UP_MID = 43739579
CHANNEL_ID = 28754                     # 《流汗黄豆》合集频道的 ID
OUTPUT_DIR = Path("output")
OUTPUT_JSON = OUTPUT_DIR / "liuhan_data.json"
OUTPUT_MD = OUTPUT_DIR / "liuhan_outline.md"

# 第二季及以后的标题关键词（其余自动归为第一季）
SEASON_RULES = [
    ("大专|生化|丧尸|厂长|雌小豆|西瓜条|求生之路", "第二季"),
    ("狼人杀", "第三季·狼人杀篇"),
    ("马之勇者|钢琴家", "外传·马之勇者"),
]

# 第一季篇章规则（按在视频列表中的序号区间划分）
ARC_RULES = [
    (range(1, 3),   "启程篇"),
    (range(3, 9),   "芜湖港篇"),
    (range(9, 17),  "歪比巴卜篇"),
    (range(17, 20), "捉鬼篇"),
    (range(20, 28), "偶像篇"),
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def classify_season(title: str) -> str:
    for keyword, season_name in SEASON_RULES:
        if re.search(keyword, title):
            return season_name
    return "第一季"


def classify_arc(index: int, season: str) -> str:
    if season != "第一季":
        return ""
    for rng, arc_name in ARC_RULES:
        if index in rng:
            return arc_name
    return ""


def ts_to_str(ts: int) -> str:
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


# ---------------------------------------------------------------------------
# 数据采集
# ---------------------------------------------------------------------------

def fetch_channel_videos(channel_id: int = CHANNEL_ID) -> list:
    """从合集频道获取全部视频"""
    u = user.User(UP_MID)
    channels = sync(u.get_channels())

    for ch in channels:
        meta = sync(ch.get_meta())
        if ch.id_ == channel_id:
            print(f"  合集频道：{meta.get('name', '?')}（{meta.get('total', 0)} 集）")
            resp = sync(ch.get_videos(ps=100))
            archives = resp.get("archives", [])
            print(f"  获取到 {len(archives)} 个视频")
            return archives

    print("  [ERROR] 未找到目标合集频道")
    return []


def fetch_video_detail(bvid: str) -> dict | None:
    v = video.Video(bvid=bvid)
    try:
        return sync(v.get_info())
    except Exception as e:
        print(f"  [WARN] 获取 {bvid} 详情失败: {e}")
        return None


def fetch_danmaku(bvid: str, cid: int, max_dms: int = 3000) -> list:
    """返回 [(时间秒, 文本), ...]"""
    v = video.Video(bvid=bvid)
    dms = []
    try:
        page = 0
        while True:
            batch = sync(v.get_danmakus(page_index=page, cid=cid))
            if not batch:
                break
            for dm in batch:
                dms.append((dm.dm_time, dm.text))
                if len(dms) >= max_dms:
                    break
            page += 1
            if len(dms) >= max_dms:
                break
            time.sleep(0.3)
    except Exception as e:
        print(f"  [WARN] 弹幕获取失败: {e}")
    return dms


def fetch_comments(oid: int) -> list:
    try:
        resp = sync(comment.get_comments(
            oid=oid,
            type_=CommentResourceType.VIDEO,
            page_index=1,
        ))
        replies = resp.get("replies") or []
        return [
            {
                "user": r.get("member", {}).get("uname", ""),
                "content": r.get("content", {}).get("message", ""),
                "likes": r.get("like", 0),
            }
            for r in replies[:20]
        ]
    except Exception as e:
        print(f"  [WARN] 评论获取失败: {e}")
        return []


# ---------------------------------------------------------------------------
# 数据整理
# ---------------------------------------------------------------------------

def organize_series(archives: list) -> dict:
    """按发布时间排序 + 按季度/篇章分组"""
    archives.sort(key=lambda v: v.get("pubdate", 0) or v.get("ctime", 0))

    seasons = {}
    second_season_idx = 0   # 第二季之后的集数，用于独立编号

    for idx, v in enumerate(archives):
        title = v.get("title", "")
        season = classify_season(title)
        arc = classify_arc(idx, season)

        if season not in seasons:
            seasons[season] = []

        if season == "第一季":
            ep_num = idx + 1
        else:
            second_season_idx += 1
            ep_num = second_season_idx

        seasons[season].append({
            "index": ep_num,
            "title": title,
            "bvid": v.get("bvid", ""),
            "aid": v.get("aid", 0),
            "cid": v.get("cid", 0),
            "created": ts_to_str(v.get("pubdate", 0) or v.get("ctime", 0)),
            "duration": v.get("duration", ""),
            "play": v.get("stat", {}).get("view", 0) if isinstance(v.get("stat"), dict) else v.get("play", 0),
            "danmaku_count": v.get("stat", {}).get("danmaku", 0) if isinstance(v.get("stat"), dict) else 0,
            "description": v.get("desc", ""),
            "arc": arc,
        })

    return seasons


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def generate_markdown(seasons: dict) -> str:
    lines = [
        "# 《关于我转生变成流汗黄豆这档事》采集结果",
        "",
        f"> 自动采集时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> UP主 UID：{UP_MID} | 合集频道 ID：{CHANNEL_ID}",
        "",
    ]

    total_eps = 0
    season_order = ["第一季", "第二季", "第三季·狼人杀篇", "外传·马之勇者"]

    for season_name in season_order:
        episodes = seasons.get(season_name, [])
        if not episodes:
            continue
        total_eps += len(episodes)
        lines.append(f"## {season_name}（{len(episodes)} 集）")
        lines.append("")

        current_arc = ""
        for ep in episodes:
            if ep["arc"] and ep["arc"] != current_arc:
                current_arc = ep["arc"]
                lines.append(f"### {current_arc}")
                lines.append("")

            lines.append(f"### 第 {ep['index']} 集 · {ep['title']}")
            lines.append("")
            lines.append(f"- **BV号**：`{ep['bvid']}`")
            lines.append(f"- **发布时间**：{ep['created']}")
            lines.append(f"- **时长**：{ep['duration']}")
            lines.append(f"- **播放量**：{ep.get('play', 0):,}")
            lines.append(f"- **弹幕数**：{ep.get('danmaku_count', 0):,}")
            lines.append(f"- **点赞**：{ep.get('like', 0):,}")
            lines.append("")

            if ep.get("description"):
                desc = ep["description"].strip()[:300]
                if desc:
                    lines.append(f"> {desc}")
                    lines.append("")

            if ep.get("danmaku_highlights"):
                lines.append("**弹幕高能时刻**：")
                for ts, density in ep.get("danmaku_highlights", [])[:5]:
                    lines.append(f"  - `{ts}s` 弹幕密度 {density}")
                lines.append("")

            if ep.get("top_comments"):
                lines.append("**热门评论**：")
                for c in ep["top_comments"][:3]:
                    text = c["content"][:100]
                    lines.append(f"  - **{c['user']}**：{text}（{c['likes']}赞）")
                lines.append("")

            lines.append("---")
            lines.append("")

    lines.insert(2, f"**总计 {total_eps} 集** | 共 {len(seasons)} 个季度")
    lines.insert(3, "")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(download_videos: bool = False):
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print(f"B站视频采集 — 《关于我转生变成流汗黄豆这档事》")
    print(f"合集频道 ID={CHANNEL_ID}")
    print("=" * 60)

    # Step 1: 从合集频道获取全部视频
    print("\n[1/4] 从合集频道获取视频列表 ...")
    archives = fetch_channel_videos(CHANNEL_ID)
    if not archives:
        print("  [ERROR] 未获取到视频，退出")
        return

    # Step 2: 整理分季
    print("\n[2/4] 按季度/篇章整理 ...")
    seasons = organize_series(archives)
    total_eps = sum(len(v) for v in seasons.values())
    print(f"  共 {total_eps} 集，分布在 {len(seasons)} 个季度中")
    for s_name, eps in seasons.items():
        print(f"    {s_name}: {len(eps)} 集")

    # Step 3: 逐集获取详情/弹幕/评论
    print("\n[3/4] 逐集获取详情、弹幕、评论 ...")
    episode_count = 0
    for season_name, episodes in seasons.items():
        for ep in episodes:
            episode_count += 1
            bvid = ep["bvid"]
            cid = ep.get("cid", 0)
            title = ep["title"][:50]
            print(f"  [{episode_count}/{total_eps}] [{season_name}] {title}")

            # 详情（补充缺失字段）
            info = fetch_video_detail(bvid)
            if info:
                stat = info.get("stat", {})
                ep["description"] = info.get("desc", ep.get("description", ""))
                ep["play"] = stat.get("view", ep.get("play", 0))
                ep["danmaku_count"] = stat.get("danmaku", ep.get("danmaku_count", 0))
                ep["like"] = stat.get("like", 0)
                ep["coin"] = stat.get("coin", 0)
                ep["favorite"] = stat.get("favorite", 0)
                ep["aid"] = info.get("aid", ep.get("aid", 0))
                if not ep.get("cid"):
                    ep["cid"] = info.get("cid", 0)

            # 弹幕（需要有效的 cid）
            if ep.get("cid"):
                dms = fetch_danmaku(bvid, ep["cid"])
                ep["danmaku_list"] = [{"time": t, "text": txt} for t, txt in dms[:200]]

                density = {}
                for t, _ in dms:
                    bucket = (t // 10) * 10
                    density[bucket] = density.get(bucket, 0) + 1
                ep["danmaku_highlights"] = sorted(density.items(), key=lambda x: -x[1])[:10]
            else:
                ep["danmaku_list"] = []
                ep["danmaku_highlights"] = []

            # 评论
            if ep.get("aid"):
                ep["top_comments"] = fetch_comments(ep["aid"])
            else:
                ep["top_comments"] = []

            time.sleep(0.5)

    # Step 4: 输出
    print("\n[4/4] 输出结果 ...")

    json_output = {
        "meta": {
            "up_mid": UP_MID,
            "up_name": "沙雕Mars",
            "channel_id": CHANNEL_ID,
            "series": "关于我转生变成流汗黄豆这档事",
            "total_episodes": total_eps,
            "seasons": list(seasons.keys()),
            "generated_at": datetime.now().isoformat(),
        },
        "seasons": seasons,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f"  JSON -> {OUTPUT_JSON}")

    md = generate_markdown(seasons)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  MD  -> {OUTPUT_MD}")

    if download_videos:
        print("\n[可选] 用 yt-dlp 下载视频 ...")
        _download_videos(seasons)

    print("\n" + "=" * 60)
    print("采集完成！")
    print("=" * 60)


def _download_videos(seasons: dict):
    dl_dir = OUTPUT_DIR / "videos"
    dl_dir.mkdir(exist_ok=True)
    for episodes in seasons.values():
        for ep in episodes:
            url = f"https://www.bilibili.com/video/{ep['bvid']}"
            name = safe_filename(f"{ep['title']}_{ep['bvid']}")
            print(f"  下载: {name}")
            try:
                subprocess.run(
                    ["yt-dlp", "-o", str(dl_dir / f"{name}.%(ext)s"),
                     "--write-subs", "--sub-langs", "ai-zh", url],
                    check=False,
                )
            except FileNotFoundError:
                print("  [ERROR] yt-dlp 未安装")
                return


# ---------------------------------------------------------------------------
# 分析模块
# ---------------------------------------------------------------------------

def analyze_series(json_path: str = str(OUTPUT_JSON)):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60)
    print("数据分析")
    print("=" * 60)

    all_dms = []
    all_keywords = Counter()

    for season_name, episodes in data["seasons"].items():
        print(f"\n## {season_name}")
        for ep in episodes:
            dms = ep.get("danmaku_list", [])
            all_dms.extend(dms)
            for word in ["抽象", "绝绝子", "偶像", "丧尸", "恶魔", "勇者",
                         "狼人杀", "纯爱", "轮回"]:
                if word in ep["title"]:
                    all_keywords[word] += 1

            highlights = ep.get("danmaku_highlights", [])
            top_info = f" 高能: {highlights[0][0]}s ({highlights[0][1]}条)" if highlights else ""
            print(f"  {ep['title'][:50]}")
            print(f"    播放: {ep.get('play', 0):,} | "
                  f"弹幕: {ep.get('danmaku_count', 0):,} | "
                  f"点赞: {ep.get('like', 0):,}{top_info}")

    print(f"\n## 总览")
    print(f"  总弹幕数: {len(all_dms):,}")
    print(f"  标题关键词: {all_keywords.most_common(10)}")

    all_eps = [ep for episodes in data["seasons"].values() for ep in episodes]
    all_eps.sort(key=lambda e: e.get("play", 0), reverse=True)
    print(f"\n## 播放量 TOP 10")
    for ep in all_eps[:10]:
        print(f"  {ep['play']:,} — {ep['title']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="B站流汗黄豆系列采集器")
    parser.add_argument("--download", action="store_true", help="额外下载视频（需 yt-dlp）")
    parser.add_argument("--analyze", action="store_true", help="分析已采集的 JSON 数据")
    parser.add_argument("--json", default=str(OUTPUT_JSON), help="分析用的 JSON 路径")
    args = parser.parse_args()

    if args.analyze:
        analyze_series(args.json)
    else:
        run(download_videos=args.download)
