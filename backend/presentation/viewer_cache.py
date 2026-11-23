"""Refresh only this project's Bike viewer route after source changes."""
from pathlib import Path
import hashlib

def refresh(cache,source):
    source=Path(source)
    stamp=hashlib.sha256(source.read_bytes()).hexdigest()
    receipt="bike.link.viewer.source.sha256"
    if cache.get(receipt)==stamp:return False
    cache.pop("route.code#bike.link.viewer",None)
    for key in list(cache):
        if key.startswith("route.fn#"):
            try:same=Path(key.split("#",1)[1]).resolve()==source.resolve()
            except (ValueError,OSError):same=False
            if same:cache.pop(key,None)
    cache[receipt]=stamp
    return True
