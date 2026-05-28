from bilibili_api import sync, search, user
from bilibili_api.search import SearchObjectType

# --- Search for the series ---
print("=== Search API ===")
resp = sync(search.search_by_type(
    keyword="沙雕Mars 关于我转生变成流汗黄豆",
    search_type=SearchObjectType.VIDEO,
    page=1,
    page_size=50,
))
items = resp.get("result", [])
print(f"Found {len(items)} results")
for item in items[:5]:
    title = item.get("title", "")
    bvid = item.get("bvid", "")
    play = item.get("play", 0)
    print(f"  {title[:60]} | {bvid} | {play:,} plays")

# --- Check channels (合集) ---
print("\n=== Channels ===")
u = user.User(43739579)
try:
    channels = sync(u.get_channels())
    print(f"Found {len(channels)} channels")
    for ch in channels[:10]:
        print(f"  {ch.get('name','')} | id={ch.get('id','')} | {ch.get('count','')}集")
except Exception as e:
    print(f"Error: {e}")

# --- Try series API ---
print("\n=== Video Series ===")
try:
    # Try to get series by UP
    series_resp = sync(u.get_channel_videos_series())
    print(f"Series: {series_resp}")
except Exception as e:
    print(f"Error: {e}")
