"""Поиск кратчайшего пути по списку перегонов из CSV."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from routing import dijkstra


def main():
    parser = argparse.ArgumentParser(description="Кратчайший путь по подготовленному CSV")
    parser.add_argument("csv", type=Path)
    parser.add_argument("start", help="ID платформы отправления")
    parser.add_argument("end", help="ID платформы прибытия")
    args = parser.parse_args()

    graph = defaultdict(dict)
    names = {}
    with args.csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        for row in reader:
            a = row["ID платформы отправления"]
            b = row["ID платформы прибытия"]
            mm = int(row["Длина направленного перегона, мм"])
            if mm <= 0 or b in graph[a]:
                parser.error(f"Недопустимая длина или повтор перегона в строке {reader.line_num}")
            graph[a][b] = (mm, None)
            names[a] = row["Название платформы отправления"]
            names[b] = row["Название платформы прибытия"]

    print(f"Загружено перегонов: {sum(map(len, graph.values()))}. Платформ: {len(names)}.")
    if args.start not in names or args.end not in names:
        parser.error("Платформа отсутствует во входном файле")
    distances, previous = dijkstra(graph, args.start)
    if args.end not in distances:
        print("Путь отсутствует в данном графе.")
        return
    path = [args.end]
    while path[-1] != args.start:
        path.append(previous[path[-1]])
    for i, p in enumerate(reversed(path), 1):
        print(f"{i}. {names[p]} (ID {p})")
    print(f"{distances[args.end]} мм = {distances[args.end] / 1_000_000:.6f} км")


if __name__ == "__main__":
    main()
