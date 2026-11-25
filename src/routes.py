"""Кратчайший путь между двумя платформами и таблица по трём периодам."""
import argparse
from statistics import mean

from model import archives, build_graph, platform, verified_paths, year_data
from routing import dijkstra

PAIRS = (
    (("3964", 289765150), ("4269", 1321839897), "От Байкальской улицы до Красноярской улицы, 13"),
    (("4272", 1376671988), ("3965", 289765148), "От 8-го микрорайона до Хабаровской улицы, 4"),
    (("1000303", 856329643), ("1820", 2516761437), "От Абрамцево до Поворота на Мытищи"),
)
YEARS = range(2018, 2027)


def verified_result(graph, edges, a, b):
    score, path = verified_paths(edges, a)[b]
    minimum = dijkstra(graph, a[0])[0][b[0]]
    if score[0] != minimum or sum(e["mm"] for e in path) != minimum:
        raise ValueError("Проверенный маршрут расходится с минимумом годового графа")
    return score, path


def km(mm):
    return f"{mm/1_000_000:.3f}".replace(".", ",")


def table():
    print("Пары остановок и официальные ID")
    for i, (a, b, name) in enumerate(PAIRS, 1):
        print(f"Пара {i}. {name} (ID {a[0]} и {b[0]})")
    print("\nКратчайшие расстояния по трассе, км")
    print("Срез или период     " + "  ".join(f"{label:>12}" for label in ("Пара 1", "Пара 2", "Пара 3")))
    rows = []
    archive = archives()
    for y in YEARS:
        record = archive[str(y)]
        edges = record["edges"]
        graph = build_graph(year_data(y)["directions"], edges)
        row = [verified_result(graph, edges, a, b)[0][0] for a, b, _ in PAIRS]
        rows.append(row)
        print(f"{record['date']:20}" + "  ".join(f"{km(v):>12}" for v in row))
    print("Средние по трём годовым срезам")
    for i in (0, 3, 6):
        print(
            f"{2018+i}-{2020+i}           "
            + "  ".join(f"{km(mean(col)):>12}" for col in zip(*rows[i : i + 3]))
        )


def load_trip_data(year):
    data = year_data(year)
    checked = archives()[str(year)]["edges"]
    names = {p: value[0] for p, value in data["platforms"].items()}
    for leg in checked:
        for p in (leg["a"], leg["b"]):
            names[p["id"]] = p["name"]
    return build_graph(data["directions"], checked), checked, names


def search(year, fragment):
    graph, _, names = load_trip_data(year)
    ids = set(graph) | {b for neighbours in graph.values() for b in neighbours}
    query = fragment.casefold().replace("ё", "е").strip()
    if not query:
        raise SystemExit("Введите часть названия остановки.")
    matches = sorted((names[p], p) for p in ids if query in names[p].casefold().replace("ё", "е"))
    for name, p in matches:
        following = sorted({names[b] for b in graph.get(p, {})})
        hint = ", ".join(following) if following else "конечная в графе"
        print(f"{p:>8}  {name}. Дальше: {hint}")
    if not matches:
        print("В графе этого года совпадений нет.")


def show(year, start, end):
    graph, edges, names = load_trip_data(year)
    targets = {platform(e["b"]) for e in edges if e["b"]["id"] == end}
    distance, previous = dijkstra(graph, start)
    if end not in distance or (
        start == end and start not in graph and not any(start in near for near in graph.values())
    ):
        raise SystemExit("Для этой пары путь в годовом графе не найден.")
    options = []
    for origin in sorted({platform(e["a"]) for e in edges if e["a"]["id"] == start}):
        routes = verified_paths(edges, origin)
        for dest in sorted(targets.intersection(routes)):
            score, steps = routes[dest]
            if score[0] == distance[end] and steps:
                options.append((score, steps))
    print(
        f"{year} г. От остановки «{names[start]}» до остановки «{names[end]}». {km(distance[end])} км."
    )
    if options:
        (_, changes), steps = min(options, key=lambda x: x[0])
        print(f"Архивная проверка всех перегонов. Пересадок в поездке: {changes}.")
        prev = None
        for e in steps:
            transfer = bool(prev) and (
                prev["relation"] != e["relation"]
                or prev["position"] + 1 != e["position"]
                or prev["platform_index"] + 1 != e["platform_index"]
                or prev["rid"] != e["rid"]
            )
            if transfer:
                print(
                    f"  Пересадка на платформе {e['a']['name']} (ID {e['a']['id']}, OSM {e['a']['osm']})"
                )
            print(
                f"  Маршрут {e['number']}   от «{e['a']['name']}» до «{e['b']['name']}»   {km(e['mm'])} км"
                f"   [OSM {e['relation']} v{e['version']}, реестр {e['rid']}]"
            )
            prev = e
    else:
        print("Модельный путь. Полная архивная проверка этой поездки отсутствует.")
        path = [end]
        while path[-1] != start:
            path.append(previous[path[-1]])
        path.reverse()
        for a, b in zip(path, path[1:]):
            mm, service = graph[a][b]
            print(f"  Маршрут {service[0]}, от «{names[a]}» до «{names[b]}», {km(mm)} км")


def main():
    parser = argparse.ArgumentParser(
        description="Кратчайшие пути Москвы. Без аргументов выводится таблица по годам и периодам."
    )
    parser.add_argument("year", type=int, choices=YEARS, nargs="?")
    parser.add_argument("start", nargs="?")
    parser.add_argument("end", nargs="?")
    parser.add_argument("--find", metavar="НАЗВАНИЕ", help="Найти ID платформ по части названия")
    args = parser.parse_args()
    if args.find is not None:
        if args.year is None or args.start or args.end:
            parser.error("Для поиска укажите год и часть названия после --find")
        return search(args.year, args.find)
    if all(x is None for x in (args.year, args.start, args.end)):
        table()
    elif None in (args.year, args.start, args.end):
        parser.error("Для отдельной поездки укажите год и два ID платформ.")
    else:
        show(args.year, args.start, args.end)


if __name__ == "__main__":
    main()
