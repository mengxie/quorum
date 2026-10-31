from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import segno
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from quorum.domain.codes import format_code

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def ago(moment: datetime) -> str:
    seconds = (datetime.now(UTC) - moment).total_seconds()
    if seconds < 60:
        return "just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 24 else f"{moment.day} {moment:%b}"


def qr_svg(url: str, *, title: str) -> Markup:
    """An inline, scannable QR code, generated server-side: no images, scripts or services."""
    svg: str = segno.make(url, error="m").svg_inline(
        scale=6, border=2, dark="#161b2e", light="#ffffff", title=title
    )
    return Markup(svg)  # noqa: S704  # SVG produced by segno, not user input


templates.env.filters["ago"] = ago
templates.env.filters["code"] = format_code
templates.env.globals["version"] = version("quorum")
