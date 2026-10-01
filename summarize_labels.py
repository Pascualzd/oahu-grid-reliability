"""Spell an outage label from contingency.csv in words (shared by makefigs.py)."""
import csv, os
HERE = os.path.dirname(os.path.abspath(__file__))
NCIR = {f'{b["from_bus"]}-{b["to_bus"]}': int(b["circuits"])
        for b in csv.DictReader(open(os.path.join(HERE, "data", "network_branches.csv")))}
DASH = lambda s: s.replace("-", "\u2013")

def pretty(outage):
    if outage.startswith("two of"):
        n, name = outage.split()[2], " ".join(outage.split()[3:])
        return (f"both {DASH(name)} circuits" if n == "2"
                else f"two of the {n} {DASH(name)} circuits")
    if outage.startswith("one of"):
        return f"one {DASH(' '.join(outage.split()[3:]))} circuit"
    parts = []
    for x in outage.split("+"):
        x = x.strip()
        parts.append(f"one {DASH(x)} circuit" if NCIR.get(x, 1) > 1 else DASH(x))
    return " + ".join(parts)


def short(outage):
    """The same, in the fewest words: 'both Koolau-Pukele', '1 Waiau-Makalapa + 1 Halawa-Downtown'."""
    if outage.startswith("two of"):
        n, name = outage.split()[2], " ".join(outage.split()[3:])
        return f"both {DASH(name)}" if n == "2" else f"2 of 3 {DASH(name)}"
    parts = []
    for x in outage.split("+"):
        x = x.strip()
        parts.append(f"1 {DASH(x)}" if NCIR.get(x, 1) > 1 else DASH(x))
    return " + ".join(parts)
