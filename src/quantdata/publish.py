"""Create bounded GitHub Release assets, keeping large datasets outside Git history."""
import json
import zipfile
from pathlib import Path

from .acquire import atomic_json, sha256


def assets(root, max_bytes=400_000_000):
    root = Path(root)
    dest = root / "release-assets"
    dest.mkdir(exist_ok=True)
    candidates = sorted(p for p in (root / "data").rglob("*") if p.is_file() and not p.name.endswith(".part"))
    groups, current, size = [], [], 0
    for path in candidates:
        if path.stat().st_size > max_bytes:
            raise ValueError(f"Partition exceeds asset budget: {path}")
        if current and size + path.stat().st_size > max_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(path)
        size += path.stat().st_size
    if current:
        groups.append(current)
    result = []
    for n, group in enumerate(groups, 1):
        target = dest / f"research-data-{n:03d}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as out:
            for path in group:
                out.write(path, str(path.relative_to(root)))
        result.append({"asset": target.name, "sha256": sha256(target), "bytes": target.stat().st_size,
                       "members": [str(p.relative_to(root)) for p in group]})
    atomic_json(dest / "ASSETS.json", result)
    return result
