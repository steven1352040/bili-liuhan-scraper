"""
弹幕分析 + 高能台词匹配脚本

功能：
  1. 读取 liuhan_data.json 的弹幕数据
  2. 每集提取弹幕热词 TOP5
  3. 找到弹幕密度最高的时刻（高能时刻）
  4. 匹配对应 SRT 字幕中的台词
  5. 输出结果，用于补充 liuhan_analysis.md

输出：output/danmaku_insights.json（结构化数据）
      output/danmaku_insights.md（可直接粘贴到分析报告）
"""

import json
import re
import os
import sys
from collections import Counter
from pathlib import Path

# 强制 UTF-8 输出，避免 emoji 导致的编码崩溃
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

OUTPUT_DIR = Path("output")
JSON_PATH = OUTPUT_DIR / "liuhan_data.json"
SUBS_DIR = OUTPUT_DIR / "subs"
OUT_JSON = OUTPUT_DIR / "danmaku_insights.json"
OUT_MD = OUTPUT_DIR / "danmaku_insights.md"

# 停用词（弹幕中常见但无分析价值的词）
STOP_WORDS = set([
    "哈哈哈", "哈哈哈哈", "哈哈", "笑死", "来了", "打卡", "有人吗",
    "前排", "第一", "第二", "第三", "火钳刘明", "考古", "再看一遍",
    "卧槽", "牛逼", "666", "？？？", "？？", "!!!", "。。。",
    "啊啊啊", "啊啊啊啊", "awsl", "后面呢", "前面的", "真实",
    "确实", "就是", "这个", "那个", "什么", "不是", "可以",
    "一个", "怎么", "为什么", "所以", "因为", "但是", "如果",
    "已经", "还是", "没有", "自己", "真的", "觉得", "知道",
    "不过", "然后", "的话", "吧", "吗", "呢", "啊", "哦", "嗯",
    "了", "的", "是", "在", "我", "你", "他", "她", "它",
    "这", "那", "不", "就", "都", "也", "还", "要", "会",
    "有", "很", "好", "看", "说", "想", "到", "去", "来",
    "多", "少", "大", "小", "上", "下", "中", "前", "后",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "个", "次", "点", "只", "",
])


def parse_srt(filepath: str) -> list[tuple[float, float, str]]:
    """解析 SRT 字幕，返回 [(开始秒, 结束秒, 文本), ...]"""
    if not os.path.exists(filepath):
        return []

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    subtitles = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # 跳过硬编码的换行序号
        time_match = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s*-->\s*(\d+):(\d+):(\d+)[.,](\d+)", lines[1] if len(lines) > 1 else "")
        if not time_match:
            # 尝试在整块中找时间戳
            for line in lines:
                time_match = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s*-->\s*(\d+):(\d+):(\d+)[.,](\d+)", line)
                if time_match:
                    break
        if not time_match:
            continue

        start = int(time_match.group(1)) * 3600 + int(time_match.group(2)) * 60 + int(time_match.group(3)) + int(time_match.group(4)) / 1000
        end = int(time_match.group(5)) * 3600 + int(time_match.group(6)) * 60 + int(time_match.group(7)) + int(time_match.group(8)) / 1000

        text_lines = []
        for line in lines[2:]:
            line = line.strip()
            if line and not line.isdigit():
                text_lines.append(line)
        text = " ".join(text_lines)
        if text:
            subtitles.append((start, end, text))

    return subtitles


def tokenize(text: str) -> list[str]:
    """简易中文分词：提取有意义的2-4字词组"""
    # 先清理：去掉纯英文+数字+标点的重复模式（如 hhhh、666、??? ）
    text = re.sub(r"\b[a-zA-Z0-9]+\b", "", text)  # 去掉纯英文数字词
    text = re.sub(r"[^一-鿿]", "", text)   # 只保留汉字
    if len(text) < 2:
        return []

    tokens = []
    # 2-gram
    for i in range(len(text) - 1):
        w = text[i:i+2]
        if w not in STOP_WORDS:
            tokens.append(w)
    # 3-gram
    for i in range(len(text) - 2):
        w = text[i:i+3]
        if w not in STOP_WORDS and w[0] != w[1]:  # 过滤同字重复（如"啊啊啊"）
            tokens.append(w)
    # 4-gram
    for i in range(len(text) - 3):
        w = text[i:i+4]
        if len(set(w)) > 1:  # 至少两个不同字符
            tokens.append(w)
    return tokens


def extract_keywords(danmaku_list: list[dict], top_k: int = 8) -> list[str]:
    """从弹幕列表提取热词"""
    all_tokens = []
    for dm in danmaku_list:
        text = dm.get("text", "")
        all_tokens.extend(tokenize(text))

    counter = Counter(all_tokens)
    # 过滤频率<2的词
    keywords = [(w, c) for w, c in counter.most_common(50) if c >= 2]
    return [w for w, _ in keywords[:top_k]]


