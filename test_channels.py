import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from bilibili_api import sync, user
import inspect

u = user.User(43739579)
channels = sync(u.get_channels())

# Find the 流汗黄豆 channel
for ch in channels:
    meta = sync(ch.get_meta())
    name = meta.get("name", "")
    if "流汗黄豆" in name:
        print(f"Found: id={ch.id_}, name={name}, count={meta.get('total',0)}")
        # Check get_videos signature
        print(f"get_videos sig: {inspect.signature(ch.get_videos)}")
        # Try getting videos
        try:
            vids = sync(ch.get_videos())
            print(f"Type: {type(vids)}")
            if isinstance(vids, dict):
                print(f"Keys: {list(vids.keys())}")
                if "list" in vids or "archives" in vids:
                    inner = vids.get("list") or vids.get("archives") or []
                    print(f"Videos: {len(inner)}")
                    if inner:
                        v = inner[0]
                        print(f"First: {v.get('title','')[:60]} | {v.get('bvid','')}")
            elif isinstance(vids, list):
                print(f"List length: {len(vids)}")
                if vids:
                    v = vids[0]
                    if isinstance(v, dict):
                        print(f"First: {v.get('title','')[:60]} | {v.get('bvid','')}")
                    else:
                        print(f"First type: {type(v)}")
                        print(dir(v)[:20])
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        break
