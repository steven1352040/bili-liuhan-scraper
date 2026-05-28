"""Quick test of bilibili-api-python APIs"""
from bilibili_api import sync, user, video

u = user.User(43739579)
resp = sync(u.get_videos(ps=5, pn=1))
print("Response keys:", list(resp.keys()))
if "list" in resp:
    l = resp["list"]
    if "vlist" in l:
        print("vlist count:", len(l["vlist"]))
        if l["vlist"]:
            v = l["vlist"][0]
            print("Video keys:", list(v.keys()))
            print("Title:", v.get("title", "")[:50])
            print("Bvid:", v.get("bvid", ""))

# Test danmaku
print("\n--- Danmaku test ---")
v2 = video.Video(bvid="BV16F411z7QY")
info = sync(v2.get_info())
print("Info keys:", list(info.keys())[:10])
print("Title:", info.get("title", "")[:50])

dms = sync(v2.get_danmakus(page_index=0))
print(f"Danmaku count (page 0): {len(dms)}")
if dms:
    dm = dms[0]
    print(f"First danmaku type: {type(dm).__name__}")
    print(f"First danmaku attrs: {[a for a in dir(dm) if not a.startswith('_')]}")
    print(f"Text: {dm.text}, Time: {dm.dm_time}")
