"""Turn spoken numbers in a radio transcript into digits.

Whisper usually writes digits, but about 1 in 8 unit numbers on the fire
channels came out as words: "Engine twenty-three sixty-three", "Medic
fifty-three", "seventeen twenty-three", "two zero one". This rewrites
those runs the way radio says them:

  twenty-three sixty-three  -> 2363   (pairs make one ID or time)
  seventeen twenty-three    -> 1723
  two zero one              -> 201    (digit by digit)
  fifteen hundred           -> 1500
  ten-four                  -> 10-4
  Medic two                 -> Medic 2 (a lone digit only after a unit word)
  Medic one, twenty nineteen -> Medic 1, 2019 (a comma ends a run)

A lone "one"/"two" elsewhere stays a word ("one engine to 30", "no one").
"""

import re

_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
         "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_NUMBER_WORDS = set(_ONES) | set(_TEENS) | set(_TENS) | {"hundred"}

# Words after which a lone digit word is a radio ID: "Medic two", "Engine five".
_UNIT_WORDS = {
    "engine", "medic", "battalion", "truck", "rescue", "squad", "ambulance",
    "amr", "copter", "helicopter", "helitack", "helitanker", "dozer", "tender",
    "transport", "patrol", "utility", "attack", "recon", "tanker", "crew",
    "division", "chief", "prevention", "unit", "ht", "station", "district",
}

_WORD = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def _groups(words):
    """Digit strings for one run of number words.

    Each group is (digits, kind): kind "d" for a digit-by-digit run
    ("two zero one"), "n" for a spoken number ("twenty-three", "fifteen
    hundred").
    """
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if w in _TENS:
            v = _TENS[w]
            if i + 1 < len(words) and words[i + 1] in _ONES and words[i + 1] != "zero":
                v += _ONES[words[i + 1]]
                i += 1
            out.append([str(v), "n"])
        elif w in _TEENS:
            out.append([str(_TEENS[w]), "n"])
        elif w == "hundred":
            if out and len(out[-1][0]) <= 2 and out[-1][0][0] != "0":
                base = int(out.pop()[0]) * 100
                rest = 0
                if i + 1 < len(words) and words[i + 1] in _TENS:
                    rest = _TENS[words[i + 1]]
                    i += 1
                    if i + 1 < len(words) and words[i + 1] in _ONES and words[i + 1] != "zero":
                        rest += _ONES[words[i + 1]]
                        i += 1
                elif i + 1 < len(words) and words[i + 1] in _TEENS:
                    rest = _TEENS[words[i + 1]]
                    i += 1
                out.append([str(base + rest), "n"])
            else:
                out.append(["100", "n"])
        else:
            d = str(_ONES[w])
            if out and out[-1][1] == "d":
                out[-1][0] += d
            else:
                out.append([d, "d"])
        i += 1
    return out


def _join(groups):
    """Adjacent two-digit groups pair into one ID or time: "23 63" -> "2363",
    "17 23" -> "1723", "19 03" -> "1903"; "fifteen hundred" is already 1500."""
    parts = []
    i = 0
    while i < len(groups):
        g, _kind = groups[i]
        if len(g) == 2 and i + 1 < len(groups) and len(groups[i + 1][0]) == 2:
            parts.append(g + groups[i + 1][0])
            i += 2
            continue
        parts.append(g)
        i += 1
    return " ".join(parts)


def spoken_numbers_to_digits(text: str) -> str:
    if not text:
        return text
    tokens = _WORD.findall(text)
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low not in _NUMBER_WORDS:
            out.append(tok)
            i += 1
            continue
        # Collect a run of number words joined by spaces or hyphens. A comma
        # ends the run: Whisper writes "Medic one, twenty nineteen" with the
        # comma between the unit and the time.
        run = [low]
        j = i + 1
        while j + 1 < len(tokens) and re.fullmatch(r"[\s-]+", tokens[j]) \
                and tokens[j + 1].lower() in _NUMBER_WORDS \
                and len(tokens[j].strip()) <= 1:
            run.append(tokens[j + 1].lower())
            j += 2
        prev = ""
        for k in range(len(out) - 1, -1, -1):
            if out[k].strip():
                prev = out[k].strip().lower()
                break
        if run in (["ten", "four"],):
            out.append("10-4")
            i = j
            continue
        convert = (len(run) >= 2 or run[0] not in _ONES or prev in _UNIT_WORDS)
        if not convert:
            out.append(tok)
            i += 1
            continue
        out.append(_join(_groups(run)))
        i = j
    return "".join(out)
