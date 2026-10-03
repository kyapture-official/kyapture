"""Benchmark representative JPEGs against the production download-master pipeline."""
import argparse
import csv
import io
import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django

django.setup()

from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.utils import process_image_pipeline


CASES = (
    ("jpeg_1mb", 1_000_000, (1800, 1200)),
    ("jpeg_2mb", 2_000_000, (2600, 1733)),
    ("jpeg_3_5mb", 3_500_000, (3600, 2400)),
    ("jpeg_6_3mb", 6_300_000, (5200, 3467)),
    ("high_resolution_camera", 8_000_000, (8000, 5333)),
)


def build_fixture(target_bytes, initial_size):
    dimensions = initial_size
    fixture_bytes = b""
    for _ in range(6):
        image = PILImage.effect_noise(dimensions, 96).convert("RGB")
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=96, subsampling=0)
        fixture_bytes = stream.getvalue()
        if not fixture_bytes:
            break
        scale = math.sqrt(target_bytes / len(fixture_bytes))
        if 0.98 <= scale <= 1.02:
            break
        dimensions = (
            max(640, int(dimensions[0] * scale)),
            max(480, int(dimensions[1] * scale)),
        )
    return fixture_bytes


def benchmark_case(name, target_bytes, dimensions, output_dir):
    original_bytes = build_fixture(target_bytes, dimensions)
    fixture_path = output_dir / f"{name}_original.jpg"
    fixture_path.write_bytes(original_bytes)

    source = SimpleUploadedFile(
        fixture_path.name,
        original_bytes,
        content_type="image/jpeg",
    )
    download_file = process_image_pipeline(source)[3]
    output_bytes = original_bytes if download_file is None else download_file.read()
    output_path = output_dir / f"{name}_download.jpg"
    output_path.write_bytes(output_bytes)

    original_image = PILImage.open(io.BytesIO(original_bytes))
    output_image = PILImage.open(io.BytesIO(output_bytes))
    reduction_percent = (1 - len(output_bytes) / len(original_bytes)) * 100
    return {
        "case": name,
        "original_bytes": len(original_bytes),
        "optimized_bytes": len(output_bytes),
        "reduction_percent": round(reduction_percent, 2),
        "original_dimensions": f"{original_image.width}x{original_image.height}",
        "optimized_dimensions": f"{output_image.width}x{output_image.height}",
        "format": output_image.format,
        "used_original_fallback": download_file is None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="benchmark-artifacts/download-master",
        help="Directory for generated fixtures and CSV output.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [benchmark_case(*case, output_dir) for case in CASES]
    report_path = output_dir / "download-master-benchmark.csv"
    with report_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("case,original_bytes,optimized_bytes,reduction_percent,original_dimensions,optimized_dimensions,format,used_original_fallback")
    for row in rows:
        print(",".join(str(row[key]) for key in row))
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
