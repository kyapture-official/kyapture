"""Resumable, staged runner for the isolated JPEG benchmark.

This wrapper deliberately delegates every encode, normalization, quality
search, threshold, and metric decision to jpeg_download_benchmark.py.  Its
only responsibilities are deterministic screen selection, one-image worker
isolation, atomic completion markers, resumability, and final aggregation.
It never imports or changes the live application pipeline.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from PIL import Image, ImageStat

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
HARNESS = SCRIPT_DIR / "jpeg_download_benchmark.py"
sys.path.insert(0, str(SCRIPT_DIR))
import jpeg_download_benchmark as bench  # noqa: E402


ACTIVE_PROCESSES: set[subprocess.Popen[str]] = set()
ACTIVE_LOCK = threading.Lock()
ATOMIC_WRITE_LOCK = threading.Lock()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        with ATOMIC_WRITE_LOCK:
            for attempt in range(5):
                try:
                    os.replace(temp_name, path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        atomic_text(path, "")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        with ATOMIC_WRITE_LOCK:
            for attempt in range(5):
                try:
                    os.replace(temp_name, path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def tool_args(args: argparse.Namespace) -> list[str]:
    result: list[str] = []
    for name in ("mozjpeg_bin", "jpegli_bin", "ssimulacra2_bin", "butteraugli_bin"):
        value = getattr(args, name, None)
        if value:
            result += [f"--{name.replace('_', '-')}", str(value)]
    return result


def image_profile(path: Path) -> dict[str, Any]:
    """Small deterministic visual profile used only to choose screen strata."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        raw_width, raw_height = image.size
        image.thumbnail((256, 256), Image.Resampling.BILINEAR)
        stat = ImageStat.Stat(image)
        pixels = list(image.getdata())
    means = stat.mean
    lumas = [(0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 for r, g, b in pixels]
    variance = ImageStat.Stat(image.convert("L")).var[0] / (255 * 255)
    bright = sum(v > 0.92 for v in lumas) / max(1, len(lumas))
    dark = sum(v < 0.10 for v in lumas) / max(1, len(lumas))
    green = sum(g > r * 1.08 and g > b * 1.04 and g > 70 for r, g, b in pixels) / max(1, len(pixels))
    blue = sum(b > r * 1.12 and b > g * 1.02 and b > 90 for r, g, b in pixels) / max(1, len(pixels))
    skin = sum(
        r > 70 and r > g * 1.08 and g > b * 1.15 and (r - b) > 25 and (r - g) < 110
        for r, g, b in pixels
    ) / max(1, len(pixels))
    return {
        "path": str(path), "filename": path.name, "bytes": path.stat().st_size,
        "width": raw_width, "height": raw_height, "long_edge": max(raw_width, raw_height),
        "orientation": "landscape" if raw_width >= raw_height else "portrait",
        "mean_luma": sum(lumas) / max(1, len(lumas)), "variance": variance,
        "bright_fraction": bright, "dark_fraction": dark, "green_fraction": green,
        "blue_fraction": blue, "skin_fraction": skin,
    }


def choose_screen(paths: list[Path], count: int) -> tuple[list[Path], list[dict[str, Any]]]:
    profiles = [image_profile(path) for path in paths]
    used: set[str] = set()
    selected: list[Path] = []

    def choose(label: str, score) -> None:
        if len(selected) >= count:
            return
        candidates = sorted(
            (profile for profile in profiles if profile["path"] not in used),
            key=lambda profile: (-float(score(profile)), profile["filename"].casefold()),
        )
        if candidates:
            profile = candidates[0]
            used.add(profile["path"])
            selected.append(Path(profile["path"]))
            profile["screen_strata"] = profile.get("screen_strata", []) + [label]

    # These are intentionally transparent image-stat heuristics, not claims
    # about the photographer's subject matter. The final report lists them.
    choose("portrait_skin", lambda p: p["skin_fraction"] * 4 + (1 if p["orientation"] == "portrait" else 0))
    choose("low_light_high_iso_proxy", lambda p: p["dark_fraction"] * 3 + p["variance"])
    choose("foliage_proxy", lambda p: p["green_fraction"] * 5 + p["variance"])
    choose("sky_gradient_proxy", lambda p: p["blue_fraction"] * 4 + (1 - p["variance"]))
    choose("fine_texture_proxy", lambda p: p["variance"] * 4 + p["green_fraction"])
    choose("architecture_proxy", lambda p: p["variance"] * 2 + (1 if p["orientation"] == "landscape" else 0))
    choose("bright_highlights", lambda p: p["bright_fraction"] * 5)
    choose("dark_shadows", lambda p: p["dark_fraction"] * 5)
    choose("landscape_orientation", lambda p: 1 if p["orientation"] == "landscape" else 0)
    choose("portrait_orientation", lambda p: 1 if p["orientation"] == "portrait" else 0)
    choose("small_original", lambda p: 1 / max(1, p["long_edge"]))
    choose("large_original", lambda p: p["long_edge"])

    remaining = sorted((p for p in profiles if p["path"] not in used), key=lambda p: p["filename"].casefold())
    while len(selected) < min(count, len(profiles)) and remaining:
        # Evenly spaced by sorted filename after the required strata have been
        # covered, keeping the selection stable across reruns.
        position = round((len(selected) - 12) * (len(remaining) - 1) / max(1, count - 13)) if len(selected) >= 12 else 0
        position = max(0, min(len(remaining) - 1, position))
        profile = remaining.pop(position)
        used.add(profile["path"])
        profile["screen_strata"] = profile.get("screen_strata", []) + ["deterministic_fill"]
        selected.append(Path(profile["path"]))
    selected_profiles = [next(p for p in profiles if p["path"] == str(path)) for path in selected]
    return selected, selected_profiles


def run_child(command: list[str], env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    with ACTIVE_LOCK:
        ACTIVE_PROCESSES.add(process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise RuntimeError(f"child benchmark timed out after {timeout}s\n{stdout}\n{stderr}")
    finally:
        with ACTIVE_LOCK:
            ACTIVE_PROCESSES.discard(process)


def stop_children() -> None:
    with ACTIVE_LOCK:
        processes = list(ACTIVE_PROCESSES)
    for process in processes:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass


def write_pixieset_reference(path: Path, pairs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    reference = {
        pair["original_filename"]: {
            "original_bytes": pair["original_bytes"],
            "pixieset_bytes": pair["pixieset_bytes"],
        }
        for pair in pairs
    }
    atomic_json(path, reference)
    return reference


def config_hash(args: argparse.Namespace, selected_count: int, include_timeout: bool = False) -> str:
    payload = {
        "harness_sha256": hashlib.sha256(HARNESS.read_bytes()).hexdigest(),
        "thresholds": args.thresholds, "quality_min": args.quality_min,
        "quality_max": args.quality_max,
        "worst_threshold": args.worst_threshold, "selected_count": selected_count,
        "tools": {key: str(getattr(args, key, "")) for key in ("mozjpeg_bin", "jpegli_bin", "ssimulacra2_bin")},
    }
    if include_timeout:
        payload["timeout"] = args.timeout_seconds
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_child(attempt: Path, filename: str, thresholds: tuple[float, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    results_path = attempt / "results.csv"
    candidates_path = attempt / "candidate-results.csv"
    if not results_path.is_file() or not candidates_path.is_file():
        raise ValueError("missing final child CSVs")
    with results_path.open(newline="", encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    with candidates_path.open(newline="", encoding="utf-8") as handle:
        candidates = list(csv.DictReader(handle))
    expected = 1 + len(thresholds) * 2
    if len(results) != expected:
        raise ValueError(f"expected {expected} selected rows, found {len(results)}")
    methods = {row.get("method") for row in results}
    if "current" not in methods or not {"mozjpeg", "jpegli"}.issubset(methods):
        raise ValueError("not all required methods completed")
    for row in results:
        if row.get("ssimulacra2") in (None, ""):
            raise ValueError(f"missing SSIMULACRA2 for {row.get('method')} {row.get('threshold')}")
        output_path = row.get("output_path")
        if row.get("status") == "selected":
            if not output_path or not Path(output_path).is_file():
                raise ValueError("selected output is missing")
            if int(row["output_bytes"]) != Path(output_path).stat().st_size:
                raise ValueError("selected output size does not match CSV")
    marker = {
        "status": "complete", "filename": filename,
        "results_csv": str(results_path), "candidate_results_csv": str(candidates_path),
        "result_count": len(results), "candidate_count": len(candidates),
    }
    return results, candidates, marker


def find_valid_marker(work: Path, key: str, expected_hashes: set[str], source_bytes: int) -> Path | None:
    image_dir = work / key
    if not image_dir.is_dir():
        return None
    for marker_path in sorted(image_dir.glob("attempt-*/complete.json"), reverse=True):
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if marker.get("status") != "complete" or marker.get("config_hash") not in expected_hashes or marker.get("source_bytes") != source_bytes:
                continue
            attempt = marker_path.parent
            validate_child(attempt, marker["filename"], tuple(float(v) for v in marker["thresholds"]))
            return marker_path
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


def next_attempt(work: Path, key: str) -> Path:
    image_dir = work / key
    image_dir.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.name.split("-", 1)[1]) for p in image_dir.glob("attempt-*") if p.name.split("-", 1)[-1].isdigit()]
    attempt = image_dir / f"attempt-{max(numbers, default=0) + 1:03d}"
    attempt.mkdir()
    return attempt


def worker(item: dict[str, Any], args: argparse.Namespace, root: Path, reference_json: Path, expected_hashes: set[str], expected_hash: str) -> dict[str, Any]:
    source = Path(item["source_path"])
    key = item["key"]
    if args.resume:
        marker_path = find_valid_marker(root / "work", key, expected_hashes, source.stat().st_size)
        if marker_path:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            results, candidates, _ = validate_child(marker_path.parent, source.name, tuple(float(v) for v in marker["thresholds"]))
            return {"item": item, "attempt": str(marker_path.parent), "results": results, "candidates": candidates, "resumed": True}
    attempt = next_attempt(root / "work", key)
    staged_input = attempt / "input"
    staged_input.mkdir()
    shutil.copy2(source, staged_input / source.name)
    command = [sys.executable, str(HARNESS), "--input-dir", str(staged_input), "--pixieset-reference", str(reference_json), "--output-dir", str(attempt)]
    command += tool_args(args) + ["--thresholds", args.thresholds, "--quality-min", str(args.quality_min), "--quality-max", str(args.quality_max), "--timeout-seconds", str(args.timeout_seconds), "--worst-threshold", str(args.worst_threshold)]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    jpegli_tools = Path(args.jpegli_bin).resolve().parent if args.jpegli_bin else None
    if jpegli_tools:
        env["PATH"] = str(jpegli_tools) + os.pathsep + env.get("PATH", "")
    child_timeout = max(300, args.timeout_seconds * max(1, len(args.thresholds.split(","))) * 4)
    returncode, stdout, stderr = run_child(command, env, child_timeout)
    atomic_text(attempt / "child.stdout.txt", stdout)
    atomic_text(attempt / "child.stderr.txt", stderr)
    if returncode != 0:
        raise RuntimeError(f"child failed for {source.name} with exit code {returncode}: {stderr[-1000:]}")
    thresholds = tuple(float(v.strip()) for v in args.thresholds.split(",") if v.strip())
    results, candidates, marker = validate_child(attempt, source.name, thresholds)
    marker.update({"config_hash": expected_hash, "source_bytes": source.stat().st_size, "thresholds": list(thresholds), "completed_at": time.time()})
    # This is the only completion signal. It is written last and atomically;
    # a power loss before this point cannot be mistaken for completed work.
    atomic_json(attempt / "complete.json", marker)
    return {"item": item, "attempt": str(attempt), "results": results, "candidates": candidates, "resumed": False}


def load_completed(root: Path, items: list[dict[str, Any]], args: argparse.Namespace, reference_json: Path, expected_hashes: set[str], expected_hash: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    all_results: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    completed_items: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="jpeg-benchmark") as executor:
        futures = {executor.submit(worker, item, args, root, reference_json, expected_hashes, expected_hash): item for item in items}
        try:
            for future in as_completed(futures):
                item = futures[future]
                try:
                    payload = future.result()
                    all_results.extend(payload["results"])
                    all_candidates.extend(payload["candidates"])
                    completed_items.append(item)
                    elapsed = time.time() - args._started
                    atomic_json(root / "progress.json", {"status": "running", "completed": len(completed_items), "total": len(items), "elapsed_seconds": elapsed, "last_filename": item["filename"], "resumed": sum(1 for x in completed_items if x is item)})
                    print(f"completed {len(completed_items)}/{len(items)} {item['filename']} ({elapsed/60:.1f} min)", flush=True)
                except Exception as exc:
                    errors.append(f"{item['filename']}: {exc}")
                    print(f"FAILED {item['filename']}: {exc}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            stop_children()
            for future in futures:
                future.cancel()
            atomic_json(root / "progress.json", {"status": "interrupted", "completed": len(completed_items), "total": len(items), "elapsed_seconds": time.time() - args._started, "resume_required": True})
            raise
    return all_results, all_candidates, completed_items, errors


def build_aggregates(results: list[dict[str, Any]], candidates: list[dict[str, Any]], items: list[dict[str, Any]], args: argparse.Namespace, root: Path, pixieset: dict[str, dict[str, int]]) -> None:
    thresholds = tuple(float(v.strip()) for v in args.thresholds.split(",") if v.strip())
    integer_fields = {"input_bytes", "reference_bytes", "reference_width", "reference_height", "output_bytes", "output_width", "output_height", "selected_quality"}
    float_fields = {"threshold", "percentage_reduction", "compression_ratio", "ssimulacra2", "psnr", "butteraugli", "encode_time_ms"}
    for row in results:
        for field in integer_fields:
            if row.get(field) not in (None, ""):
                row[field] = int(float(row[field]))
        for field in float_fields:
            if row.get(field) not in (None, ""):
                row[field] = float(row[field])
        item = next((x for x in items if x["filename"] == row.get("filename")), None)
        if item:
            row["source_path"] = item["source_path"]
    results.sort(key=lambda row: (row.get("filename", "").casefold(), row.get("method", ""), str(row.get("threshold", ""))))
    candidates.sort(key=lambda row: (row.get("filename", "").casefold(), row.get("method", ""), str(row.get("quality", ""))))
    image_metadata: list[dict[str, Any]] = []
    for item in items:
        rows = [row for row in results if row.get("filename") == item["filename"] and row.get("method") == "current"]
        if rows:
            row = rows[0]
            image_metadata.append({"source_path": Path(item["source_path"]), "original_bytes": int(row["input_bytes"]), "reference_bytes": int(row["reference_bytes"]), "reference_width": int(row["reference_width"]), "reference_height": int(row["reference_height"]), "reference_path": Path(row["reference_path"]), "metric_reference_path": Path(row["reference_path"]), "stem": Path(row["reference_path"]).stem})
    summary: list[dict[str, Any]] = []
    methods = sorted({row.get("method") for row in results})
    for method in methods:
        method_rows = [row for row in results if row.get("method") == method and bench.threshold_matches(row.get("threshold"), args.worst_threshold)]
        if method_rows:
            item = bench.aggregate(method_rows); item["median_output_bytes"] = bench.statistics.median(bench.numeric_values(method_rows, "output_bytes")) if bench.numeric_values(method_rows, "output_bytes") else None; summary.append(item)
        for threshold in thresholds:
            rows = [row for row in results if row.get("method") == method and bench.threshold_matches(row.get("threshold"), threshold, include_current=False)]
            if rows:
                item = bench.aggregate(rows); item["median_output_bytes"] = bench.statistics.median(bench.numeric_values(rows, "output_bytes")) if bench.numeric_values(rows, "output_bytes") else None; summary.append(item)
    pairwise = bench.build_pairwise_rows(results, args.worst_threshold, pixieset)
    focus = [row for row in results if bench.threshold_matches(row.get("threshold"), args.worst_threshold)]
    worst: list[dict[str, Any]] = []
    for row in sorted(focus, key=lambda r: float(r.get("ssimulacra2") or 10**9))[:10]:
        copy = dict(row); copy["analysis"] = "worst_perceptual_score"; worst.append(copy)
    for row in sorted(focus, key=lambda r: float(r.get("percentage_reduction") or 10**9))[:10]:
        copy = dict(row); copy["analysis"] = "largest_size_regression"; worst.append(copy)
    atomic_csv(root / "results.csv", results); atomic_csv(root / "candidate-results.csv", candidates); atomic_csv(root / "summary.csv", summary); atomic_csv(root / "pairwise.csv", pairwise); atomic_csv(root / "worst-cases.csv", worst)
    selected_paths = {(row["filename"], row["method"]): Path(row["output_path"]) for row in results if row.get("output_path") and Path(row["output_path"]).is_file()}
    contact_sheet = None
    if args.contact_sheet and all(any(row.get("filename") == item["filename"] and row.get("method") == "current" for row in results) for item in items):
        contact_sheet = bench.make_contact_sheet(results, root, args.contact_sheet_count, args.worst_threshold, selected_paths)
    tools = bench.audit_tools(args)
    bench.render_report(root / "report.md", tools, image_metadata, summary, results, pairwise, pixieset, contact_sheet, args.worst_threshold)


def write_screen_report(root: Path, results: list[dict[str, Any]], items: list[dict[str, Any]], profiles: list[dict[str, Any]], args: argparse.Namespace, started: float, errors: list[str]) -> None:
    elapsed = time.time() - started
    completed = len({row.get("filename") for row in results if row.get("filename")})
    projection = elapsed * 103 / completed if completed else None
    lines = ["# KYAPTURE quick-screen execution report", "", f"Elapsed seconds: **{elapsed:.1f}**", f"Images completed: **{completed}/{len(items)}**", f"Projected 103-image time at this observed throughput: **{projection/60:.1f} minutes**" if projection else "Projected full time: unavailable", "", "The screen uses transparent image-stat strata as a deterministic proxy for the requested scene categories; it does not assert semantic labels. SSIMULACRA2 remains primary.", "", "| Encoder | Threshold | Images | Median bytes | Median SSIM2 | P5 SSIM2 | Worst SSIM2 | P95 encode ms |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    thresholds = tuple(float(v.strip()) for v in args.thresholds.split(",") if v.strip())
    for method in ("current", "mozjpeg", "jpegli"):
        for threshold in (args.worst_threshold, *thresholds):
            rows = [row for row in results if row.get("method") == method and bench.threshold_matches(row.get("threshold"), threshold)]
            if not rows:
                continue
            summary = bench.aggregate(rows); sizes = bench.numeric_values(rows, "output_bytes")
            lines.append(f"| {method} | {threshold:g} | {len(rows)} | {bench.fmt(bench.statistics.median(sizes) if sizes else None)} | {bench.fmt(summary['median_ssimulacra2'])} | {bench.fmt(summary['p5_ssimulacra2'])} | {bench.fmt(summary['worst_ssimulacra2'])} | {bench.fmt(summary['p95_encode_time_ms'])} |")
    lines += ["", "## Elimination gate", "", "No encoder is safely eliminated by this screen unless it is consistently no smaller, no better in worst-case SSIMULACRA2, and no faster than its alternative. The conservative result is: **retain Current, MozJPEG, and jpegli for Phase B** unless a clearly dominant and consistent result is measured.", ""]
    if errors:
        lines += ["## Incomplete images", "", *[f"- {error}" for error in errors], ""]
    lines += ["## Selected strata", "", "| File | Strata | Dimensions | Bytes |", "|---|---|---:|---:|"]
    for profile in profiles:
        lines.append(f"| {profile['filename']} | {', '.join(profile.get('screen_strata', []))} | {profile['width']}x{profile['height']} | {profile['bytes']} |")
    atomic_text(root / "quick-screen-summary.md", "\n".join(lines) + "\n")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", required=True, type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick-screen", action="store_true")
    mode.add_argument("--full", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--pixieset-dir", required=True, type=Path)
    p.add_argument("--mozjpeg-bin", required=True)
    p.add_argument("--jpegli-bin", required=True)
    p.add_argument("--ssimulacra2-bin", required=True)
    p.add_argument("--butteraugli-bin")
    p.add_argument("--thresholds", default="80,85,88,90")
    p.add_argument("--quality-min", type=int, default=30)
    p.add_argument("--quality-max", type=int, default=100)
    p.add_argument("--timeout-seconds", type=int, default=120)
    p.add_argument("--worst-threshold", type=float, default=88)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--quick-count", type=int, default=24)
    p.add_argument("--contact-sheet", action="store_true")
    p.add_argument("--contact-sheet-count", type=int, default=20)
    return p


def main() -> int:
    args = parser().parse_args()
    if not args.input_dir.is_dir() or not args.pixieset_dir.is_dir():
        raise SystemExit("input and Pixieset directories must exist")
    if args.workers < 1 or args.workers > 4:
        raise SystemExit("--workers must be between 1 and 4; 2 is the conservative Windows default")
    root = (args.output_dir or ROOT / "benchmark-artifacts" / ("jpeg-quick-screen" if args.quick_screen else "jpeg-real-full-resumable")).resolve()
    if root.exists() and (root / "work").exists() and not args.resume:
        raise SystemExit(f"{root} already contains benchmark work; use --resume to continue without discarding it")
    root.mkdir(parents=True, exist_ok=True)
    args._started = time.time()
    tools = bench.audit_tools(args)
    missing = [tool.name for tool in tools if tool.name in {"MozJPEG cjpeg", "jpegli cjpegli", "SSIMULACRA2"} and not tool.available]
    atomic_json(root / "tool-availability.json", [{"name": tool.name, "path": tool.path, "version": tool.version, "error": tool.error} for tool in tools])
    if missing:
        raise SystemExit("Required benchmark tools missing: " + ", ".join(missing))
    preflight_dir = root / "preflight"
    try:
        preflight = bench.preflight_pixieset(args.input_dir, args.pixieset_dir, preflight_dir)
    except bench.PreflightError as exc:
        raise SystemExit(str(exc)) from exc
    pixieset = write_pixieset_reference(root / "pixieset-reference.json", preflight["pairs"])
    all_paths = sorted(path for path in args.input_dir.rglob("*") if path.is_file() and path.suffix.lower() in bench.JPEG_EXTENSIONS)
    if args.quick_screen:
        paths, profiles = choose_screen(all_paths, args.quick_count)
        atomic_json(root / "quick-screen-selection.json", profiles)
    else:
        paths, profiles = all_paths, []
    items = [{"filename": path.name, "source_path": str(path.resolve()), "key": bench.safe_stem(path, index)} for index, path in enumerate(paths, 1)]
    expected_hash = config_hash(args, len(items))
    expected_hashes = {expected_hash, config_hash(args, len(items), include_timeout=True)}
    atomic_json(root / "run-config.json", {"mode": "quick-screen" if args.quick_screen else "full", "expected_hash": expected_hash, "images": [item["filename"] for item in items], "started_at": args._started, "workers": args.workers})
    try:
        results, candidates, completed, errors = load_completed(root, items, args, root / "pixieset-reference.json", expected_hashes, expected_hash)
    except KeyboardInterrupt:
        print(f"Interrupted safely. Completed image markers remain under {root / 'work'}. Re-run with --resume --output-dir \"{root}\".", file=sys.stderr)
        return 130
    build_aggregates(results, candidates, items, args, root, pixieset)
    atomic_json(root / "progress.json", {"status": "complete" if len(completed) == len(items) and not errors else "partial", "completed": len(completed), "total": len(items), "elapsed_seconds": time.time() - args._started, "errors": errors})
    if args.quick_screen:
        write_screen_report(root, results, items, profiles, args, args._started, errors)
    if errors:
        atomic_text(root / "errors.txt", "\n".join(errors) + "\n")
    print(f"elapsed_seconds={time.time() - args._started:.1f}")
    print(f"images_completed={len(completed)}/{len(items)}")
    print(f"report={root / 'report.md'}")
    if args.quick_screen:
        print(f"quick_screen_summary={root / 'quick-screen-summary.md'}")
    return 0 if not errors and len(completed) == len(items) else 2


if __name__ == "__main__":
    raise SystemExit(main())
