"""Восстановление годовых направлений по маршрутам и справочнику остановок."""
import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path

import numpy as np
from numba import njit

from stop_names import expand, expansion_pattern, key, normalize, stop_labels

DATA = Path(__file__).resolve().parents[1] / "data"
EARTH = 6371008.8


def distance(a, b):
    lon, lat = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat) / 2) ** 2
        + math.cos(lat) * math.cos(lat2) * math.sin((lon2 - lon) / 2) ** 2
    )
    return 2 * EARTH * math.asin(math.sqrt(h))


def ordered_candidates(layers):
    """Кандидаты, принадлежащие хотя бы одной полной цепочке по ходу линии."""

    def allowed(left, right):
        return left[0] != right[0] and left[1] <= right[1]

    forward = [layers[0]]
    for candidates in layers[1:]:
        forward.append([b for b in candidates if any(allowed(a, b) for a in forward[-1])])
    viable = [forward[-1]]
    for candidates in reversed(forward[:-1]):
        viable.append([a for a in candidates if any(allowed(a, b) for b in viable[-1])])
    return [[sid for sid, _ in positions] for positions in reversed(viable)]


@njit
def locate(lon, lat, line):
    """Положение ближайшей точки вдоль линии в локальной системе координат."""
    sy = math.pi / 180 * 6371008.8
    sx = sy * math.cos(math.radians(lat))
    along = 0.0
    best = math.inf
    position = 0.0
    for i in range(1, len(line)):
        a, b = line[i - 1], line[i]
        x, y = (a[0] - lon) * sx, (a[1] - lat) * sy
        dx, dy = (b[0] - a[0]) * sx, (b[1] - a[1]) * sy
        span = math.hypot(dx, dy)
        if span:
            t = max(0.0, min(1.0, -(x * dx + y * dy) / span**2))
            offset = math.hypot(x + t * dx, y + t * dy)
            if offset < best:
                best, position = offset, along + t * span
        along += span
    return best, position


def projected_parts(labels, lines, stops):
    """Для каждой платформы находим ближайшую точку каждой линии."""
    parts = []
    for line in lines:
        line = np.asarray(line, dtype=float)
        if len(line) < 2:
            continue
        lo, hi = line.min(axis=0), line.max(axis=0)
        candidates = {}
        for name in set(labels):
            points = []
            for sid, lon, lat in stops.get(name, ()):
                # Заведомо более широкий фильтр, чем 30 м на широте Москвы.
                if (
                    lo[0] - 0.002 <= lon <= hi[0] + 0.002
                    and lo[1] - 0.002 <= lat <= hi[1] + 0.002
                ):
                    off, pos = locate(lon, lat, line)
                    if off <= 30:
                        points.append((sid, off, pos))
            candidates[name] = points
        parts.append(candidates)
    return parts


def classify(names, parts, radius):
    local = [set() for _ in names]
    ordered = [set() for _ in names]
    for part in parts:
        layers = [[(sid, pos) for sid, off, pos in part[name] if off <= radius] for name in names]
        for ids, layer in zip(local, layers):
            ids.update(sid for sid, _ in layer)
        if not all(layers):
            continue
        for sign in [1, -1]:
            result = ordered_candidates([[(s, sign * p) for s, p in layer] for layer in layers])
            for ids, valid in zip(ordered, result):
                ids.update(valid)
    return local, ordered


def best_path(layers, sign):
    if any(not layer for layer in layers):
        return None
    parents = []
    previous = []
    for i, layer in enumerate(layers):
        costs = []
        indices = []
        for sid, off, pos in layer:
            cost = off
            if i:
                choices = (
                    (prev, j)
                    for j, (prev, (prev_id, _, prev_pos)) in enumerate(
                        zip(previous, layers[i - 1])
                    )
                    if prev_id != sid and sign * prev_pos <= sign * pos
                )
                best, j = min(choices, default=(float("inf"), -1))
                cost += best
                indices.append(j)
            costs.append(cost)
        if min(costs) == float("inf"):
            return None
        parents.append(indices)
        previous = costs
    score, j = min((v, j) for j, v in enumerate(previous))
    path = []
    for i in range(len(layers) - 1, -1, -1):
        path.append(layers[i][j][0])
        if i:
            j = parents[i][j]
    return score, list(reversed(path))


@njit
def project(x, y, line, cumulative):
    sy = math.pi / 180 * EARTH
    sx = sy * math.cos(math.radians(y))
    closest, position = math.inf, 0.0
    for k in range(len(line) - 1):
        dx = (line[k + 1, 0] - line[k, 0]) * sx
        dy = (line[k + 1, 1] - line[k, 1]) * sy
        ax = (line[k, 0] - x) * sx
        ay = (line[k, 1] - y) * sy
        norm = dx * dx + dy * dy
        if norm == 0:
            continue
        fraction = max(0.0, min(1.0, -(ax * dx + ay * dy) / norm))
        offset = math.hypot(ax + fraction * dx, ay + fraction * dy)
        if offset < closest:
            closest = offset
            position = cumulative[k] + fraction * (cumulative[k + 1] - cumulative[k])
    return closest, position


