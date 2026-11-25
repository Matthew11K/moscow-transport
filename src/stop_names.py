"""Названия остановок и варианты сокращений в реестре Москвы."""
import re


def normalize(s):
    s = s.casefold().replace("ё", "е").replace("«", '"').replace("»", '"')
    s = re.sub(r"\bул\.", "улица", s)
    return re.sub(r"\s*-\s*", "-", s).strip()


def labels(s):
    # В реестре пробелы около дефиса иногда разрывают одно название.
    s = re.sub(r"(Солнцево|Ново) - (Парк|Переделкино)", r"\1-\2", s)
    s = s.replace("Реабилитационно - образовательный", "Реабилитационно-образовательный")
    s = re.sub(r"(\d) - (я|й)\b", r"\1-\2", s)
    return re.split(r"\s+[-\u2013\u2014]\s+", s)


def stop_labels(text, stops):
    tokens = [normalize(s) for s in labels(text) if s.strip()]

    names = []
    i = 0
    while i < len(tokens):
        # Не объединяем два известных названия. Для пропущенного фрагмента
        # проверяем, образует ли он с соседом точное название из справочника.
        for width in (3, 2):
            part = tokens[i : i + width]
            joined = "-".join(part)
            if len(part) == width and joined in stops and any(t not in stops for t in part):
                names.append(joined)
                i += width
                break
        else:
            names.append(tokens[i])
            i += 1
    return names


WORDS = {
    "просп.": "проспект",
    "бул.": "бульвар",
    "бульв.": "бульвар",
    "пер.": "переулок",
    "пл.": "площадь",
    "ал.": "аллея",
    "ш.": "шоссе",
    "мкр.": "микрорайон",
    "п-ка": "поликлиника",
    "б-ца": "больница",
    "к/т": "кинотеатр",
    "з-д": "завод",
    "ф-ка": "фабрика",
    "акад.": "академика",
    "им.": "имени",
    "марш.": "маршала",
    "ген.": "генерала",
    "ин-т": "институт",
    "кладб.": "кладбище",
    "кв-л": "квартал",
}
pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, WORDS)) + r")(?!\w)")


def expand(name):
    return pattern.sub(lambda m: WORDS[m.group()], name)


SHORT = {
    "проезд": "пр.",
    "проспект": "пр.",
    "большая": "б.",
    "большой": "б.",
    "большие": "б.",
    "малая": "м.",
    "малый": "м.",
    "малые": "м.",
    "верхняя": "верхн.",
    "верхние": "верхн.",
    "нижние": "нижн.",
    "нижняя": "нижн.",
    "набережная": "наб.",
    "квартал": "кв.",
    "музыкальная": "муз.",
    "трамвайное": "трамв.",
    "адмирала": "адм.",
    "городская": "гор.",
    "магазин": "м-н",
    "гостиница": "гост.",
    "платформа": "платф.",
    "поселок": "пос.",
    "медицинский": "мед.",
    "дом культуры": "д/к",
    "километр": "км.",
}
ABBREV_WORDS = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, SHORT)) + r")(?!\w)")


def key(name):
    return ABBREV_WORDS.sub(lambda m: SHORT[m.group()], name)


ABBREVIATIONS = re.compile(
    r"(?<!\w)("
    + "|".join(map(re.escape, sorted(set(SHORT.values()), key=len, reverse=True)))
    + r")(?!\w)"
)


def expansion_pattern(name):
    pieces = []
    pos = 0
    for match in ABBREVIATIONS.finditer(name):
        pieces.append(re.escape(name[pos : match.start()]))
        forms = [match.group(), *(word for word, abbr in SHORT.items() if abbr == match.group())]
        pieces.append("(?:" + "|".join(map(re.escape, forms)) + ")")
        pos = match.end()
    pieces.append(re.escape(name[pos:]))
    return re.compile("".join(pieces))
