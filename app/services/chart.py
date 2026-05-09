import hashlib
import json
import os
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

_CJK_FONT = None
for candidate in ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC"]:
    for f in fm.fontManager.ttflist:
        if candidate.lower() in f.name.lower():
            _CJK_FONT = f.name
            break
    if _CJK_FONT:
        break

if _CJK_FONT:
    plt.rcParams["font.family"] = _CJK_FONT
    plt.rcParams["axes.unicode_minus"] = False


def _make_filename(title: str, data_json: str) -> str:
    raw = f"{title}_{data_json}"
    return f"chart_{hashlib.md5(raw.encode()).hexdigest()[:10]}.png"


def _render_chart(
    labels: list[str], values: list[float], title: str,
    xlabel: str, ylabel: str, plot_fn: Callable,
    extra_setup: Callable | None = None,
) -> str:
    fig, ax = plt.subplots(figsize=(10, 6))
    plot_fn(ax, labels, values)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(xlabel or "")
    ax.set_ylabel(ylabel or "")
    ax.tick_params(axis="x", rotation=30)
    if extra_setup:
        extra_setup(ax)
    fig.tight_layout()

    filename = _make_filename(title, json.dumps({"labels": labels, "values": values}))
    filepath = os.path.join(STATIC_DIR, filename)
    fig.savefig(filepath, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return f"/static/{filename}"


def generate_bar_chart(
    labels: list[str], values: list[float], title: str,
    xlabel: str = "", ylabel: str = "",
) -> str:
    def _plot(ax, x, y):
        ax.bar(x, y, color="steelblue", edgecolor="white")

    return _render_chart(labels, values, title, xlabel, ylabel, _plot)


def generate_line_chart(
    x: list[str], y: list[float], title: str,
    xlabel: str = "", ylabel: str = "",
) -> str:
    def _plot(ax, x_vals, y_vals):
        ax.plot(x_vals, y_vals, marker="o", color="steelblue", linewidth=2)

    def _setup(ax):
        ax.grid(True, alpha=0.3)

    return _render_chart(x, y, title, xlabel, ylabel, _plot, _setup)
