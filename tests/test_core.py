from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from word_merge_app.core import build_word, scan_sources


def make_image(path: Path, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, "white")
    for x in range(20, size[0] - 20):
        image.putpixel((x, 20), (18, 92, 84))
    image.save(path)


def make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=420)
    page.insert_text((72, 72), "PDF TEST 39.80", fontsize=28)
    page.draw_rect(fitz.Rect(60, 110, 540, 320), color=(0.4, 0, 0), width=2)
    doc.save(path)
    doc.close()


def test_scan_depth(tmp_path: Path) -> None:
    make_image(tmp_path / "root.jpg", (300, 500))
    one = tmp_path / "one"
    two = one / "two"
    two.mkdir(parents=True)
    make_image(one / "one.png", (400, 300))
    make_image(two / "two.jpg", (300, 300))

    assert len(scan_sources(tmp_path, 0)) == 1
    assert len(scan_sources(tmp_path, 1)) == 2
    assert len(scan_sources(tmp_path, 2)) == 3
    assert len(scan_sources(tmp_path, None)) == 3


def test_build_word_with_image_and_pdf(tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg", (300, 500))
    make_pdf(tmp_path / "b.pdf")
    output = tmp_path / "out.docx"

    result = build_word(tmp_path, output, None)

    assert output.exists()
    assert result.source_count == 2
    assert result.page_count == 2
