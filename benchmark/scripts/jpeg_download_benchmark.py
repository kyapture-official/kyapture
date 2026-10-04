"""Read-only JPEG download-master benchmark.

This file is deliberately isolated from the application package.  It reads
source JPEGs, creates benchmark-only reference/candidate files, and writes
CSV/Markdown reports.  It never opens Django's database, touches MediaAsset,
or writes to the application's media directory.

The benchmark's primary metric is SSIMULACRA2.  If no SSIMULACRA2 executable
is available, encoders can still be smoke-tested and PSNR is recorded as a
secondary diagnostic, but no perceptual-quality conclusion is made.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
MAX_EDGE = 3600
DEFAULT_THRESHOLDS = (80.0, 85.0, 88.0, 90.0)
JPEG_EXTENSIONS = {".jpg", ".jpeg"}


@dataclass
class Tool:
    name: str
    command: str | None
    path: str | None
    version: str | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.path is not None


def find_executable(explicit: str | None, names: Iterable[str]) -> str | None:
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.is_file():
            return str(explicit_path.resolve())
        resolved = shutil.which(explicit)
        if resolved:
            return resolved
        return None
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def command_version(path: str | None) -> tuple[str | None, str | None]:
    if not path:
        return None, None
    for args in (("--version",), ("-version",)):
        try:
            completed = subprocess.run(
                [path, *args], capture_output=True, text=True, timeout=5, check=False
            )
            output = (completed.stdout or completed.stderr).strip()
            if output:
                return output.splitlines()[0][:240], None
        except Exception as exc:  # pragma: no cover - platform-specific executable errors
            last_error = str(exc)
    return None, locals().get("last_error")


def audit_tools(args: argparse.Namespace) -> list[Tool]:
    tools: list[Tool] = []
    try:
        import PIL

        pillow_detail = f"Pillow {PIL.__version__} ({sys.executable})"
        tools.append(Tool("Pillow/Python image pipeline", "python -c 'import PIL'", sys.executable, pillow_detail))
    except Exception as exc:
        tools.append(Tool("Pillow/Python image pipeline", "python -c 'import PIL'", None, error=str(exc)))

    specs = (
        ("MozJPEG cjpeg", "cjpeg", args.mozjpeg_bin, ("cjpeg", "mozjpeg-cjpeg")),
        ("jpegli cjpegli", "cjpegli", args.jpegli_bin, ("cjpegli", "jpegli-cjpeg")),
        ("SSIMULACRA2", "ssimulacra2", args.ssimulacra2_bin, ("ssimulacra2", "ssimulacra2_bin")),
        ("Butteraugli", "butteraugli", args.butteraugli_bin, ("butteraugli",)),
    )
    for label, command, explicit, names in specs:
        path = find_executable(explicit, names)
        version, error = command_version(path)
        tools.append(Tool(label, command, path, version, error))

    docker_path = find_executable(None, ("docker",))
    docker_version, docker_error = command_version(docker_path)
    tools.append(Tool("Docker host", "docker", docker_path, docker_version, docker_error))
    return tools


def normalize_to_srgb(image):
    """Return an oriented, opaque sRGB copy without source metadata."""
    from PIL import ImageCms

    image = image.copy()
    icc_bytes = image.info.get("icc_profile")
    if icc_bytes:
        try:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
            srgb_profile = ImageCms.createProfile("sRGB")
            image = ImageCms.profileToProfile(
                image, source_profile, srgb_profile, outputMode="RGB"
            )
        except Exception:
            image = image.convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")
    else:
        image = image.copy()
    image.info.pop("icc_profile", None)
    return image


def make_reference(source_path: Path):
    from PIL.ImageOps import exif_transpose

    with _open_image(source_path) as source:
        oriented = exif_transpose(source)
        reference = normalize_to_srgb(oriented)
    if max(reference.size) > MAX_EDGE:
        reference.thumbnail((MAX_EDGE, MAX_EDGE), resample=_resampling_lanczos())
    reference.info.clear()
    return reference


def _open_image(path: Path):
    from PIL import Image

    return Image.open(path)


def _resampling_lanczos():
    from PIL import Image

    return Image.Resampling.LANCZOS


def save_reference(reference, png_path: Path, ppm_path: Path) -> None:
    reference.save(png_path, format="PNG", optimize=True)
    reference.save(ppm_path, format="PPM")


def psnr(reference, candidate) -> float | None:
    from PIL import ImageChops, ImageStat

    if reference.size != candidate.size:
        return None
    candidate_rgb = candidate.convert("RGB")
    difference = ImageChops.difference(reference.convert("RGB"), candidate_rgb)
    channel_rms = ImageStat.Stat(difference).rms
    mse = sum(value * value for value in channel_rms) / len(channel_rms)
    if mse == 0:
        return float("inf")
    return 20 * math.log10(255 / math.sqrt(mse))


def parse_float(text: str) -> float | None:
    values = re.findall(r"(?<![A-Za-z0-9_])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
    if not values:
        return None
    return float(values[-1])


def run_metric(
    binary: str, reference_path: Path, candidate_path: Path, timeout: int,
    cache: dict[tuple[str, str, str], float] | None = None,
) -> float:
    cache_key = None
    if cache is not None:
        cache_key = (
            str(Path(binary).resolve()),
            hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        )
        if cache_key in cache:
            return cache[cache_key]
    completed = subprocess.run(
        [binary, str(reference_path), str(candidate_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    value = parse_float(output)
    if completed.returncode != 0 or value is None:
        raise RuntimeError(
            f"metric command failed ({completed.returncode}): {output[-500:]}"
        )
    score = value * 100 if binary.lower().endswith("ssimulacra2") and value <= 1.2 else value
    if cache is not None and cache_key is not None:
        cache[cache_key] = score
    return score


def run_butteraugli(binary: str | None, reference_path: Path, candidate_path: Path, timeout: int) -> float | None:
    if not binary:
        return None
    try:
        return run_metric(binary, reference_path, candidate_path, timeout)
    except Exception:
        return None


def safe_stem(path: Path, index: int) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "image"
    digest = hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:8]
    return f"{index:04d}_{raw[:ninety()]}_{digest}"


def ninety() -> int:
    # Kept as a function so the filename cap is conspicuous and easy to alter.
    return 80


def parse_csv_or_json(path: Path) -> dict[str, dict[str, int]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    else:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and "rows" in payload:
            rows = payload["rows"]
        elif isinstance(payload, dict):
            rows = [dict(value, filename=key) for key, value in payload.items()]
        else:
            rows = payload
    parsed: dict[str, dict[str, int]] = {}
    for row in rows:
        filename = str(row.get("filename", "")).strip()
        if not filename:
            continue
        try:
            parsed[filename] = {
                "original_bytes": int(row["original_bytes"]),
                "pixieset_bytes": int(row["pixieset_bytes"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Pixieset reference row for {filename!r}: {row}") from exc
    return parsed


class PreflightError(RuntimeError):
    """Raised when the two folders cannot be paired safely."""


def filename_key(name: str) -> str:
    return name.casefold()


def normalized_filename_key(name: str) -> str:
    """Deterministic filename normalization; never uses folder ordering."""
    return re.sub(r"\s+", "", name).casefold()


def inspect_dataset_file(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "filename": path.name,
        "path": str(path),
        "bytes": path.stat().st_size,
        "suffix": path.suffix.lower(),
        "format": None,
        "is_jpeg": False,
        "width": None,
        "height": None,
        "raw_width": None,
        "raw_height": None,
        "error": None,
    }
    try:
        from PIL.ImageOps import exif_transpose

        with _open_image(path) as image:
            info["format"] = image.format
            info["raw_width"], info["raw_height"] = image.size
            oriented = exif_transpose(image)
            info["width"], info["height"] = oriented.size
            info["is_jpeg"] = image.format == "JPEG" and path.suffix.lower() in JPEG_EXTENSIONS
    except Exception as exc:
        info["error"] = str(exc)
    return info


def dataset_inventory(directory: Path) -> dict[str, Any]:
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    entries = [inspect_dataset_file(path) for path in files]
    jpeg_entries = [entry for entry in entries if Path(entry["path"]).suffix.lower() in JPEG_EXTENSIONS]
    exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in jpeg_entries:
        exact_groups[filename_key(entry["filename"])].append(entry)
        normalized_groups[normalized_filename_key(entry["filename"])].append(entry)
    return {
        "directory": str(directory),
        "total_files": len(files),
        "jpeg_count": len(jpeg_entries),
        "non_jpeg_files": [entry["filename"] for entry in entries if entry not in jpeg_entries],
        "entries": entries,
        "jpeg_entries": jpeg_entries,
        "duplicate_filenames": [
            sorted(entry["filename"] for entry in group)
            for group in exact_groups.values()
            if len(group) > 1
        ],
        "duplicate_normalized_filenames": [
            sorted(entry["filename"] for entry in group)
            for group in normalized_groups.values()
            if len(group) > 1
        ],
        "exact_groups": exact_groups,
        "normalized_groups": normalized_groups,
    }


def expected_reference_dimensions(width: int | None, height: int | None) -> tuple[int | None, int | None]:
    if not width or not height:
        return None, None
    if max(width, height) <= MAX_EDGE:
        return width, height
    scale = MAX_EDGE / max(width, height)
    return round(width * scale), round(height * scale)


def preflight_pixieset(original_dir: Path, pixieset_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Build and persist a strict, filename-based original/Pixieset audit."""
    original = dataset_inventory(original_dir)
    pixieset = dataset_inventory(pixieset_dir)
    errors: list[str] = []
    if original["duplicate_filenames"]:
        errors.append("duplicate original filenames")
    if pixieset["duplicate_filenames"]:
        errors.append("duplicate Pixieset filenames")
    if original["duplicate_normalized_filenames"]:
        errors.append("ambiguous whitespace-normalized original filenames")
    if pixieset["duplicate_normalized_filenames"]:
        errors.append("ambiguous whitespace-normalized Pixieset filenames")
    if original["non_jpeg_files"]:
        errors.append("non-JPEG files in original dataset")
    if pixieset["non_jpeg_files"]:
        errors.append("non-JPEG files in Pixieset dataset")
    invalid_originals = [entry["filename"] for entry in original["jpeg_entries"] if not entry["is_jpeg"]]
    invalid_pixieset = [entry["filename"] for entry in pixieset["jpeg_entries"] if not entry["is_jpeg"]]
    if invalid_originals:
        errors.append("files with invalid/non-JPEG original contents")
    if invalid_pixieset:
        errors.append("files with invalid/non-JPEG Pixieset contents")

    used_pixieset: set[str] = set()
    pairs: list[dict[str, Any]] = []
    unmatched_originals: list[str] = []
    for original_entry in original["jpeg_entries"]:
        # Exact lookup against the Pixieset inventory, while preserving the
        # original's exact filename as the report key.
        exact_pix = [
            entry for entry in pixieset["jpeg_entries"]
            if filename_key(entry["filename"]) == filename_key(original_entry["filename"])
        ]
        match_type = "exact"
        candidates = exact_pix
        if not candidates:
            match_type = "whitespace-normalized"
            candidates = pixieset["normalized_groups"].get(
                normalized_filename_key(original_entry["filename"]), []
            )
        candidates = [entry for entry in candidates if entry["path"] not in used_pixieset]
        if len(candidates) != 1:
            unmatched_originals.append(original_entry["filename"])
            continue
        pix_entry = candidates[0]
        used_pixieset.add(pix_entry["path"])
        expected_width, expected_height = expected_reference_dimensions(
            original_entry["width"], original_entry["height"]
        )
        original_long = max(original_entry["width"] or 0, original_entry["height"] or 0)
        pixieset_long = max(pix_entry["width"] or 0, pix_entry["height"] or 0)
        pairs.append({
            "original_filename": original_entry["filename"],
            "pixieset_filename": pix_entry["filename"],
            "match_type": match_type,
            "original_bytes": original_entry["bytes"],
            "pixieset_bytes": pix_entry["bytes"],
            "original_format": original_entry["format"],
            "pixieset_format": pix_entry["format"],
            "original_width": original_entry["width"],
            "original_height": original_entry["height"],
            "pixieset_width": pix_entry["width"],
            "pixieset_height": pix_entry["height"],
            "expected_reference_width": expected_width,
            "expected_reference_height": expected_height,
            "original_long_edge": original_long,
            "pixieset_long_edge": pixieset_long,
            "pixieset_matches_3600_contract": (
                pix_entry["is_jpeg"]
                and pixieset_long == max(expected_width or 0, expected_height or 0)
            ),
            "original_path": original_entry["path"],
            "pixieset_path": pix_entry["path"],
        })
    unmatched_pixieset = [
        entry["filename"] for entry in pixieset["jpeg_entries"] if entry["path"] not in used_pixieset
    ]
    if unmatched_originals:
        errors.append("unmatched original filenames")
    if unmatched_pixieset:
        errors.append("unmatched Pixieset filenames")
    if len(original["jpeg_entries"]) != len(pixieset["jpeg_entries"]):
        errors.append("original/Pixieset JPEG counts differ")

    preflight = {
        "original_directory": str(original_dir),
        "pixieset_directory": str(pixieset_dir),
        "original_count": len(original["jpeg_entries"]),
        "pixieset_count": len(pixieset["jpeg_entries"]),
        "matched_count": len(pairs),
        "exact_match_count": sum(pair["match_type"] == "exact" for pair in pairs),
        "normalized_match_count": sum(pair["match_type"] == "whitespace-normalized" for pair in pairs),
        "missing_originals": unmatched_originals,
        "missing_pixieset_files": unmatched_pixieset,
        "duplicate_original_filenames": original["duplicate_filenames"],
        "duplicate_pixieset_filenames": pixieset["duplicate_filenames"],
        "duplicate_normalized_original_filenames": original["duplicate_normalized_filenames"],
        "duplicate_normalized_pixieset_filenames": pixieset["duplicate_normalized_filenames"],
        "invalid_originals": invalid_originals,
        "invalid_pixieset_files": invalid_pixieset,
        "non_jpeg_original_files": original["non_jpeg_files"],
        "non_jpeg_pixieset_files": pixieset["non_jpeg_files"],
        "contract_matches": sum(bool(pair["pixieset_matches_3600_contract"]) for pair in pairs),
        "contract_mismatches": sum(not pair["pixieset_matches_3600_contract"] for pair in pairs),
        "pairs": pairs,
        "errors": errors,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "preflight.json").write_text(
        json.dumps(preflight, indent=2), encoding="utf-8"
    )
    csv_write(output_dir / "preflight.csv", pairs)
    lines = [
        "# KYAPTURE Pixieset preflight",
        "",
        "Filename-based audit only. No arbitrary ordering was used.",
        "",
        f"- Original count: **{preflight['original_count']}**",
        f"- Pixieset count: **{preflight['pixieset_count']}**",
        f"- Matched count: **{preflight['matched_count']}**",
        f"- Exact filename matches: **{preflight['exact_match_count']}**",
        f"- Whitespace-normalized matches: **{preflight['normalized_match_count']}**",
        f"- Pixieset files matching the expected no-upscale/3600px contract: **{preflight['contract_matches']}**",
        f"- Pixieset files not matching that dimension contract: **{preflight['contract_mismatches']}**",
        "",
        f"Missing originals: {', '.join(preflight['missing_originals']) or 'none'}",
        f"Missing Pixieset files: {', '.join(preflight['missing_pixieset_files']) or 'none'}",
        f"Duplicate original filenames: {preflight['duplicate_original_filenames'] or 'none'}",
        f"Duplicate Pixieset filenames: {preflight['duplicate_pixieset_filenames'] or 'none'}",
        f"Invalid original JPEGs: {', '.join(preflight['invalid_originals']) or 'none'}",
        f"Invalid Pixieset JPEGs: {', '.join(preflight['invalid_pixieset_files']) or 'none'}",
        "",
        "Pixieset is treated as an empirical downloaded-file reference only; this does not reproduce or identify Pixieset's encoder or algorithm.",
        "",
        "| Original filename | Pixieset filename | Match | Original dimensions | Pixieset dimensions | Original bytes | Pixieset bytes | 3600 contract |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for pair in pairs:
        lines.append(
            f"| {pair['original_filename']} | {pair['pixieset_filename']} | {pair['match_type']} | "
            f"{pair['original_width']}x{pair['original_height']} | {pair['pixieset_width']}x{pair['pixieset_height']} | "
            f"{pair['original_bytes']} | {pair['pixieset_bytes']} | {pair['pixieset_matches_3600_contract']} |"
        )
    if errors:
        lines += ["", "## Strict preflight failure", "", *[f"- {error}" for error in errors]]
    (output_dir / "preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if errors:
        raise PreflightError(
            "Strict Pixieset preflight failed: " + "; ".join(errors)
        )
    return preflight


def percent_reduction(input_bytes: int, output_bytes: int | None) -> float | None:
    if output_bytes is None or not input_bytes:
        return None
    return (1 - output_bytes / input_bytes) * 100


def ratio(input_bytes: int, output_bytes: int | None) -> float | None:
    if output_bytes in (None, 0):
        return None
    return input_bytes / output_bytes


def image_dimensions(path: Path) -> tuple[int, int]:
    with _open_image(path) as image:
        return image.size


def encode_mozjpeg(binary: str, input_path: Path, output_path: Path, quality: int, subsampling: str, timeout: int) -> float:
    sample = "2x2" if subsampling == "420" else "1x1"
    command = [
        binary,
        "-quality", str(quality),
        "-sample", sample,
        "-optimize",
        "-progressive",
        "-outfile", str(output_path),
        str(input_path),
    ]
    return run_encoder_command(command, output_path, timeout)


def encode_jpegli(binary: str, input_path: Path, output_path: Path, quality: int, subsampling: str, timeout: int) -> float:
    # This matches the upstream cjpegli CLI: progressive_level=2 is the
    # optimized progressive mode.  jpegli has no separate --optimize flag.
    command = [
        binary,
        f"--quality={quality}",
        f"--chroma_subsampling={subsampling}",
        "--progressive_level=2",
        str(input_path),
        str(output_path),
    ]
    return run_encoder_command(command, output_path, timeout)


def run_encoder_command(command: list[str], output_path: Path, timeout: int) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if completed.returncode != 0 or not output_path.is_file():
        detail = (completed.stderr or completed.stdout or "no output").strip()
        raise RuntimeError(f"encoder failed ({completed.returncode}): {detail[-600:]}")
    return elapsed_ms


def current_encoder(reference, original_bytes: int, stem: str):
    """Call the current production helper, without changing or persisting it."""
    # The production module imports an optional blurhash helper used by other
    # image-processing paths. It is not used by _make_download_master; keep
    # this compatibility shim confined to the benchmark process so the live
    # environment and production dependencies remain untouched.
    if "blurh" not in sys.modules:
        sys.modules["blurh"] = types.ModuleType("blurh")
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()
    from apps.core.utils import _make_download_master

    started = time.perf_counter()
    result = _make_download_master(
        reference.copy(), "JPEG", stem, original_size=original_bytes
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if result is None:
        return None, elapsed_ms
    result.seek(0)
    return result.read(), elapsed_ms


def discover_current_settings(reference, original_bytes: int, output_bytes: bytes | None):
    if output_bytes is None:
        return None, None
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from apps.core.utils import JPEG_DOWNLOAD_STRATEGIES, DOWNLOAD_MIN_PSNR

    for quality, subsampling_value in JPEG_DOWNLOAD_STRATEGIES:
        candidate_stream = io.BytesIO()
        reference.save(
            candidate_stream,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=subsampling_value,
        )
        candidate = candidate_stream.getvalue()
        if len(candidate) > original_bytes:
            continue
        with _open_image(io.BytesIO(candidate)) as decoded:
            score = psnr(reference, decoded)
        if score is not None and score >= DOWNLOAD_MIN_PSNR and candidate == output_bytes:
            label = {2: "420", 1: "422", 0: "444"}.get(subsampling_value, str(subsampling_value))
            return quality, label
    return None, None


def metric_row(
    *, image: dict[str, Any], method: str, threshold: float | None,
    output_path: Path | None, output_bytes: int | None, encode_ms: float | None,
    quality: int | None, subsampling: str | None, status: str,
    ss2: float | None, butter: float | None, psnr_value: float | None,
) -> dict[str, Any]:
    output_width = output_height = None
    if output_path and output_path.is_file():
        output_width, output_height = image_dimensions(output_path)
    reduction = percent_reduction(image["original_bytes"], output_bytes)
    return {
        "filename": image["source_path"].name,
        "source_path": str(image["source_path"]),
        "method": method,
        "threshold": "" if threshold is None else threshold,
        "status": status,
        "input_bytes": image["original_bytes"],
        "reference_bytes": image["reference_bytes"],
        "reference_width": image["reference_width"],
        "reference_height": image["reference_height"],
        "output_bytes": output_bytes,
        "output_width": output_width,
        "output_height": output_height,
        "format": "JPEG" if output_path else None,
        "output_path": str(output_path) if output_path else None,
        "percentage_reduction": reduction,
        "compression_ratio": ratio(image["original_bytes"], output_bytes),
        "ssimulacra2": ss2,
        "psnr": psnr_value,
        "butteraugli": butter,
        "encode_time_ms": encode_ms,
        "selected_quality": quality,
        "subsampling": subsampling,
        "encoder": method,
        "candidate_bytes_ge_original": (
            None if output_bytes is None else output_bytes >= image["original_bytes"]
        ),
        "used_original_fallback": status == "original_fallback",
    }


def csv_write(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) not in (None, "")]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return statistics.quantiles(sorted(values), n=100, method="inclusive")[max(0, min(99, int(fraction * 100) - 1))] if len(values) > 1 else values[0]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reductions = numeric_values(rows, "percentage_reduction")
    scores = numeric_values(rows, "ssimulacra2")
    times = numeric_values(rows, "encode_time_ms")
    return {
        "method": rows[0]["method"] if rows else "",
        "threshold": rows[0].get("threshold", "") if rows else "",
        "images": len(rows),
        "total_input_bytes": sum(int(row["input_bytes"]) for row in rows),
        "total_output_bytes": sum(int(row["output_bytes"]) for row in rows if row.get("output_bytes") not in (None, "")),
        "total_bytes_saved": sum(int(row["input_bytes"]) - int(row["output_bytes"]) for row in rows if row.get("output_bytes") not in (None, "")),
        "average_reduction": statistics.mean(reductions) if reductions else None,
        "median_reduction": statistics.median(reductions) if reductions else None,
        "p5_reduction": percentile(reductions, 0.05),
        "p95_reduction": percentile(reductions, 0.95),
        "median_ssimulacra2": statistics.median(scores) if scores else None,
        "p5_ssimulacra2": percentile(scores, 0.05),
        "worst_ssimulacra2": min(scores) if scores else None,
        "median_encode_time_ms": statistics.median(times) if times else None,
        "p95_encode_time_ms": percentile(times, 0.95),
        "total_encode_time_ms": sum(times) if times else 0,
        "quality_score_coverage": len(scores),
    }


def build_pairwise_rows(
    selected_rows: list[dict[str, Any]], threshold: float,
    pixieset: dict[str, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    """Align methods by filename at one matched-quality threshold."""
    aligned: dict[str, dict[str, dict[str, Any]]] = {}
    for row in selected_rows:
        if not threshold_matches(row.get("threshold"), threshold):
            continue
        aligned.setdefault(row["filename"], {})[row["method"]] = row
    result: list[dict[str, Any]] = []
    for filename, methods in sorted(aligned.items()):
        current = methods.get("current", {})
        mozjpeg = methods.get("mozjpeg", {})
        jpegli = methods.get("jpegli", {})
        current_bytes = current.get("output_bytes")
        moz_bytes = mozjpeg.get("output_bytes")
        jpegli_bytes = jpegli.get("output_bytes")
        pixieset_bytes = (pixieset or {}).get(filename, {}).get("pixieset_bytes")
        row = {
            "filename": filename,
            "threshold": threshold,
            "current_bytes": current_bytes,
            "mozjpeg_bytes": moz_bytes,
            "jpegli_bytes": jpegli_bytes,
            "pixieset_bytes": pixieset_bytes,
            "current_bytes_delta_vs_pixieset": (current_bytes - pixieset_bytes) if current_bytes is not None and pixieset_bytes is not None else None,
            "mozjpeg_bytes_delta_vs_pixieset": (moz_bytes - pixieset_bytes) if moz_bytes is not None and pixieset_bytes is not None else None,
            "jpegli_bytes_delta_vs_pixieset": (jpegli_bytes - pixieset_bytes) if jpegli_bytes is not None and pixieset_bytes is not None else None,
            "current_ssimulacra2": current.get("ssimulacra2"),
            "mozjpeg_ssimulacra2": mozjpeg.get("ssimulacra2"),
            "jpegli_ssimulacra2": jpegli.get("ssimulacra2"),
            "current_beats_mozjpeg": bool(current_bytes and moz_bytes and current_bytes < moz_bytes),
            "jpegli_beats_current": bool(current_bytes and jpegli_bytes and jpegli_bytes < current_bytes),
            "mozjpeg_beats_jpegli": bool(moz_bytes and jpegli_bytes and moz_bytes < jpegli_bytes),
            "mozjpeg_bytes_saved_vs_current": (current_bytes - moz_bytes) if current_bytes and moz_bytes else None,
            "jpegli_bytes_saved_vs_current": (current_bytes - jpegli_bytes) if current_bytes and jpegli_bytes else None,
            "mozjpeg_bytes_saved_vs_jpegli": (jpegli_bytes - moz_bytes) if moz_bytes and jpegli_bytes else None,
        }
        result.append(row)
    return result


def fmt(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def threshold_matches(value: Any, target: float, include_current: bool = True) -> bool:
    if value in (None, ""):
        return include_current
    try:
        return math.isclose(float(value), float(target), rel_tol=0, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False


def make_contact_sheet(
    selected_rows: list[dict[str, Any]], output_dir: Path, count: int, threshold: float,
    selected_paths: dict[tuple[str, str], Path],
) -> Path | None:
    from PIL import Image, ImageDraw, ImageFont, ImageStat

    by_image: dict[str, list[dict[str, Any]]] = {}
    for row in selected_rows:
        if threshold_matches(row.get("threshold"), threshold):
            by_image.setdefault(row["filename"], []).append(row)
    scored = []
    for filename, rows in by_image.items():
        score_values = numeric_values(rows, "ssimulacra2")
        scored.append((min(score_values) if score_values else float("inf"), filename))
    chosen = [filename for _, filename in sorted(scored)[:count]]
    if not chosen:
        return None

    tile_size = (360, 360)
    label_height = 26
    columns = 4
    rows_count = len(chosen)
    sheet = Image.new("RGB", (columns * tile_size[0], rows_count * (tile_size[1] + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    visual_crop_dir = output_dir / "visual-crops"
    visual_crop_dir.mkdir(exist_ok=True)
    method_order = ("reference", "current", "mozjpeg", "jpegli")
    for row_index, filename in enumerate(chosen):
        matching = next(row for row in selected_rows if row["filename"] == filename)
        source = Path(matching["source_path"])
        reference_path = Path(matching.get("reference_path", ""))
        paths = {"reference": reference_path}
        for method in method_order[1:]:
            candidate = selected_paths.get((filename, method))
            if candidate:
                paths[method] = candidate
        if not reference_path.is_file():
            continue
        with Image.open(reference_path) as ref:
            ref = ref.convert("RGB")
            crop_box = detail_crop_box(ref)
            native_crops = []
            for col, method in enumerate(method_order):
                path = paths.get(method)
                if not path or not path.is_file():
                    continue
                with Image.open(path) as image:
                    image = image.convert("RGB")
                    if image.size != ref.size:
                        image = image.resize(ref.size, Image.Resampling.LANCZOS)
                    crop = image.crop(crop_box)
                    native_crops.append((method, crop.copy()))
                    crop.thumbnail(tile_size, Image.Resampling.LANCZOS)
                    tile = Image.new("RGB", tile_size, "#eeeeee")
                    tile.paste(crop, ((tile_size[0] - crop.width) // 2, (tile_size[1] - crop.height) // 2))
                    x = col * tile_size[0]
                    y = row_index * (tile_size[1] + label_height)
                    sheet.paste(tile, (x, y + label_height))
                    draw.text((x + 8, y + 6), method.upper(), fill="black", font=font)
            if native_crops:
                crop_width, crop_height = native_crops[0][1].size
                native_sheet = Image.new("RGB", (crop_width * len(native_crops), crop_height), "white")
                native_draw = ImageDraw.Draw(native_sheet)
                for native_index, (method, crop) in enumerate(native_crops):
                    native_sheet.paste(crop, (native_index * crop_width, 0))
                    native_draw.rectangle((native_index * crop_width, 0, native_index * crop_width + 120, 24), fill="white")
                    native_draw.text((native_index * crop_width + 6, 6), method.upper(), fill="black", font=font)
                native_sheet.save(visual_crop_dir / f"{Path(filename).stem}.jpg", format="JPEG", quality=95)
    sheet_path = output_dir / f"contact-sheet-threshold-{str(threshold).replace('.', '_')}.jpg"
    sheet.save(sheet_path, format="JPEG", quality=90, optimize=True)
    return sheet_path


def detail_crop_box(image) -> tuple[int, int, int, int]:
    """Pick a high-variance square from a downsampled luminance thumbnail."""
    from PIL import Image, ImageStat

    width, height = image.size
    crop_size = min(768, width, height)
    if crop_size <= 0:
        return 0, 0, width, height
    small = image.convert("L").resize((min(256, width), min(256, height)), Image.Resampling.BILINEAR)
    sw, sh = small.size
    window = max(8, min(48, min(sw, sh) // 3))
    best = (-1.0, 0, 0)
    for y in range(0, max(1, sh - window + 1), max(1, window // 3)):
        for x in range(0, max(1, sw - window + 1), max(1, window // 3)):
            variance = ImageStat.Stat(small.crop((x, y, min(sw, x + window), min(sh, y + window)))).var[0]
            if variance > best[0]:
                best = (variance, x, y)
    cx = int((best[1] + window / 2) * width / sw)
    cy = int((best[2] + window / 2) * height / sh)
    left = max(0, min(width - crop_size, cx - crop_size // 2))
    top = max(0, min(height - crop_size, cy - crop_size // 2))
    return left, top, left + crop_size, top + crop_size


def render_report(
    path: Path, tools: list[Tool], images: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]], selected_rows: list[dict[str, Any]],
    pairwise_rows: list[dict[str, Any]], pixieset: dict[str, dict[str, int]] | None, contact_sheet: Path | None,
    default_threshold: float,
) -> None:
    lines = [
        "# KYAPTURE JPEG download compression benchmark",
        "",
        "Read-only benchmark. No production code, database rows, existing media, or download masters were modified.",
        "",
        "## A. Tool availability",
        "",
        "Metadata policy: all benchmark candidates are newly encoded, metadata-free JPEGs; references are metadata-free PNG/PPM. EXIF/copyright policy is not decided here.",
        "",
        "| Tool | Status | Path/command | Version/detail |",
        "|---|---|---|---|",
    ]
    for tool in tools:
        status = "available" if tool.available else "MISSING"
        detail = tool.error or ""
        lines.append(f"| {tool.name} | {status} | `{tool.path or tool.command}` | {detail or tool.version or ''} |")
    lines += [
        "",
        "Missing tools are not emulated. In particular, PSNR is only a diagnostic; a run without SSIMULACRA2 cannot support a perceptual-quality production decision.",
        "",
        "## B. Dataset summary",
        "",
        f"Images: **{len(images)}**; total original bytes: **{sum(image['original_bytes'] for image in images):,}**.",
        f"Reference long edge: at most **{MAX_EDGE}px**; no upscaling. References use EXIF orientation, best-effort ICC-to-sRGB conversion, RGB pixels, and no metadata.",
        "",
        "| Dataset statistic | Value |",
        "|---|---:|",
        f"| Original bytes min / median / max | {fmt(min((i['original_bytes'] for i in images), default=0))} / {fmt(statistics.median([i['original_bytes'] for i in images]) if images else None)} / {fmt(max((i['original_bytes'] for i in images), default=0))} |",
        f"| Reference dimensions | {', '.join(sorted({str(i['reference_width']) + 'x' + str(i['reference_height']) for i in images}))} |",
        "",
        "## C–E. Method results",
        "",
        f"The comparison table below uses threshold **{default_threshold:g}** when available. Current is the production helper called on the same normalized reference; MozJPEG/jpegli rows are the lowest tested encoder quality passing the threshold, with a neighborhood verification.",
        "",
        "| Encoder | Images | Median size | Median SSIMULACRA2 | Worst SSIMULACRA2 | P95 encode ms | Median reduction |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    chosen_summary = [row for row in summary_rows if threshold_matches(row.get("threshold"), default_threshold)]
    for row in chosen_summary:
        method = row.get("method", "")
        selected = [r for r in selected_rows if r.get("method") == method and threshold_matches(r.get("threshold"), default_threshold)]
        sizes = numeric_values(selected, "output_bytes")
        lines.append(f"| {method} | {row.get('images', 0)} | {fmt(statistics.median(sizes) if sizes else None, 0)} | {fmt(row.get('median_ssimulacra2'))} | {fmt(row.get('worst_ssimulacra2'))} | {fmt(row.get('p95_encode_time_ms'))} | {fmt(row.get('median_reduction'))}% |")
    lines += [
        "",
        "## F. SSIMULACRA2 threshold comparison",
        "",
        "| Method | Threshold | Total input bytes | Total output bytes | Bytes saved | Median reduction | p5 SSIM2 | Worst SSIM2 | Total encode seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(f"| {row.get('method')} | {row.get('threshold')} | {row.get('total_input_bytes'):,} | {row.get('total_output_bytes'):,} | {row.get('total_bytes_saved'):,} | {fmt(row.get('median_reduction'))}% | {fmt(row.get('p5_ssimulacra2'))} | {fmt(row.get('worst_ssimulacra2'))} | {fmt((row.get('total_encode_time_ms') or 0) / 1000)} |")
    lines += ["", "## G. Worst-case and pairwise analysis", ""]
    threshold_rows = [r for r in selected_rows if threshold_matches(r.get("threshold"), default_threshold)]
    for method in sorted({r.get("method") for r in threshold_rows}):
        method_rows = [r for r in threshold_rows if r.get("method") == method]
        worst = sorted(method_rows, key=lambda r: float(r["ssimulacra2"]) if r.get("ssimulacra2") not in (None, "") else float("inf"))[:10]
        lines.append(f"### {method}: 10 lowest available SSIMULACRA2 scores")
        lines.append("")
        lines.append("| File | SSIM2 | Output bytes | Reduction | Status |")
        lines.append("|---|---:|---:|---:|---|")
        for row in worst:
            lines.append(f"| {row['filename']} | {fmt(row.get('ssimulacra2'))} | {row.get('output_bytes') or 'n/a'} | {fmt(row.get('percentage_reduction'))}% | {row.get('status')} |")
        lines.append("")
    lines += [
        "### Explicit pairwise categories",
        "",
    ]
    pairwise_categories = (
        ("current_beats_mozjpeg", "Images where Current is smaller than MozJPEG", "mozjpeg_bytes_saved_vs_current"),
        ("jpegli_beats_current", "Images where jpegli is smaller than Current", "jpegli_bytes_saved_vs_current"),
        ("mozjpeg_beats_jpegli", "Images where MozJPEG is smaller than jpegli", "mozjpeg_bytes_saved_vs_jpegli"),
    )
    for flag, title, sort_key in pairwise_categories:
        lines.append(f"**{title}**")
        lines.append("")
        lines.append("| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |")
        lines.append("|---|---:|---:|---:|---:|")
        category_rows = sorted((row for row in pairwise_rows if row.get(flag)), key=lambda row: row.get(sort_key) or 0, reverse=True)[:10]
        if not category_rows:
            lines.append("| none | n/a | n/a | n/a | n/a |")
        for row in category_rows:
            lines.append(f"| {row['filename']} | {row.get('current_bytes') or 'n/a'} | {row.get('mozjpeg_bytes') or 'n/a'} | {row.get('jpegli_bytes') or 'n/a'} | {row.get(sort_key) or 'n/a'} |")
        lines.append("")
    review_rows = [row for row in threshold_rows if row.get("near_threshold_review")]
    lines += [
        "**Potential visual-QA queue:** " + (", ".join(row["filename"] for row in review_rows[:20]) if review_rows else "none flagged") + ". A near-threshold score is not proof of an artifact; inspect the contact sheet/crops.",
        "",
        "Largest regressions and wins, pairwise flags, and all per-image values are exported in `worst-cases.csv` and `pairwise.csv`. A `near_threshold_review` flag means a score passed but was close to the requested threshold; it is a human-visual-QA queue, not proof of an artifact.",
        "",
        "## H–I. Encode time and storage/bandwidth",
        "",
        "See the threshold table above for total input/output bytes, savings, median reduction, total CPU time, and p95 encode time. `candidate_bytes_ge_original=true` is the explicit original-size safety signal.",
        "",
        "## J. Pixieset reference comparison",
        "",
    ]
    if pixieset:
        lines.append("Pixieset values below are supplied observations only; this benchmark does not reproduce Pixieset's private algorithm.")
        lines += ["", "| File | Original | Pixieset | Current | Current Δ | MozJPEG | MozJPEG Δ | jpegli | jpegli Δ |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for filename, value in sorted(pixieset.items()):
            rows = [r for r in threshold_rows if r.get("filename") == filename]
            by_method = {r.get("method"): r.get("output_bytes") for r in rows}
            pixieset_bytes = value["pixieset_bytes"]
            current_bytes = by_method.get("current")
            mozjpeg_bytes = by_method.get("mozjpeg")
            jpegli_bytes = by_method.get("jpegli")
            delta = lambda candidate: (candidate - pixieset_bytes) if candidate is not None else "n/a"
            lines.append(f"| {filename} | {value['original_bytes']} | {pixieset_bytes} | {current_bytes if current_bytes is not None else 'n/a'} | {delta(current_bytes)} | {mozjpeg_bytes if mozjpeg_bytes is not None else 'n/a'} | {delta(mozjpeg_bytes)} | {jpegli_bytes if jpegli_bytes is not None else 'n/a'} | {delta(jpegli_bytes)} |")
    else:
        lines.append("No `--pixieset-reference` file was supplied.")
    lines += ["", "## K. Recommendation", ""]
    has_ss2 = any(tool.name == "SSIMULACRA2" and tool.available for tool in tools)
    complete = [r for r in summary_rows if not (r.get("threshold") in (None, "")) and threshold_matches(r.get("threshold"), default_threshold) and r.get("quality_score_coverage", 0) == len(images)]
    if not has_ss2:
        lines.append("**No production recommendation from this run.** SSIMULACRA2 is missing, so the run cannot establish matched perceptual quality. Install/use the approved external metric outside production and rerun this isolated harness.")
    elif not complete:
        lines.append("**No production recommendation from this run.** One or more methods lack complete SSIMULACRA2 coverage at the selected threshold; inspect tool errors and rerun before deciding.")
    else:
        best = min(
            complete,
            key=lambda r: (
                float(r.get("median_output_bytes") or float("inf")),
                float(r.get("median_encode_time_ms") or float("inf")),
            ),
        ) if complete else None
        lines.append("This run has complete SSIMULACRA2 coverage. Use the threshold table and worst-case CSV together with deployment/compatibility review; the lowest median file is not sufficient by itself.")
        if best:
            lines.append(f"Measured size leader at threshold {default_threshold:g}: **{best['method']}**. This is a benchmark result only; it does not authorize a production change.")
    if contact_sheet:
        lines += ["", f"Contact sheet: `{contact_sheet.name}` (overview centered on high-variance crops). Native-pixel side-by-side crops are in `visual-crops/` for human inspection."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing real source JPEGs.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmark-artifacts" / "jpeg-download")
    pixieset_group = parser.add_mutually_exclusive_group()
    pixieset_group.add_argument("--pixieset-reference", type=Path, help="CSV/JSON with filename, original_bytes, pixieset_bytes.")
    pixieset_group.add_argument("--pixieset-dir", type=Path, help="Pixieset downloaded JPEG folder for strict filename preflight and empirical size comparison.")
    parser.add_argument("--preflight-only", action="store_true", help="Run and write strict original/Pixieset preflight, then stop before encoding.")
    parser.add_argument("--mozjpeg-bin", help="Explicit cjpeg/MozJPEG executable path.")
    parser.add_argument("--jpegli-bin", help="Explicit cjpegli/jpegli executable path.")
    parser.add_argument("--ssimulacra2-bin", help="Explicit SSIMULACRA2 executable path.")
    parser.add_argument("--butteraugli-bin", help="Explicit optional Butteraugli executable path.")
    parser.add_argument("--thresholds", default=",".join(str(x) for x in DEFAULT_THRESHOLDS))
    parser.add_argument("--quality-min", type=int, default=30)
    parser.add_argument("--quality-max", type=int, default=100)
    parser.add_argument("--fallback-qualities", default="40,50,60,70,80,85,90,95,100", help="Quality ladder used only when SSIMULACRA2 is unavailable.")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--max-images", type=int)
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--contact-sheet-count", type=int, default=20)
    parser.add_argument("--worst-threshold", type=float, default=88)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {args.input_dir}")
    if args.preflight_only and not args.pixieset_dir:
        raise SystemExit("--preflight-only requires --pixieset-dir")
    if args.pixieset_dir and not args.pixieset_dir.is_dir():
        raise SystemExit(f"Pixieset directory does not exist: {args.pixieset_dir}")
    if not 1 <= args.quality_min <= args.quality_max <= 100:
        raise SystemExit("quality range must satisfy 1 <= --quality-min <= --quality-max <= 100")
    thresholds = tuple(float(value.strip()) for value in args.thresholds.split(",") if value.strip())
    fallback_qualities = tuple(sorted({int(value.strip()) for value in args.fallback_qualities.split(",") if value.strip()}))
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pixieset = None
    if args.pixieset_dir:
        try:
            preflight = preflight_pixieset(args.input_dir, args.pixieset_dir, output_dir)
        except PreflightError as exc:
            print(f"preflight={output_dir / 'preflight.md'}")
            raise SystemExit(str(exc)) from exc
        pixieset = {
            pair["original_filename"]: {
                "original_bytes": pair["original_bytes"],
                "pixieset_bytes": pair["pixieset_bytes"],
            }
            for pair in preflight["pairs"]
        }
        print(f"preflight={output_dir / 'preflight.md'}")
        if args.preflight_only:
            print(f"preflight_csv={output_dir / 'preflight.csv'}")
            return 0
    for name in ("references", "outputs", "raw-candidates"):
        (output_dir / name).mkdir(exist_ok=True)

    tools = audit_tools(args)
    tool_by_name = {tool.name: tool for tool in tools}
    images_paths = sorted(path for path in args.input_dir.rglob("*") if path.is_file() and path.suffix.lower() in JPEG_EXTENSIONS)
    if args.max_images:
        images_paths = images_paths[: args.max_images]
    if not images_paths:
        raise SystemExit("No .jpg/.jpeg files found in --input-dir")

    if args.pixieset_reference:
        pixieset = parse_csv_or_json(args.pixieset_reference)
    selected_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    selected_paths: dict[tuple[str, str], Path] = {}
    image_metadata: list[dict[str, Any]] = []
    current_import_error: str | None = None
    # Shared for this benchmark process.  Quality-search results are already
    # cached per encoder/subsampling; this cache avoids launching SSIM2 again
    # when a selected candidate is re-encoded for durable output.
    metric_cache: dict[tuple[str, str, str], float] = {}

    print(f"Benchmarking {len(images_paths)} JPEGs; output={output_dir}")
    for index, source_path in enumerate(images_paths, start=1):
        try:
            reference = make_reference(source_path)
        except Exception as exc:
            print(f"SKIP {source_path.name}: reference normalization failed: {exc}", file=sys.stderr)
            continue
        stem = safe_stem(source_path, index)
        reference_path = output_dir / "references" / f"{stem}.png"
        ppm_path = output_dir / "references" / f"{stem}.ppm"
        save_reference(reference, reference_path, ppm_path)
        original_bytes = source_path.stat().st_size
        image = {
            "source_path": source_path,
            "original_bytes": original_bytes,
            "reference_bytes": reference_path.stat().st_size,
            "reference_width": reference.width,
            "reference_height": reference.height,
            "reference_path": reference_path,
            "ppm_path": ppm_path,
            # SSIMULACRA2 can consume lossless PNM directly. Keeping the PNG
            # path for visual QA avoids requiring an extra PNG codec in the
            # isolated Windows metric build.
            "metric_reference_path": ppm_path,
            "stem": stem,
        }
        image_metadata.append(image)
        print(f"[{index}/{len(images_paths)}] {source_path.name} {original_bytes:,} bytes -> {reference.size}")

        # Current KYAPTURE: invoke the existing production helper on the
        # normalized reference. This writes only to memory and benchmark output.
        try:
            current_bytes, current_ms = current_encoder(reference, original_bytes, stem)
        except Exception as exc:
            current_import_error = str(exc)
            current_bytes, current_ms = None, None
            status = "current_unavailable"
        else:
            status = "selected" if current_bytes is not None else "original_fallback"
        current_path = None
        current_q = current_subsampling = None
        current_ss2 = current_butter = current_psnr = None
        if current_bytes is not None:
            current_path = output_dir / "outputs" / f"{stem}_current.jpg"
            current_path.write_bytes(current_bytes)
            current_q, current_subsampling = discover_current_settings(reference, original_bytes, current_bytes)
            with _open_image(current_path) as candidate_image:
                current_psnr = psnr(reference, candidate_image)
            if tool_by_name["SSIMULACRA2"].available:
                try:
                    current_ss2 = run_metric(tool_by_name["SSIMULACRA2"].path, image["metric_reference_path"], current_path, args.timeout_seconds, cache=metric_cache)
                except Exception as exc:
                    current_import_error = current_import_error or f"SSIMULACRA2: {exc}"
            current_butter = run_butteraugli(tool_by_name["Butteraugli"].path, reference_path, current_path, args.timeout_seconds)
            selected_paths[(source_path.name, "current")] = current_path
        current_row = metric_row(
            image=image, method="current", threshold=None, output_path=current_path,
            output_bytes=None if current_bytes is None else len(current_bytes), encode_ms=current_ms,
            quality=current_q, subsampling=current_subsampling, status=status,
            ss2=current_ss2, butter=current_butter, psnr_value=current_psnr,
        )
        current_row["reference_path"] = str(reference_path)
        selected_rows.append(current_row)

        # Independent encoders. Raw candidates are retained in memory only;
        # selected threshold outputs are copied to benchmark output.
        for method, tool_name, encoder in (
            ("mozjpeg", "MozJPEG cjpeg", encode_mozjpeg),
            ("jpegli", "jpegli cjpegli", encode_jpegli),
        ):
            tool = tool_by_name[tool_name]
            if not tool.available:
                continue
            cache: dict[tuple[str, int], dict[str, Any]] = {}

            def evaluate(quality: int, subsampling: str) -> dict[str, Any]:
                key = (subsampling, quality)
                if key in cache:
                    return cache[key]
                with tempfile.NamedTemporaryFile(prefix=f"{stem}_{method}_", suffix=".jpg", dir=output_dir / "raw-candidates", delete=False) as handle:
                    candidate_path = Path(handle.name)
                try:
                    encode_ms = encoder(tool.path, ppm_path, candidate_path, quality, subsampling, args.timeout_seconds)
                    output_size = candidate_path.stat().st_size
                    with _open_image(candidate_path) as candidate_image:
                        psnr_value = psnr(reference, candidate_image)
                    ss2 = None
                    if tool_by_name["SSIMULACRA2"].available:
                        try:
                            ss2 = run_metric(tool_by_name["SSIMULACRA2"].path, image["metric_reference_path"], candidate_path, args.timeout_seconds, cache=metric_cache)
                        except Exception as exc:
                            raise RuntimeError(f"SSIMULACRA2 failed for {source_path.name}: {exc}") from exc
                    butter = run_butteraugli(tool_by_name["Butteraugli"].path, reference_path, candidate_path, args.timeout_seconds)
                    result = {
                        "quality": quality, "subsampling": subsampling, "bytes": output_size,
                        "encode_ms": encode_ms, "psnr": psnr_value, "ss2": ss2,
                        "butter": butter, "path": candidate_path,
                    }
                    candidate_rows.append({
                        "filename": source_path.name, "method": method, "quality": quality,
                        "subsampling": subsampling, "output_bytes": output_size,
                        "percentage_reduction": percent_reduction(original_bytes, output_size),
                        "ssimulacra2": ss2, "psnr": psnr_value, "butteraugli": butter,
                        "encode_time_ms": encode_ms, "candidate_bytes_ge_original": output_size >= original_bytes,
                    })
                    cache[key] = result
                    return result
                finally:
                    if candidate_path.exists():
                        candidate_path.unlink()

            def search(threshold: float) -> dict[str, Any] | None:
                if not tool_by_name["SSIMULACRA2"].available:
                    return None
                # Binary search assumes the usual quality/score direction,
                # then explicitly verifies the selected neighborhood.
                low, high, best = args.quality_min, args.quality_max, None
                while low <= high:
                    mid = (low + high) // 2
                    result = evaluate(mid, "420")
                    if result["ss2"] is not None and result["ss2"] >= threshold:
                        best = mid
                        high = mid - 1
                    else:
                        low = mid + 1
                chosen_subsampling = "420"
                if best is None:
                    low, high, best = args.quality_min, args.quality_max, None
                    while low <= high:
                        mid = (low + high) // 2
                        result = evaluate(mid, "444")
                        if result["ss2"] is not None and result["ss2"] >= threshold:
                            best = mid
                            high = mid - 1
                        else:
                            low = mid + 1
                    chosen_subsampling = "444"
                if best is None:
                    return None
                neighborhood = range(max(args.quality_min, best - 2), min(args.quality_max, best + 2) + 1)
                passing = [evaluate(q, chosen_subsampling) for q in neighborhood if evaluate(q, chosen_subsampling)["ss2"] is not None and evaluate(q, chosen_subsampling)["ss2"] >= threshold]
                return min(passing, key=lambda result: (result["quality"], result["bytes"])) if passing else evaluate(best, chosen_subsampling)

            for threshold in thresholds:
                try:
                    result = search(threshold)
                except Exception as exc:
                    current_import_error = current_import_error or f"{method} {source_path.name}: {exc}"
                    result = None
                if result is None:
                    if not tool_by_name["SSIMULACRA2"].available:
                        for quality in fallback_qualities:
                            for subsampling in ("420",):
                                try:
                                    evaluate(quality, subsampling)
                                except Exception as exc:
                                    current_import_error = current_import_error or f"{method} {source_path.name}: {exc}"
                    continue
                selected_path = output_dir / "outputs" / f"{stem}_{method}_t{str(threshold).replace('.', '_')}.jpg"
                # evaluate() deletes its temporary output, so re-encode the
                # selected setting once for durable benchmark/visual-QA output.
                encode_ms = encoder(tool.path, ppm_path, selected_path, result["quality"], result["subsampling"], args.timeout_seconds)
                output_size = selected_path.stat().st_size
                with _open_image(selected_path) as candidate_image:
                    selected_psnr = psnr(reference, candidate_image)
                selected_ss2 = run_metric(tool_by_name["SSIMULACRA2"].path, image["metric_reference_path"], selected_path, args.timeout_seconds, cache=metric_cache) if tool_by_name["SSIMULACRA2"].available else None
                selected_butter = run_butteraugli(tool_by_name["Butteraugli"].path, reference_path, selected_path, args.timeout_seconds)
                status = "selected"
                score_margin = (selected_ss2 - threshold) if selected_ss2 is not None else None
                row = metric_row(
                    image=image, method=method, threshold=threshold, output_path=selected_path,
                    output_bytes=output_size, encode_ms=encode_ms, quality=result["quality"],
                    subsampling=result["subsampling"], status=status, ss2=selected_ss2,
                    butter=selected_butter, psnr_value=selected_psnr,
                )
                row["reference_path"] = str(reference_path)
                row["near_threshold_review"] = score_margin is not None and score_margin <= 1.0
                selected_rows.append(row)
                selected_paths[(source_path.name, method)] = selected_path

    # Current rows have no threshold; external rows are threshold-specific.
    for method in sorted({row["method"] for row in selected_rows}):
        method_rows = [row for row in selected_rows if row["method"] == method and str(row.get("threshold", "")) in ("", str(args.worst_threshold), f"{args.worst_threshold:g}")]
        if method_rows:
            summary = aggregate(method_rows)
            sizes = numeric_values(method_rows, "output_bytes")
            summary["median_output_bytes"] = statistics.median(sizes) if sizes else None
            summary_rows.append(summary)
        for threshold in thresholds:
            rows = [row for row in selected_rows if row["method"] == method and str(row.get("threshold", "")) in (str(threshold), f"{threshold:g}")]
            if rows:
                summary = aggregate(rows)
                sizes = numeric_values(rows, "output_bytes")
                summary["median_output_bytes"] = statistics.median(sizes) if sizes else None
                summary_rows.append(summary)
    # Add a conservative human-review flag to current rows if their score is
    # close to the worst requested threshold, without calling it an artifact.
    for row in selected_rows:
        if row.get("method") == "current" and row.get("ssimulacra2") not in (None, ""):
            row["near_threshold_review"] = float(row["ssimulacra2"]) <= args.worst_threshold + 1.0

    csv_write(output_dir / "results.csv", selected_rows)
    csv_write(output_dir / "candidate-results.csv", candidate_rows)
    csv_write(output_dir / "summary.csv", summary_rows)
    pairwise_rows = build_pairwise_rows(selected_rows, args.worst_threshold, pixieset)
    csv_write(output_dir / "pairwise.csv", pairwise_rows)
    worst_rows = []
    focus = [row for row in selected_rows if threshold_matches(row.get("threshold"), args.worst_threshold)]
    for row in sorted(focus, key=lambda r: float(r.get("ssimulacra2") or 10**9))[:10]:
        copy = dict(row); copy["analysis"] = "worst_perceptual_score"; worst_rows.append(copy)
    for row in sorted(focus, key=lambda r: float(r.get("percentage_reduction") or 10**9))[:10]:
        copy = dict(row); copy["analysis"] = "largest_size_regression"; worst_rows.append(copy)
    csv_write(output_dir / "worst-cases.csv", worst_rows)

    contact_sheet = None
    if args.contact_sheet:
        contact_sheet = make_contact_sheet(selected_rows, output_dir, args.contact_sheet_count, args.worst_threshold, selected_paths)
    render_report(output_dir / "report.md", tools, image_metadata, summary_rows, selected_rows, pairwise_rows, pixieset, contact_sheet, args.worst_threshold)

    if current_import_error:
        (output_dir / "errors.txt").write_text(current_import_error + "\n", encoding="utf-8")
    print(f"report={output_dir / 'report.md'}")
    print(f"results={output_dir / 'results.csv'}")
    if current_import_error:
        print(f"warnings={output_dir / 'errors.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
