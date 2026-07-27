from __future__ import annotations

from pathlib import Path
from typing import Any

from .csv_export import write_normalized_csv
from .dashboard import render_html_v2

__all__ = ["render_html", "render_html_v2", "write_html", "write_normalized_csv"]

render_html = render_html_v2


def write_html(path: Path, analysis: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_v2(analysis), encoding="utf-8")
