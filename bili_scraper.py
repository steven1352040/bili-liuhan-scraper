"""
B站 UP主「沙雕Mars」《关于我转生变成流汗黄豆》系列视频采集 & 分析脚本

按 B站合集原始分类，每个合集频道作为一季/系列。
数据源：UP主空间的全部合集频道

使用：
  python bili_scraper.py              # 采集全部合集元数据（快速）
  python bili_scraper.py --full       # 采集元数据 + 弹幕 + 评论（慢）
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

sys.stdout.reconfigure(encoding='utf-8')

from bilibili_api import sync, user, video, comment
from bilibili_api.comment import CommentResourceType

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

UP_MID = 43739579
UP_NAME = "沙雕Mars"
OUTPUT_DIR = Path("output")
OUTPUT_JSON = OUTPUT_DIR / "liuhan_data.json"
OUTPUT_MD = OUTPUT_DIR / "liuhan_outline.md"

# 要采集的合集频道 ID 及其自定义名称 & 排序
# B站上该UP主的合集已按季/系列分好
CHANNELS = [
    {"id": 28754,   "name": "第一季·原创动画",      "order": 1},
    {"id": 2199285, "name": "第一季·合集版",         "order": 2},
    {"id": 5096626, "name": "番外·表情包大战PVZ",    "order": 3},
    {"id": 5134293, "name": "番外·emoji日常",        "order": 4},
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def ts_to_str(ts: int) -> str:
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


# ---------------------------------------------------------------------------
# 数据采集（元数据）
# ---------------------------------------------------------------------------

def fetch_all_channels() -> list[dict]:
    """获取所有目标合集的视频列表，返回 [{channel_info, videos}, ...]"""
    u = user.User(UP_MID)
    channels = sync(u.get_channels())

    results = []
    for ch_config in CHANNELS:
        target_id = ch_config["id"]
        found = False
        for ch in channels:
            meta = sync(ch.get_meta())
            if ch.id_ == target_id:
                resp = sync(ch.get_videos(ps=100))
                archives = resp.get("archives", [])
                results.append({
                    "channel_id": target_id,
                    "channel_name": ch_config["name"],
                    "order": ch_config["order"],
                    "bilibili_name": meta.get("name", ""),
                    "bilibili_total": meta.get("total", 0),
                    "description": meta.get("description", ""),
                    "videos": archives,
                    "fetched": len(archives),
                })
                print(f"  [{ch_config['name']}] {meta.get('name', '?')} "
                      f"— {len(archives)}/{meta.get('total', 0)} 集")
                found = True
                break
        if not found:
            print(f"  [WARN] 未找到合集频道 id={target_id} ({ch_config['name']})")

    return results


# ---------------------------------------------------------------------------
# 数据采集（详情/弹幕/评论）
# ---------------------------------------------------------------------------

def fetch_video_detail(bvid: str) -> dict | None:
    v = video.Video(bvid=bvid)
    try:
        return sync(v.get_info())
    except Exception as e:
        print(f"  [WARN] 获取 {bvid} 详情失败: {e}")
        return None


def fetch_danmaku(bvid: str, cid: int, max_dms: int = 3000) -> list:
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
            oid=oid, type_=CommentResourceType.VIDEO, page_index=1,
        ))
        replies = resp.get("replies") or []
        return [
            {"user": r.get("member", {}).get("uname", ""),
             "content": r.get("content", {}).get("message", ""),
             "likes": r.get("like", 0)}
            for r in replies[:20]
        ]
    except Exception as e:
        print(f"  [WARN] 评论获取失败: {e}")
        return []


# ---------------------------------------------------------------------------
# 数据整理
# ---------------------------------------------------------------------------

def organize(channel_results: list[dict]) -> dict:
    """将频道数据整理为统一的 seasons 结构"""
    seasons = {}
    total_eps = 0

    for ch in sorted(channel_results, key=lambda x: x["order"]):
        season_name = ch["channel_name"]
        episodes = []

        for idx, v in enumerate(ch["videos"]):
            title = v.get("title", "")
            stat = v.get("stat", {}) if isinstance(v.get("stat"), dict) else {}
            episodes.append({
                "index": idx + 1,
                "title": title,
                "bvid": v.get("bvid", ""),
                "aid": v.get("aid", 0),
                "cid": v.get("cid", 0),
                "created": ts_to_str(v.get("pubdate", 0) or v.get("ctime", 0)),
                "duration": v.get("duration", ""),
                "play": stat.get("view", v.get("play", 0)),
                "danmaku_count": stat.get("danmaku", 0),
                "description": v.get("desc", ""),
            })

        seasons[season_name] = {
            "channel_id": ch["channel_id"],
            "bilibili_name": ch["bilibili_name"],
            "description": ch["description"],
            "episodes": episodes,
        }
        total_eps += len(episodes)

    return {"seasons": seasons, "total_episodes": total_eps}


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def generate_markdown(data: dict) -> str:
    seasons = data["seasons"]
    lines = [
        "# 《关于我转生变成流汗黄豆这档事》采集结果",
        "",
        f"> 自动采集时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> UP主：{UP_NAME}（UID: {UP_MID}）",
        "",
        f"**总计 {data['total_episodes']} 集** | 共 {len(seasons)} 个分类",
        "",
    ]

    for season_name, info in seasons.items():
        episodes = info["episodes"]
        lines.append(f"## {season_name}（{len(episodes)} 集）")
        lines.append(f"> B站合集：{info['bilibili_name']}")
        if info["description"]:
            lines.append(f"> {info['description'][:200]}")
        lines.append("")

        for ep in episodes:
            lines.append(f"### 第 {ep['index']} 集 · {ep['title']}")
            lines.append("")
            lines.append(f"- **BV号**：`{ep['bvid']}`")
            lines.append(f"- **发布时间**：{ep['created']}")
            lines.append(f"- **时长**：{ep['duration']}秒")
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
                for ts, density in ep["danmaku_highlights"][:5]:
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

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(full: bool = False, download_videos: bool = False):
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print(f"B站视频采集 — 沙雕Mars 全部合集")
    print(f"共 {len(CHANNELS)} 个合集频道")
    print("=" * 60)

    # Step 1: 获取全部合集频道
    print("\n[1/2] 从合集频道获取视频列表 ...")
    channel_results = fetch_all_channels()
    if not channel_results:
        print("  [ERROR] 未获取到任何视频，退出")
        return

    total_videos = sum(ch["fetched"] for ch in channel_results)
    print(f"  共获取 {total_videos} 个视频")

    # Step 1.5: 整理
    data = organize(channel_results)

    # Step 2 (可选): 逐集获取详情/弹幕/评论
    if full:
        print(f"\n[2/2] 逐集获取详情、弹幕、评论（共 {data['total_episodes']} 集）...")
        episode_count = 0
        for season_name, info in data["seasons"].items():
            for ep in info["episodes"]:
                episode_count += 1
                bvid = ep["bvid"]
                cid = ep.get("cid", 0)
                title = ep["title"][:50]
                print(f"  [{episode_count}/{data['total_episodes']}] "
                      f"[{season_name}] {title}")

                info_resp = fetch_video_detail(bvid)
                if info_resp:
                    stat = info_resp.get("stat", {})
                    ep["description"] = info_resp.get("desc", ep.get("description", ""))
                    ep["play"] = stat.get("view", ep.get("play", 0))
                    ep["danmaku_count"] = stat.get("danmaku", ep.get("danmaku_count", 0))
                    ep["like"] = stat.get("like", 0)
                    ep["coin"] = stat.get("coin", 0)
                    ep["favorite"] = stat.get("favorite", 0)
                    ep["aid"] = info_resp.get("aid", ep.get("aid", 0))
                    if not ep.get("cid"):
                        ep["cid"] = info_resp.get("cid", 0)

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

                if ep.get("aid"):
                    ep["top_comments"] = fetch_comments(ep["aid"])
                else:
                    ep["top_comments"] = []

                time.sleep(0.3)
    else:
        print(f"\n[2/2] 跳过详情采集（使用 --full 可获取弹幕和评论）")

    # 输出
    print("\n生成输出文件 ...")

    json_output = {
        "meta": {
            "up_mid": UP_MID,
            "up_name": UP_NAME,
            "total_episodes": data["total_episodes"],
            "categories": list(data["seasons"].keys()),
            "generated_at": datetime.now().isoformat(),
        },
    }
    # 扁平化 seasons 结构
    json_seasons = {}
    for name, info in data["seasons"].items():
        json_seasons[name] = {
            "channel_id": info["channel_id"],
            "bilibili_name": info["bilibili_name"],
            "episodes": info["episodes"],
        }
    json_output["seasons"] = json_seasons

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f"  JSON -> {OUTPUT_JSON}")

    md = generate_markdown(data)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  MD  -> {OUTPUT_MD}")

    # 打印统计
    print("\n" + "=" * 60)
    print(f"采集完成！")
    for s_name in data["seasons"]:
        eps = data["seasons"][s_name]["episodes"]
        total_play = sum(ep.get("play", 0) for ep in eps)
        print(f"  {s_name}: {len(eps)} 集 | 总播放: {total_play:,}")
    print(f"  **总计: {data['total_episodes']} 集**")
    print("=" * 60)

    if download_videos:
        print("\n[可选] 用 yt-dlp 下载视频 ...")
        _download_videos(data["seasons"])


def _download_videos(seasons: dict):
    dl_dir = OUTPUT_DIR / "videos"
    dl_dir.mkdir(exist_ok=True)
    for season_name, info in seasons.items():
        for ep in info["episodes"]:
            url = f"https://www.bilibili.com/video/{ep['bvid']}"
            name = safe_filename(f"[{season_name}]{ep['title']}_{ep['bvid']}")
            print(f"  下载: {name[:60]}")
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

    for season_name, info in data["seasons"].items():
        episodes = info["episodes"]
        total_play = sum(ep.get("play", 0) for ep in episodes)
        total_dm = sum(ep.get("danmaku_count", 0) for ep in episodes)
        total_like = sum(ep.get("like", 0) for ep in episodes)
        print(f"\n## {season_name}（{len(episodes)} 集）")
        print(f"  总播放: {total_play:,} | 总弹幕: {total_dm:,} | 总点赞: {total_like:,}")

        # 播放量 TOP 5
        sorted_eps = sorted(episodes, key=lambda e: e.get("play", 0), reverse=True)
        print(f"  播放量 TOP 5:")
        for ep in sorted_eps[:5]:
            print(f"    {ep.get('play', 0):,} — {ep['title'][:50]}")

        # 弹幕数 TOP 5
        sorted_dm = sorted(episodes, key=lambda e: e.get("danmaku_count", 0), reverse=True)
        print(f"  弹幕数 TOP 5:")
        for ep in sorted_dm[:5]:
            print(f"    {ep.get('danmaku_count', 0):,} — {ep['title'][:50]}")

    # 全系列总览
    all_eps = []
    for season_name, info in data["seasons"].items():
        for ep in info["episodes"]:
            ep = dict(ep)
            ep["_season"] = season_name
            all_eps.append(ep)

    all_eps.sort(key=lambda e: e.get("play", 0), reverse=True)
    print(f"\n## 全系列播放量 TOP 10")
    for ep in all_eps[:10]:
        print(f"  {ep.get('play', 0):,} [{ep['_season']}] {ep['title'][:50]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="B站流汗黄豆系列采集器")
    parser.add_argument("--full", action="store_true", help="获取全部详情（弹幕+评论，耗时较长）")
    parser.add_argument("--download", action="store_true", help="额外下载视频（需 yt-dlp）")
    parser.add_argument("--analyze", action="store_true", help="分析已采集的 JSON 数据")
    parser.add_argument("--json", default=str(OUTPUT_JSON), help="分析用的 JSON 路径")
    args = parser.parse_args()

    if args.analyze:
        analyze_series(args.json)
    else:
        run(full=args.full, download_videos=args.download)
