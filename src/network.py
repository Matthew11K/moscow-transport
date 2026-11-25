"""Годовые длина, плотность и индекс Канского в постоянной границе Москвы."""
import csv
import json
from statistics import mean

import shapely as sh
from shapely.geometry import shape

from geometry import (
    GEOD,
    MASK,
    RESULTS,
    clipped_lines,
    counts,
    geodesic_km,
    lengths,
    project,
    routes,
    segments,
)


def measure(year, boundary, projected_boundary, area):
    rows = routes(year)
    lines = clipped_lines(rows, projected_boundary)
    total_m = 0.0
    measured = 0
    for row in rows:
        coordinates = (row["geoData"] or {}).get("coordinates", [])
        if coordinates:
            measured += 1
            total_m += sum(lengths(line, boundary)[1] for line in coordinates)

    by_grid = {}
    for grid in (5, 10, 20):
        distinct = segments(lines, grid)
        joined = sh.union_all(sh.linestrings(distinct), grid_size=grid)
        vertices, edges = counts(joined)
        # Округление может перенести концы линий за границу Москвы.
        inside = sh.intersection(sh.set_precision(joined, 0), projected_boundary, grid_size=0)
        km = geodesic_km(inside)
        assert vertices >= 3 and 0 < edges <= 3 * vertices - 6
        by_grid[grid] = dict(
            V=vertices, E=edges, gamma=edges / (3 * vertices - 6), km=km, density=km / area
        )
    return dict(
        year=year, records=len(rows), measured=measured, route_km=total_m / 1000, grids=by_grid
    )


def main():
    boundary = shape(json.loads(MASK.read_bytes()))
    area = (
        sum(abs(GEOD.geometry_area_perimeter(sh.orient_polygons(p))[0]) for p in boundary.geoms)
        / 1e6
    )
    projected = project(boundary)
    sh.prepare(boundary)
    annual = []
    for year in range(2018, 2027):
        row = measure(year, boundary, projected, area)
        annual.append(row)
        print(year, f'{row["grids"][10]["km"]:.1f} км', flush=True)

    columns = [
        "Срез или период",
        "Длина объединённых линий, км",
        "Плотность, км на кв. км",
        "Индекс Канского",
        "Сумма маршрутных длин, км",
    ]
    table = [
        [
            str(r["year"]),
            r["grids"][10]["km"],
            r["grids"][10]["density"],
            r["grids"][10]["gamma"],
            r["route_km"],
        ]
        for r in annual
    ]
    for i in (0, 3, 6):
        group = table[i : i + 3]
        table.append(
            [f"{group[0][0]}-{group[-1][0]}", *[mean(column) for column in list(zip(*group))[1:]]]
        )
    with (RESULTS / "network.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(columns)
        for label, *values in table:
            writer.writerow([label, *[f"{v:.6f}".replace(".", ",") for v in values]])
    (RESULTS / "network.json").write_text(
        json.dumps(dict(area_km2=area, years=annual), indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
