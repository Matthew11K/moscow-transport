"""Расчёт индекса Канского по ячейкам карты Москвы."""
import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np
import shapely as sh
from shapely.geometry import Polygon, shape

from geometry import MASK, RESULTS, TRANSFORM, clipped_lines, counts, project, routes, segments

OUT = RESULTS
SIDE = 4000  # сторона ячейки в метрах
MIN_V = 20  # минимум вершин в каждом году
YEARS = list(range(2018, 2027))


def hexagons(mask):
    # Соседние ячейки имеют общие координаты вершин.
    dx, dy = SIDE / 2, SIDE * math.sqrt(3) / 2
    offsets = [(2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1)]
    x0, y0, x1, y1 = mask.bounds
    for q in range(math.floor(x0 / (3 * dx)) - 1, math.ceil(x1 / (3 * dx)) + 2):
        for r in range(math.floor(y0 / (2 * dy)) - 1, math.ceil(y1 / (2 * dy)) + 2):
            x, y = q * 3, 2 * r + q % 2
            cell = Polygon([((x + i) * dx, (y + j) * dy) for i, j in offsets])
            area = mask.intersection(cell)
            if area.area > 0:
                yield f"{q}-{r}", cell, area


def draw(cells, results):
    from matplotlib.path import Path as PlotPath
    from matplotlib.patches import PathPatch
    from matplotlib.cm import ScalarMappable
    from matplotlib import colormaps

    fig, axes = plt.subplots(1, 4, figsize=(14, 6.5))
    cmaps = [colormaps["viridis"]] * 3 + [colormaps["RdBu"]]
    valid = [v["period_means"] for v in results.values() if v["period_means"]]
    low, high = np.floor(np.min(valid) * 20) / 20, np.ceil(np.max(valid) * 20) / 20
    diff = max(0.01, np.ceil(max(abs(row[2] - row[0]) for row in valid) * 100) / 100)
    norms = [Normalize(low, high)] * 3 + [TwoSlopeNorm(0, -diff, diff)]
    for ax, title in zip(axes, ["2018-2020", "2021-2023", "2024-2026", "Третий минус первый"]):
        ax.set_title(title, fontsize=13)
        ax.set_aspect("equal")
        ax.axis("off")
    for key, _, area in cells:
        values = results[key]["period_means"]
        panels = values + [values[2] - values[0]] if values else [None] * 4
        for poly in sh.get_parts(sh.orient_polygons(area)):
            if poly.geom_type != "Polygon":
                continue
            path = PlotPath.make_compound_path(
                *(
                    PlotPath(np.asarray(r.coords), closed=True)
                    for r in [poly.exterior, *poly.interiors]
                )
            )
            for ax, val, cmap, norm in zip(axes, panels, cmaps, norms):
                color = "#e3e3e3" if val is None else cmap(norm(val))
                ax.add_patch(
                    PathPatch(path, facecolor=color, edgecolor="#888888", linewidth=0.27)
                )
    for ax in axes:
        for name, lon, lat in [
            ("Зеленоград", 37.21, 55.99),
            ("Кремль", 37.62, 55.75),
            ("Троицк", 37.31, 55.48),
        ]:
            x, y = TRANSFORM.transform(lon, lat)
            ax.plot(x, y, ".", color="black", markersize=3)
            ax.annotate(
                name,
                (x, y),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=7,
                bbox=dict(facecolor="white", alpha=0.8, linewidth=0, pad=0.5),
            )
        ax.autoscale_view()
    fig.subplots_adjust(top=0.85, bottom=0.22, wspace=0.08, left=0.015, right=0.985)
    fig.suptitle("Локальный индекс Канского наземной сети Москвы", fontsize=19)
    for rect, idx, label in [
        ([0.17, 0.15, 0.40, 0.022], 0, "Среднее за три годовых среза"),
        ([0.775, 0.15, 0.18, 0.022], 3, "Разность индексов"),
    ]:
        bar = fig.colorbar(
            ScalarMappable(norm=norms[idx], cmap=cmaps[idx]),
            cax=fig.add_axes(rect),
            orientation="horizontal",
        )
        bar.set_label(label, fontsize=10)
    fig.text(
        0.5,
        0.04,
        "Сторона ячейки 4 км. Серым показаны ячейки, где хотя бы в одном году менее 20 вершин. "
        "Данные за 2026 год приведены на 6 октября.",
        ha="center",
        fontsize=10,
    )
    fig.savefig(OUT / "connectivity_map.png", dpi=180, facecolor="white")
    plt.close(fig)


def main():
    mask = project(shape(json.loads(MASK.read_bytes())))
    cells = list(hexagons(mask))
    assert abs(sum(a.area for _, _, a in cells) - mask.area) < 1
    results = {key: {"years": {}} for key, _, _ in cells}
    for year in YEARS:
        lines = clipped_lines(routes(year), mask)
        geom = sh.union_all(sh.linestrings(segments(lines, 10)), grid_size=10)
        parts = sh.get_parts(sh.set_precision(geom, 0))
        tree = sh.STRtree(parts)
        for key, cell, area in cells:
            subset = parts[tree.query(cell, predicate="intersects")]
            cut = sh.intersection(subset, area)
            local = sh.get_parts(cut)
            local = local[sh.get_type_id(local) == 1]
            assert abs(sh.length(local).sum() - sh.length(cut).sum()) < 0.001
            v, e = counts(sh.multilinestrings(local)) if len(local) else (0, 0)
            gamma = e / (3 * v - 6) if v >= 3 else None
            assert gamma is None or 0 <= gamma <= 1
            results[key]["years"][year] = dict(V=v, E=e, gamma=gamma)
        print(year, "OK", flush=True)
    for row in results.values():
        years = list(row["years"].values())
        row["period_means"] = (
            [sum(y["gamma"] for y in years[i : i + 3]) / 3 for i in (0, 3, 6)]
            if min(y["V"] for y in years) >= MIN_V
            else None
        )
    (OUT / "cells.json").write_text(
        json.dumps(
            dict(side_m=SIDE, min_V=MIN_V, crs="EPSG:32637", cells=results),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    draw(cells, results)


if __name__ == "__main__":
    main()