def find_peak_moments(danmaku_list: list[dict], top_k: int = 3) -> list[tuple[int, int]]:
    """找到弹幕密度最高的几个时刻（10秒窗口），返回 [(秒, 弹幕数), ...]"""
    buckets = {}
    for dm in danmaku_list:
        t = dm.get("time", 0)
        bucket = (int(t) // 10) * 10
        buckets[bucket] = buckets.get(bucket, 0) + 1

    sorted_buckets = sorted(buckets.items(), key=lambda x: -x[1])
    return sorted_buckets[:top_k]


def match_subtitle(seconds: float, subtitles: list[tuple[float, float, str]], window: float = 8.0) -> str:
    """找到给定秒数附近窗口内的字幕文本"""
    matches = []
    for start, end, text in subtitles:
        if start <= seconds + window and end >= seconds - window:
            matches.append((abs(start - seconds), text))

    if not matches:
        return ""
    matches.sort(key=lambda x: x[0])
    # 合并附近的多条字幕
    texts = [m[1] for m in matches[:3]]
    return " | ".join(texts)


def find_srt_file(ep_title: str, ep_index: int) -> str | None:
    """根据集标题找到对应的 SRT 文件"""
    # SRT 文件名格式: "01_标题.ai-zh.srt"
    for fname in sorted(os.listdir(SUBS_DIR)):
        if not fname.endswith(".srt"):
            continue
        # 提取文件名中的序号
        match = re.match(r"(\d+)_", fname)
        if match:
            num = int(match.group(1))
            if num == ep_index:
                return str(SUBS_DIR / fname)

    # 回退：用标题模糊匹配
    for fname in os.listdir(SUBS_DIR):
        if fname.endswith(".srt"):
            # 取标题前15字做匹配
            short_title = ep_title.replace(" ", "").replace("【", "").replace("】", "")[:15]
            if short_title and short_title in fname.replace(" ", ""):
                return str(SUBS_DIR / fname)

    return None


def process_all():
    """主处理流程"""
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    seasons = data["seasons"]
    results = {}

    for s_name, s_data in seasons.items():
        episodes = s_data.get("episodes", [])
        results[s_name] = []

        for ep in episodes:
            ep_idx = ep.get("index", 0)
            title = ep.get("title", "")
            danmaku_list = ep.get("danmaku_list", [])

            if not danmaku_list:
                results[s_name].append({"title": title, "keywords": [], "peaks": [], "subs_found": False})
                continue

            # 1. 热词
            keywords = extract_keywords(danmaku_list)
            print(f"  [{s_name}] EP{ep_idx} {title[:40]} | 弹幕:{len(danmaku_list)} | 热词:{','.join(keywords[:5])}")

            # 2. 高能时刻
            peaks = find_peak_moments(danmaku_list, top_k=3)

            # 3. 匹配字幕
            srt_path = find_srt_file(title, ep_idx)
            subs = parse_srt(srt_path) if srt_path else []

            peak_details = []
            for sec, count in peaks:
                line = match_subtitle(sec, subs) if subs else ""
                peak_details.append({
                    "seconds": sec,
                    "danmaku_count": count,
                    "subtitle_line": line[:120] if line else "(未找到对应字幕)",
                })

            results[s_name].append({
                "index": ep_idx,
                "title": title,
                "bvid": ep.get("bvid", ""),
                "play": ep.get("play", 0),
                "danmaku_count": ep.get("danmaku_count", 0),
                "keywords": keywords,
                "peak_moments": peak_details,
                "subs_found": bool(subs),
            })

    # 输出 JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[JSON] -> {OUT_JSON}")

    # 输出 Markdown
    generate_markdown(results)
    print(f"[MD]   -> {OUT_MD}")


def generate_markdown(results: dict):
    """生成可直接粘贴到分析报告的 Markdown"""
    lines = ["# 弹幕分析 & 高能台词", ""]

    for s_name, episodes in results.items():
        lines.append(f"## {s_name}")
        lines.append("")

        for ep in episodes:
            if not ep.get("keywords") and not ep.get("peak_moments"):
                continue

            lines.append(f"### EP{ep['index']} · {ep['title']}")
            lines.append("")

            # 弹幕热词
            if ep["keywords"]:
                kws = "、".join(ep["keywords"][:5])
                lines.append(f"**弹幕热词**：{kws}")
                lines.append("")

            # 高能时刻
            if ep["peak_moments"]:
                lines.append("**高能时刻**：")
                lines.append("")
                for i, p in enumerate(ep["peak_moments"], 1):
                    mm = f"{p['seconds']//60:02d}:{p['seconds']%60:02d}"
                    lines.append(f"{i}. `{mm}`（{p['danmaku_count']}条弹幕爆发）")
                    if p["subtitle_line"] and p["subtitle_line"] != "(未找到对应字幕)":
                        lines.append(f"   > {p['subtitle_line']}")
                    lines.append("")

            lines.append("---")
            lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    process_all()
