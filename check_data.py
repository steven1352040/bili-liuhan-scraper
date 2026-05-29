import json

with open("output/liuhan_data.json", encoding="utf-8") as f:
    data = json.load(f)

seasons = data["seasons"]
total_eps = 0
total_dms = 0
total_comments = 0

for s_name, eps in seasons.items():
    ep_count = len(eps)
    total_eps += ep_count
    dms_count = sum(len(ep.get("danmaku_list", [])) for ep in eps)
    comments_count = sum(len(ep.get("top_comments", [])) for ep in eps)
    total_dms += dms_count
    total_comments += comments_count
    print(f"【{s_name}】{ep_count}集 | 弹幕: {dms_count}条 | 评论: {comments_count}条")

    # Show first 2 episodes as sample
    for ep in eps[:2]:
        dms = ep.get("danmaku_list", [])
        comments = ep.get("top_comments", [])
        title = ep["title"][:50]
        print(f"  {title}")
        print(f"    弹幕: {len(dms)}条 | 评论: {len(comments)}条")
        if dms:
            # Show top 3 danmaku by time
            print(f"    弹幕示例: {dms[0]['text'][:40]} / {dms[len(dms)//2]['text'][:40]}")
        if comments:
            print(f"    评论示例: {comments[0]['content'][:60]} ({comments[0]['likes']}赞)")

print(f"\n===== 总计 =====")
print(f"集数: {total_eps}")
print(f"弹幕总数: {total_dms:,}")
print(f"评论总数: {total_comments:,}")

# TOP danmaku density episodes
print(f"\n===== 弹幕最多的5集 =====")
all_eps = []
for s_name, eps in seasons.items():
    for ep in eps:
        all_eps.append((s_name, ep["title"], len(ep.get("danmaku_list", []))))
all_eps.sort(key=lambda x: -x[2])
for s, t, c in all_eps[:5]:
    print(f"  [{s}] {t[:50]} — {c}条弹幕")

# Check comments richness
print(f"\n===== 评论最多的5集 =====")
all_eps2 = []
for s_name, eps in seasons.items():
    for ep in eps:
        all_eps2.append((s_name, ep["title"], len(ep.get("top_comments", []))))
all_eps2.sort(key=lambda x: -x[2])
for s, t, c in all_eps2[:5]:
    print(f"  [{s}] {t[:50]} — {c}条评论")
