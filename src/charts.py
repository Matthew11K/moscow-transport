"""Годовые диаграммы длины, плотности и топологической связности."""
import json
from statistics import mean
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
from geometry import RESULTS


def length_and_density(data):
    area = data["area_km2"]
    years = [row["year"] for row in data["years"]]
    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.8), sharex=True)
    fig.subplots_adjust(left=0.125, right=0.865, bottom=0.14, top=0.84, hspace=0.43)
    fig.text(
        0.075, 0.955, "Длина и плотность наземной маршрутной сети Москвы", size=19, weight="bold"
    )
    fig.text(
        0.075,
        0.911,
        "Девять срезов реестра в одной границе города. Справа показана плотность при площади 2 562,63 кв. км.",
        size=10.5,
        color="#455764",
    )
    fmt = FuncFormatter(lambda v, pos: f"{v:,.0f}".replace(",", " "))
    for idx, ax in enumerate(axes):
        color = ("#354e75", "#007269")[idx]
        y = [r["route_km"] if idx == 0 else r["grids"]["10"]["km"] for r in data["years"]]
        ax.set_title(
            ("Сумма длин маршрутов и направлений", "Длина объединённых линий")[idx],
            loc="left",
            size=13,
            pad=8,
            weight="bold",
        )
        ax.plot(years, y, marker="o", color=color, linewidth=2.3, label="Сетка 10 м", zorder=4)
        if idx:
            bounds = [[r["grids"][k]["km"] for k in ("5", "10", "20")] for r in data["years"]]
            ax.fill_between(
                years,
                list(map(min, bounds)),
                list(map(max, bounds)),
                alpha=0.16,
                color=color,
                label="Разброс при шагах 5, 10 и 20 м",
            )
            ax.legend(loc="lower right", fontsize=9, frameon=False)
        ax.set_xlim(2017.6, 2026.4)
        ax.margins(y=0.22)
        ax.set_ylabel("Длина, км")
        ax.yaxis.set_major_formatter(fmt)
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.grid(axis="y", color="#dae0e4")
        ax.set_axisbelow(True)
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_xticks(years)
        sec = ax.secondary_yaxis("right", functions=(lambda v: v / area, lambda d: d * area))
        sec.set_ylabel("Плотность, км на кв. км", labelpad=10)
        sec.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.1f}".replace(".", ",")))
        for boundary in (2020.5, 2023.5):
            ax.axvline(boundary, ls=":", lw=1, color="#83939b")
    fig.text(
        0.075,
        0.047,
        "В 2025 г. у одной записи отсутствует геометрия. Последний срез получен 6 октября 2026 г.",
        fontsize=10,
        color="#455764",
    )
    fig.savefig(RESULTS / "length_density.png", dpi=180, facecolor="white")
    plt.close(fig)


def connectivity(rows):
    years = [r["year"] for r in rows]
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(9, 6.2), height_ratios=[2.4, 1], layout="constrained"
    )
    colors = {5: "#a26520", 10: "#173f78", 20: "#368374"}
    periods = {}
    for grid in (5, 20, 10):
        values = [r["grids"][str(grid)]["gamma"] for r in rows]
        periods[grid] = [mean(values[i : i + 3]) for i in (0, 3, 6)]
        thick = grid == 10
        ax.plot(
            years,
            values,
            color=colors[grid],
            linestyle="-" if thick else "--",
            marker="o" if thick else None,
            linewidth=2 if thick else 1.3,
            label=f"Шаг {grid} м",
        )
        ax2.plot(
            [0, 1, 2],
            periods[grid],
            color=colors[grid],
            linestyle="-" if thick else "--",
            marker="o",
            linewidth=2 if thick else 1.3,
        )
        if thick:
            for year, v in zip(years, values):
                ax.annotate(
                    f"{v:.3f}".replace(".", ","),
                    (year, v),
                    xytext=(0, 9),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
    for a in (ax, ax2):
        a.grid(axis="y", alpha=0.2)
        a.spines[["top", "right"]].set_visible(False)
        a.set_ylabel("Индекс Канского")
        a.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:.3f}".replace(".", ",")))
    ax.set_ylim(0.487, 0.536)
    ax.set_xticks(years)
    ax.legend(loc="lower right", ncol=3, fontsize=8)
    ax.set_title("Связность планарной схемы наземных маршрутов Москвы", loc="left", weight="bold")
    ax2.set_xticks([0, 1, 2], ["2018-2020", "2021-2023", "2024-2026"])
    ax2.set_title("Среднее трёх годовых значений", loc="left", fontsize=11)
    fig.supxlabel(
        "Срезы с 2018 по 2025 год взяты за декабрь, за 2026 год на 6 октября. Шаг округления координат указан в метрах.",
        fontsize=9,
    )
    fig.savefig(RESULTS / "connectivity.png", dpi=185)
    plt.close(fig)


if __name__ == "__main__":
    data = json.loads((RESULTS / "network.json").read_bytes())
    length_and_density(data)
    connectivity(data["years"])
