#!/usr/bin/env python3
"""
build_demand_puc.py -- a second demand file for the sensitivity run.

WHY
build_demand.py places load from census people and census jobs. The only
substation-level numbers Hawaiian Electric has ever filed publicly are three
shares of the 2002 DAY PEAK, in Hawai'i PUC Decision & Order No. 23747
(Docket 03-0417, 2007):

    Pukele                     "approximately seventeen percent of the Oahu load"  (p. 8)
    Koolau + Pukele            "approximately thirty percent"                     (p. 6)
    Iwilei + School St + HPP   "about twenty-five percent ... at the 2002 Day Peak" (p. 7)

Our census build gives Pukele 14.1 %, Koolau + Pukele 20.3 % and Downtown 38.4 %
of the 2021 day peak. The two cannot both be right for 2021: 2002 is nineteen
years earlier, and Kaka'ako has since grown. So the results are re-run with
the filed shares as a check on how much the conclusions depend on the split.

HOW
Every substation's hourly series is multiplied by one constant k_b, chosen so
that its day-peak share becomes the filed one:
    Pukele 17 %, Koolau 13 % (= 30 - 17), Downtown 25 %,
    and the other seven substations keep their relative sizes and share the
    remaining 45 %.
Then every hour is rescaled so the island total is unchanged. The shape of
each substation's day and year is kept; only its size changes.

"Day peak" is measured exactly as in build_demand.py: the 50 highest-load
hours between 10:00 and 16:00.

    python3 build_demand_puc.py      # writes data/bus_hourly_demand_puc.csv
"""
import csv, datetime, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "data" / "bus_hourly_demand.csv"
DST = HERE / "data" / "bus_hourly_demand_puc.csv"
FILED = {"Pukele": 0.17, "Koolau": 0.13, "Downtown": 0.25}


def day_peak_share(rows, buses):
    day = [r for r in rows if 10 <= datetime.datetime.fromisoformat(r["timestamp_hst"]).hour <= 16]
    top = sorted(day, key=lambda r: -float(r["net_load_mw"]))[:50]
    tot = sum(float(r["net_load_mw"]) for r in top)
    return {b: sum(float(r[f"load_{b}_mw"]) for r in top) / tot for b in buses}


def main():
    rows = list(csv.DictReader(open(SRC)))
    cols = [c for c in rows[0] if c.startswith("load_")]
    buses = [c[5:-3] for c in cols]
    share = day_peak_share(rows, buses)
    rest = [b for b in buses if b not in FILED and share[b] > 0]
    rest_now = sum(share[b] for b in rest)
    target = dict(FILED)
    for b in rest:
        target[b] = share[b] / rest_now * (1 - sum(FILED.values()))
    k = {b: (target[b] / share[b] if share[b] > 0 else 0.0) for b in buses}

    out = []
    for r in rows:
        net = float(r["net_load_mw"])
        raw = {b: k[b] * float(r[f"load_{b}_mw"]) for b in buses}
        s = sum(raw.values())
        new = dict(r)
        for b in buses:
            new[f"load_{b}_mw"] = f"{raw[b] * net / s:.4f}"
        out.append(new)
    with open(DST, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(out)

    after = day_peak_share(out, buses)
    print(f"{'substation':10s} {'census':>8s} {'filed/target':>13s} {'after':>7s} {'k':>6s}")
    for b in buses:
        if share[b] > 0:
            print(f"{b:10s} {share[b]:8.1%} {target[b]:13.1%} {after[b]:7.1%} {k[b]:6.3f}")
    worst = max(abs(sum(float(r[c]) for c in cols) - float(r["net_load_mw"])) for r in out)
    print(f"island total preserved to within {worst:.4f} MW in every hour")


if __name__ == "__main__":
    main()
