"""Геометрия линий и граница Москвы. Метры в UTM 37N, длины на WGS84."""
from collections import Counter
import gzip
import json
from pathlib import Path
import numpy as np
import pyproj
import shapely as sh
from shapely.geometry import LineString

DATA = Path(__file__).resolve().parents[1] / "data"
RESULTS = DATA.parent / "results"
MASK = DATA / "city_boundary.geojson"
TRANSFORM = pyproj.Transformer.from_crs(4326, 32637, always_xy=True)
GEOD = pyproj.Geod(ellps="WGS84")


def routes(year):
    with gzip.open(DATA / "routes" / f"{year}.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def project(geom):
    return sh.transform(geom, TRANSFORM.transform, interleaved=False)


def clipped_lines(rows, mask):
    lines = [
        sh.LineString(line)
        for row in rows
        for line in (row["geoData"] or {}).get("coordinates", [])
        if len(line) > 1
    ]
    lines = project(np.asarray(lines))
    sh.prepare(mask)
    inside = sh.covers(mask, lines)
    pieces = list(lines[inside])
    for line in lines[~inside]:
        clipped = sh.intersection(line, mask)
        stack = [clipped]
        while stack:
            part = stack.pop()
            if part.is_empty:
                continue
            if part.geom_type == "LineString":
                pieces.append(part)
            elif hasattr(part, "geoms"):
                stack.extend(part.geoms)
    return [sh.get_coordinates(part) for part in pieces]


def segments(lines, grid):
    # Совпадающие отрезки обоих направлений учитываем один раз.
    arrays = []
    for coords in lines:
        xy = np.floor(coords / grid + 0.5).astype(np.int64)
        a, b = xy[:-1], xy[1:]
        swap = (a[:, 0] > b[:, 0]) | ((a[:, 0] == b[:, 0]) & (a[:, 1] > b[:, 1]))
        ar = np.column_stack((np.where(swap[:, None], b, a), np.where(swap[:, None], a, b)))
        arrays.append(ar[np.any(a != b, axis=1)])
    return np.unique(np.concatenate(arrays), axis=0).reshape(-1, 2, 2) * grid


def geodesic_km(geom):
    # Считаем расстояния только внутри одной линии.
    xy, ix = sh.get_coordinates(sh.get_parts(geom), return_index=True)
    lon, lat = TRANSFORM.transform(xy[:, 0], xy[:, 1], direction="INVERSE")
    adjacent = ix[:-1] == ix[1:]
    _, _, lengths = GEOD.inv(
        lon[:-1][adjacent], lat[:-1][adjacent], lon[1:][adjacent], lat[1:][adjacent]
    )
    return float(np.sum(lengths) / 1000)


def lengths(line, mask):
    pts = np.asarray(line, dtype=float)
    if len(pts) < 2:
        return 0.0, 0.0
    whole = LineString(pts)
    dx = GEOD.inv(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1])[2]
    total = float(dx.sum())
    if sh.covers(mask, whole):
        return total, total
    if sh.disjoint(mask, whole):
        return total, 0.0
    segments = sh.linestrings(np.stack((pts[:-1], pts[1:]), axis=1))
    inside = sh.covers(mask, segments)
    outside = sh.disjoint(mask, segments)
    covered = float(dx[inside].sum())
    for segment in segments[~(inside | outside)]:
        piece = sh.intersection(mask, segment)
        if not piece.is_empty:
            covered += GEOD.geometry_length(piece)
    assert 0 <= covered <= total + 0.05
    return total, covered


def counts(geom):
    chains = sh.get_parts(sh.line_merge(geom))
    if not len(chains):
        return 0, 0
    a = sh.get_coordinates(sh.get_point(chains, 0))
    b = sh.get_coordinates(sh.get_point(chains, -1))
    pairs = Counter(tuple(sorted((tuple(p), tuple(q)))) for p, q in zip(a, b))
    extra = sum(2 * n if p == q else n - 1 for (p, q), n in pairs.items())
    return len({v for pair in pairs for v in pair}) + extra, len(chains) + extra
