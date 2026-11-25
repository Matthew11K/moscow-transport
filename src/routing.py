"""Алгоритм Дейкстры для ориентированного графа с неотрицательными весами."""
import heapq


def dijkstra(edges, start):
    dist = {start: 0}
    pred = {}
    queue = [(0, start)]
    while queue:
        cost, u = heapq.heappop(queue)
        if cost != dist[u]:
            continue
        for v, (w, _) in edges.get(u, {}).items():
            new = cost + w
            if v not in dist or new < dist[v]:
                dist[v] = new
                pred[v] = u
                heapq.heappush(queue, (new, v))
    return dist, pred
