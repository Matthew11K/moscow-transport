"""Сборка годового графа и выбор поездки с проверенными платформами."""
from collections import defaultdict
import gzip
from heapq import heappop, heappush
import json
from pathlib import Path

GRAPHS = Path(__file__).resolve().parents[1] / "data" / "graphs"


def archives():
    return json.loads(gzip.decompress((GRAPHS / "verified_edges.json.gz").read_bytes()))


def year_data(year):
    path = GRAPHS / f"{year}.json.gz"
    return json.loads(gzip.decompress(path.read_bytes()))


def build_graph(directions, checked):
    anchors = defaultdict(set)
    override = set()
    for e in checked:
        key = (e["rid"], e["field"])
        i = e["position"]
        anchors[key, i].add(e["a"]["id"])
        anchors[key, i + 1].add(e["b"]["id"])
        override.add((key, i))
    assert all(
        len(s) == 1 for s in anchors.values()
    ), "Архивные записи указывают на разные платформы"
    graph = defaultdict(dict)

    def add(a, b, mm, service):
        if b not in graph[a] or mm < graph[a][b][0]:
            graph[a][b] = (mm, service)

    for d in directions:
        key = (d["rid"], d["field"])
        for i, (a, b, mm) in enumerate(zip(d["stops"], d["stops"][1:], d["mm"])):
            if (key, i) in override:
                continue
            if a not in anchors.get((key, i), {a}) or b not in anchors.get((key, i + 1), {b}):
                continue
            add(a, b, mm, (d["number"], d["rid"], d["field"], i))
    for e in checked:
        add(
            e["a"]["id"],
            e["b"]["id"],
            e["mm"],
            (e["number"], e["rid"], e["field"], e["position"]),
        )
    return graph


def platform(p):
    return (p["id"], p["osm"])


def verified_paths(edges, start):
    # При одинаковой длине выбираем поездку с меньшим числом пересадок.
    outgoing = defaultdict(list)
    for i, e in enumerate(edges):
        outgoing[platform(e["a"])].append(i)
    source = (0, 0, -1)
    queue = [source]
    costs = {-1: source[:2]}
    previous = {}
    best = {}
    while queue:
        mm, changes, k = heappop(queue)
        if costs[k] != (mm, changes):
            continue
        p = start if k == -1 else platform(edges[k]["b"])
        if p not in best:
            best[p] = k
        for j in outgoing[p]:
            e = edges[j]
            onward = (
                k != -1
                and e["rid"] == edges[k]["rid"]
                and e["relation"] == edges[k]["relation"]
                and e["position"] == edges[k]["position"] + 1
                and e["platform_index"] == edges[k]["platform_index"] + 1
            )
            score = (mm + e["mm"], changes + int(k != -1 and not onward))
            if j not in costs or score < costs[j]:
                costs[j] = score
                previous[j] = k
                heappush(queue, (*score, j))
    results = {}
    for p, k in best.items():
        score = costs[k]
        steps = []
        while k != -1:
            steps.append(edges[k])
            k = previous[k]
        results[p] = (score, steps[::-1])
    return results