def chain(ordered, route, coordinates):
    # Выбираем цепочку с минимальной суммой отклонений от трассы.
    candidates = []
    for component, coords in enumerate(route["geoData"]["coordinates"]):
        if len(coords) < 2:
            continue
        line = np.array(coords)
        along = np.r_[0.0, np.cumsum([distance(a, b) for a, b in zip(coords, coords[1:])])]
        offsets = {}
        for layer in ordered:
            for sid in layer:
                if sid not in offsets:
                    offsets[sid] = project(*coordinates[sid][1:], line, along)
        layers = [
            [(sid, *offsets[sid]) for sid in sorted(ids) if offsets[sid][0] <= 30]
            for ids in ordered
        ]
        for sign in (1, -1):
            result = best_path(layers, sign)
            if result is not None:
                cost, ids = result
                candidates.append((cost, ids, component, sign, [offsets[s][1] for s in ids]))
    return min(candidates) if candidates else None


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def rebuild(year):
    registry = load(DATA / "routes" / f"{year}.json.gz")
    features = load(DATA / "stops" / f"{year}.geojson.gz")["features"]
    coordinates = {}
    original = defaultdict(list)
    expanded = defaultdict(list)
    conflicts = set()
    for feature in features:
        props = feature["properties"]
        if not feature["geometry"] or props["stop_id"] is None or not props["stop_name"]:
            continue
        sid = str(props["stop_id"])
        xy = feature["geometry"]["coordinates"]
        value = [props["stop_name"], *xy]
        if sid in coordinates and coordinates[sid] != value:
            conflicts.add(sid)
        coordinates[sid] = value
        name = normalize(value[0])
        original[name].append((sid, *xy))
        expanded[expand(name)].append((sid, *xy))
    dictionary = defaultdict(set)
    for name in expanded:
        dictionary[key(name)].add(name)

    directions = []
    parsed = []
    for r in registry:
        for field in ("TrackOfFollowing", "ReverseTrackOfFollowing"):
            value = (r[field] or "").strip()
            if value and not (
                value.casefold() == "нет" or value.casefold().startswith(("нет,", "нет "))
            ):
                parsed.append((r, field, stop_labels(value, original)))
    pending = parsed
    for stage in range(3 if year == 2023 else 1):
        unresolved = []
        index = original if stage == 0 else expanded
        for r, field, raw in pending:
            names = list(map(expand, raw)) if stage else raw.copy()
            if stage == 2:
                for i, name in enumerate(names):
                    matches = dictionary[key(name)]
                    if name not in index and len(matches) == 1:
                        full = next(iter(matches))
                        if expansion_pattern(name).fullmatch(full):
                            names[i] = full
            if all(name in index for name in names) and names and r["geoData"]:
                parts = projected_parts(names, r["geoData"]["coordinates"], index)
                _, ordered = classify(names, parts, 30)
                if all(ordered) and not any(conflicts.intersection(layer) for layer in ordered):
                    candidate = chain(ordered, r, coordinates)
                    if candidate:
                        _, ids, component, sign, positions = candidate
                        weights = [
                            round(sign * (b - a) * 1000) for a, b in zip(positions, positions[1:])
                        ]
                        if weights and min(weights) > 0:
                            directions.append(
                                dict(
                                    rid=r["global_id"],
                                    number=r["RouteNumber"],
                                    field=field,
                                    component=component,
                                    orientation=sign,
                                    stops=ids,
                                    mm=weights,
                                )
                            )
                            continue
            unresolved.append((r, field, raw))
        pending = unresolved
        print(
            f"{year}. Записей с полным направлением: {len({d['rid'] for d in directions})}. "
            f"Полных направлений: {len(directions)} из {len(parsed)}.",
            flush=True,
        )
    ids = sorted({sid for d in directions for sid in d["stops"]})
    return dict(
        year=year, directions=directions, platforms={sid: coordinates[sid] for sid in ids}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, choices=range(2018, 2027))
    parser.add_argument(
        "--output", type=Path, help="Сохранить восстановленные направления в JSON.gz"
    )
    args = parser.parse_args()
    result = rebuild(args.year)
    if args.output:
        args.output.write_bytes(
            gzip.compress(json.dumps(result, ensure_ascii=False).encode(), mtime=0)
        )
        print(f"Направления записаны в {args.output}")
        return
    reference = load(DATA / "graphs" / f"{args.year}.json.gz")
    for name in ("directions", "platforms"):
        if result[name] != reference[name]:
            raise ValueError(f"Расхождение с сохранённым графом в поле {name}")
    print("Платформы, последовательности и длины совпали с сохранённым графом.")


if __name__ == "__main__":
    main()
