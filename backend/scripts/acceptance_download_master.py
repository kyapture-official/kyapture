"""
Chunk 6-D acceptance: real photos through the OLD and the NEW Download Master encoder.

Run inside the backend container (the pinned cjpegli lives there):

    git show 9e17cdc:backend/apps/core/utils.py > old_utils.py        # the pre-6-B helper
    docker cp old_utils.py kyapture-backend-1:/tmp/old_utils.py
    docker exec kyapture-backend-1 python scripts/acceptance_download_master.py \\
        --src /photos --old /tmp/old_utils.py --out /tmp/acceptance-6d

Reads the photos, never writes next to them. For each photo it records original / old / new bytes,
dimensions, encode time (new: median of 3; old: one run), whether three runs give identical bytes,
the Pillow-fallback result (cjpegli deliberately pointed at nothing), the mean colour shift against
the oriented sRGB 3600 px reference, and whether the original file's SHA-256 is unchanged.
It also writes old.jpg / new.jpg / ref.ppm and 100% crop strips [reference | old | new] for a
visual review (detail, smooth gradient, shadow, hard edge).
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from apps.core import utils as new_utils

CROP = 300


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_old(path):
    spec = importlib.util.spec_from_file_location("old_core_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_master(module, name, raw):
    started = time.perf_counter()
    result = module.process_download_master(SimpleUploadedFile(name, raw, content_type="image/jpeg"))
    elapsed_ms = (time.perf_counter() - started) * 1000
    if result is None:
        return None, elapsed_ms
    result.seek(0)
    return result.read(), elapsed_ms


def reference(raw):
    """What both encoders are given to encode: oriented, sRGB, long edge <= 3600, Lanczos."""
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
    image = new_utils._normalize_to_srgb(image).convert("RGB")
    image.thumbnail((new_utils.DOWNLOAD_MAX_EDGE,) * 2, Image.Resampling.LANCZOS)
    return image


def decode(data):
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        return opened.convert("RGB"), opened.size, opened.getexif().get(274)


def mean_shift(ref, other):
    a, b = ImageStat.Stat(ref).mean, ImageStat.Stat(other).mean
    mad = ImageStat.Stat(ImageChops.difference(ref, other)).mean
    return [round(y - x, 2) for x, y in zip(a, b)], round(sum(mad) / 3, 2)


def pick_tiles(ref):
    """Four 300 px tiles worth looking at: most detail, smoothest gradient, darkest shadow, hardest edge."""
    luma = ref.convert("L")
    edges = luma.filter(ImageFilter.FIND_EDGES)
    tiles = []
    for top in range(0, ref.height - CROP + 1, CROP):
        for left in range(0, ref.width - CROP + 1, CROP):
            box = (left, top, left + CROP, top + CROP)
            tile = luma.crop(box)
            stat = ImageStat.Stat(tile)
            tiles.append({
                "box": box, "mean": stat.mean[0], "std": stat.stddev[0],
                "edge": ImageStat.Stat(edges.crop(box)).mean[0],
            })
    if not tiles:
        return []
    chosen = {}
    chosen["detail"] = max(tiles, key=lambda t: t["std"])
    smooth = [t for t in tiles if 40 < t["mean"] < 215 and t["std"] > 3] or tiles
    chosen["smooth"] = min(smooth, key=lambda t: t["std"])
    shadow = [t for t in tiles if t["std"] > 4] or tiles
    chosen["shadow"] = min(shadow, key=lambda t: t["mean"])
    chosen["edge"] = max(tiles, key=lambda t: t["edge"])
    return list(chosen.items())


def crop_strip(ref, old_image, new_image, tiles, path):
    if not tiles:
        return
    sheet = Image.new("RGB", (CROP * 3 + 40, (CROP + 18) * len(tiles)), "white")
    draw = ImageDraw.Draw(sheet)
    for row, (label, tile) in enumerate(tiles):
        top = row * (CROP + 18)
        draw.text((4, top + 3), f"{label} @ {tile['box'][0]},{tile['box'][1]}   reference | old | new (100%)", fill="black")
        for column, image in enumerate((ref, old_image or ref, new_image)):
            sheet.paste(image.crop(tile["box"]), (column * (CROP + 20), top + 18))
    sheet.save(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, help="directory holding the photos (read only)")
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--old", required=True, help="the pre-6-B apps/core/utils.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    old_utils = load_old(args.old)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, name in enumerate(args.files, start=1):
        source = Path(args.src) / name
        raw = source.read_bytes()
        original_hash = sha256(raw)
        stem = f"{index:02d}"

        ref = reference(raw)
        ref.save(out / f"{stem}-ref.ppm")

        runs = [run_master(new_utils, name, raw) for _ in range(3)]
        new_bytes = runs[0][0]
        times = [elapsed for _, elapsed in runs]
        reproducible = len({sha256(data) for data, _ in runs if data}) == 1

        old_bytes, old_ms = run_master(old_utils, name, raw)

        original_before_size = Image.open(io.BytesIO(raw)).size
        row = {
            "file": name, "original_bytes": len(raw), "original_dims": list(original_before_size),
            "original_sha256": original_hash[:16], "reproducible_3_runs": reproducible,
            "new_ms_median": round(statistics.median(times)), "new_ms_all": [round(t) for t in times],
            "old_ms": round(old_ms),
        }
        new_image = old_image = None
        if new_bytes:
            (out / f"{stem}-new.jpg").write_bytes(new_bytes)
            new_image, new_dims, new_orientation = decode(new_bytes)
            row.update(new_bytes=len(new_bytes), new_dims=list(new_dims), new_orientation_tag=new_orientation)
            shift, mad = mean_shift(ref, new_image)
            row.update(new_mean_shift_rgb=shift, new_mean_abs_diff=mad)
        else:
            row.update(new_bytes=None, new_dims=None)
        if old_bytes:
            (out / f"{stem}-old.jpg").write_bytes(old_bytes)
            old_image, old_dims, _ = decode(old_bytes)
            row.update(old_bytes=len(old_bytes), old_dims=list(old_dims))
            row["old_mean_abs_diff"] = mean_shift(ref, old_image)[1]
        else:
            row.update(old_bytes=None, old_dims=None)

        # Pillow fallback: cjpegli pointed at nothing (the same code path a missing binary takes).
        saved = new_utils.CJPEGLI_BIN
        new_utils.CJPEGLI_BIN = "/nonexistent/cjpegli"
        try:
            fb_bytes, fb_ms = run_master(new_utils, name, raw)
        finally:
            new_utils.CJPEGLI_BIN = saved
        if fb_bytes:
            _, fb_dims, _ = decode(fb_bytes)
            row.update(fallback_bytes=len(fb_bytes), fallback_dims=list(fb_dims), fallback_ms=round(fb_ms))
        else:
            row.update(fallback_bytes=None, fallback_dims=None, fallback_ms=round(fb_ms))

        if new_image is not None:
            crop_strip(ref, old_image, new_image, pick_tiles(ref), out / f"{stem}-crops.png")

        row["original_intact"] = sha256(source.read_bytes()) == original_hash
        rows.append(row)
        print(json.dumps(row), flush=True)

    (out / "results.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
