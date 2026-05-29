"""
将弹幕分析结果合并到 liuhan_analysis.md 的每集大纲中。

策略：读取 danmaku_insights.json，在 liuhan_analysis.md 中
找到每集的 #### EPXX 标题，在剧情概要后插入弹幕热词和高能时刻。
"""

import json
import re

INSIGHTS_PATH = "output/danmaku_insights.json"
ANALYSIS_PATH = "output/liuhan_analysis.md"
OUTPUT_PATH = "output/liuhan_analysis.md"

# 季/集标题到 insights 的映射规则
# insights 中的季名 -> analysis 中的篇章名
SEASON_MAP = {
    "第一季·原创动画": [
        "启程篇", "歪比巴卜篇", "捉鬼过渡篇", "枝江偶像篇",
        "抽象动画篇", "生化丧尸篇", "完结反思篇", "勇者篇"
    ],
}


def load_insights() -> dict:
    """加载弹幕分析结果，建立 (集序号) -> insights 的映射"""
    with open(INSIGHTS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # data is {season_name: [{index, title, keywords, peak_moments}, ...]}
    mapping = {}
    for s_name, episodes in data.items():
        if s_name != "第一季·原创动画":
            continue  # 只处理主系列55集
        for ep in episodes:
            ep_idx = ep.get("index", 0)
            mapping[ep_idx] = ep
    return mapping


def format_insights(ep: dict) -> str:
    """格式化一集的弹幕分析为 Markdown"""
    lines = []

    # 弹幕热词
    keywords = ep.get("keywords", [])
    if keywords:
        kws = "、".join(keywords[:5])
        lines.append(f"**🎬 弹幕热词**：{kws}")
        lines.append("")

    # 高能时刻
    peaks = ep.get("peak_moments", [])
    if peaks:
        lines.append("**🎯 高能时刻**：")
        lines.append("")
        for i, p in enumerate(peaks, 1):
            sec = p["seconds"]
            mm = f"{int(sec)//60:02d}:{int(sec)%60:02d}"
            count = p["danmaku_count"]
            sub = p.get("subtitle_line", "")
            if sub and sub != "(未找到对应字幕)":
                lines.append(f"{i}. `{mm}` — **{count}条**弹幕爆发")
                lines.append(f"   > *{sub[:150]}*")
            else:
                lines.append(f"{i}. `{mm}` — **{count}条**弹幕爆发")
            lines.append("")

    return "\n".join(lines)


def merge():
    """主合并逻辑"""
    insights_map = load_insights()
    print(f"加载了 {len(insights_map)} 集的弹幕分析")

    with open(ANALYSIS_PATH, encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    new_lines = []
    current_ep = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测 EP 标题行：#### EP01 · 或 #### EP1 ·
        ep_match = re.match(r"^#### EP(\d+) ·", line)
        if ep_match:
            current_ep = int(ep_match.group(1))
            new_lines.append(line)
            i += 1

            # 找到这段剧情概要的结束位置（下一个 #### 或 --- 或空行块结束）
            # 收集这集的所有行
            ep_lines = []
            while i < len(lines):
                next_line = lines[i]
                # 遇到下一个 EP 标题或篇章标题就停
                if re.match(r"^#### EP\d+", next_line) or re.match(r"^### [^\s]", next_line):
                    break
                if re.match(r"^---$", next_line.strip()):
                    # 把 --- 也加入，保持在后面
                    ep_lines.append(next_line)
                    i += 1
                    break
                ep_lines.append(next_line)
                i += 1

            # 在这集内容末尾插入弹幕分析
            # 先写回这集的内容
            for el in ep_lines:
                new_lines.append(el)

            # 插入弹幕分析
            if current_ep in insights_map:
                insights_text = format_insights(insights_map[current_ep])
                if insights_text:
                    new_lines.append("")  # 空行分隔
                    new_lines.extend(insights_text.split("\n"))
                    print(f"  EP{current_ep:02d} ✓")
            else:
                print(f"  EP{current_ep:02d} ✗ (无弹幕数据)")

        else:
            new_lines.append(line)
            i += 1

    # 写回
    result = "\n".join(new_lines)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n合并完成 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    merge()
