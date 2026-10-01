#!/usr/bin/env python3
"""
summarize.py -- every number quoted in paper.tex, computed from the output files.

Run after run_all.jl, contingency.jl (base, low, high, puc) and stress.jl.
Prints the tables of the paper and writes out/paper_numbers.json, which the
check at the end of this script compares against the numbers typed in paper.tex.

    python3 summarize.py
"""
import csv, json, math, os, re, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D, O = os.path.join(HERE, "data"), os.path.join(HERE, "out")
rows = lambda p: list(csv.DictReader(open(p)))
N = {}

# ------------------------------------------------------------------ small N-0 summaries
# run_all.jl writes one column per hour/draw (large files, not committed). Keep the few
# numbers the paper uses: per-line loading (mean, max) and per-bus generation.
def wide(p, k):
    r = list(csv.reader(open(p))); return r[0], r[1:], k
if os.path.exists(f"{O}/util_by_line_actual.csv"):
    with open(f"{O}/n0_lines.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["line", "from", "to", "rate_mw", "arm", "mean_loading", "max_loading",
                                        "share_at_limit"])
        for arm in ("actual", "fitted", "corr"):
            r = list(csv.reader(open(f"{O}/util_by_line_{arm}.csv")))
            for x in r[1:]:
                u = np.array([float(v) for v in x[4:]])
                w.writerow([x[0], x[1], x[2], x[3], arm, f"{u.mean():.6f}", f"{u.max():.6f}",
                            f"{(u >= 0.999).mean():.6f}"])
    with open(f"{O}/n0_genbus.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["bus", "arm", "min_mw", "mean_mw", "max_mw"])
        for arm in ("actual", "fitted", "corr"):
            r = list(csv.reader(open(f"{O}/genbus_by_hour_{arm}.csv")))
            for x in r[1:]:
                v = np.array([float(t) for t in x[1:]])
                w.writerow([x[0], arm, f"{v.min():.4f}", f"{v.mean():.4f}", f"{v.max():.4f}"])

# ------------------------------------------------------------------ network
BR = rows(f"{D}/network_branches.csv"); GEN = rows(f"{D}/generators.csv")
N["n_bus"] = len(rows(f"{D}/network_buses.csv")); N["n_corr"] = len(BR)
N["n_circ"] = sum(int(b["circuits"]) for b in BR)
N["miles_total"] = sum(float(b["length_mi"]) * int(b["circuits"]) for b in BR)
N["n_gen"] = len(GEN); N["fleet_mw"] = sum(float(g["p_max_mw"]) for g in GEN)
genbus = collections.defaultdict(float)
for g in GEN: genbus[g["bus"]] += float(g["p_max_mw"])
N["gen_by_bus"] = dict(genbus)
N["cost_min"] = min(float(g["varcost_usd_per_mwh"]) for g in GEN)
N["cost_max"] = max(float(g["varcost_usd_per_mwh"]) for g in GEN)

# ------------------------------------------------------------------ demand
fit = rows(f"{O}/bus_fit.csv")
N["bus_fit"] = {r["bus"]: (float(r["mu_mw"]), float(r["sigma_mw"])) for r in fit}
tot = {a: np.array([float(r["total_mw"]) for r in rows(f"{O}/draws_{a}.csv")])
       for a in ("actual", "fitted", "corr")}
for a in tot:
    N[f"tot_{a}"] = dict(mean=tot[a].mean(), sd=tot[a].std(ddof=1), max=tot[a].max(),
                         min=tot[a].min())
cor = rows(f"{O}/bus_corr.csv")
cv = [float(r[k]) for r in cor for k in r if k != "bus" and k != r["bus"]
      and r["bus"] != "Kalaeloa" and k != "Kalaeloa"]
N["corr_min"], N["corr_max"], N["corr_mean"] = min(cv), max(cv), float(np.mean(cv))
H = rows(f"{D}/bus_hourly_demand.csv")
for b in ("Downtown", "Pukele"):
    x = np.array([float(r[f"load_{b}_mw"]) for r in H]); m, s = N["bus_fit"][b]
    N[f"within1sd_{b}"] = float(np.mean(np.abs(x - m) <= s))
rep = json.load(open(f"{D}/demand_build_report.json"))
N["peak_share"] = rep["peak_share"]

# ------------------------------------------------------------------ contingencies
def cont(tag):
    d = O if tag == "base" else os.path.join(HERE, f"out_{tag}")
    return rows(f"{d}/contingency.csv"), rows(f"{d}/contingency_lines.csv")

def pretty(outage):
    """'Kahe-Halawa + Waiau-Makalapa' -> one circuit each, spelled out."""
    ncir = {f'{b["from_bus"]}-{b["to_bus"]}': int(b["circuits"]) for b in BR}
    def one(x):
        x = x.strip()
        return f"one {x} circuit" if ncir.get(x, 1) > 1 else f"{x}"
    if outage.startswith("two of"):
        n, name = outage.split()[2], " ".join(outage.split()[3:])
        return f"both {name} circuits" if n == "2" else f"two of the {n} {name} circuits"
    if outage.startswith("one of"):
        return f"one {' '.join(outage.split()[3:])} circuit"
    return " + ".join(one(x) for x in outage.split("+"))

S = {}
for tag in ("base", "low", "high", "puc", "noise10", "noise25", "noise50"):
    try:
        C, L = cont(tag)
    except FileNotFoundError:
        continue
    s = {}
    for kind in ("N-0", "N-1", "N-2"):
        for arm in ("actual", "random"):
            sub = [r for r in C if r["kind"] == kind and r["arm"] == arm]
            s[f"{kind}_{arm}_cases"] = len(sub)
            s[f"{kind}_{arm}_cases_short"] = sum(int(r["hours_short"]) > 0 for r in sub)
            s[f"{kind}_{arm}_cases_limit"] = sum(bool(r["lines_at_limit"]) for r in sub)
    s["n0_maxload"] = {arm: max(float(r["max_loading"]) for r in L
                                if r["kind"] == "N-0" and r["arm"] == arm) for arm in ("actual", "random")}
    s["short"] = [dict(outage=r["outage"], label=pretty(r["outage"]), kind=r["kind"], arm=r["arm"],
                       n=int(r["n"]), hours=int(r["hours_short"]), mwh=float(r["mwh_short"]),
                       worst=float(r["worst_mw"]), areas=r["areas_short"], lines=r["lines_at_limit"])
                  for r in C if int(r["hours_short"]) > 0]
    s["n1_limits"] = [dict(outage=r["outage"], label=pretty(r["outage"]), arm=r["arm"],
                           lines=r["lines_at_limit"]) for r in C
                      if r["kind"] == "N-1" and r["lines_at_limit"]]
    # per line: how many (outage, hour) pairs put it at its limit, N-1 and N-2
    per = collections.defaultdict(lambda: collections.Counter())
    for r in L:
        if r["kind"] in ("N-1", "N-2"):
            per[(r["kind"], r["arm"])][r["line"]] += int(r["hours_at_limit"])
    s["line_limit_hours"] = {f"{k[0]}_{k[1]}": dict(v) for k, v in per.items()}
    S[tag] = s
N["cont"] = S

# ------------------------------------------------------------------ growth
try:
    ST = rows(f"{O}/stress_system.csv"); SB = rows(f"{O}/stress_by_bus.csv")
    SL = rows(f"{O}/stress_by_line.csv")
    g = {}
    for arm in ("actual", "random"):
        sys = [r for r in ST if r["arm"] == arm]
        first_line = next((float(r["level"]) for r in sys if float(r["pct_any_line_at_limit"]) > 0), None)
        first_gen = next((float(r["level"]) for r in sys if float(r["pct_short_generation"]) > 0), None)
        first_wire = next((float(r["level"]) for r in sys if float(r["pct_short_wires"]) > 0), None)
        g[arm] = dict(first_line=first_line, first_gen=first_gen, first_wire=first_wire,
                      table=[{k: float(r[k]) for k in r if k != "arm"} for r in sys])
        if first_line:
            g[arm]["first_lines"] = [r["line"] for r in SL if r["arm"] == arm and
                                     float(r["level"]) == first_line and float(r["pct_at_limit"]) > 0]
        g[arm]["wire_areas"] = {}
        for r in SB:
            if r["arm"] == arm and float(r["pct_short_wires"]) > 0:
                g[arm]["wire_areas"].setdefault(r["bus"], float(r["level"]))
    N["growth"] = g
except FileNotFoundError:
    pass

json.dump(N, open(f"{O}/paper_numbers.json", "w"), indent=1, default=float)

# ------------------------------------------------------------------ print
print(f"network: {N['n_bus']} substations, {N['n_corr']} corridors, {N['n_circ']} circuits, "
      f"{N['miles_total']:.0f} circuit-miles; {N['n_gen']} units, {N['fleet_mw']:.1f} MW")
print("generation by bus:", {k: round(v, 1) for k, v in genbus.items()})
print(f"costs {N['cost_min']:.2f} .. {N['cost_max']:.2f} $/MWh")
for a in tot:
    t = N[f"tot_{a}"]; print(f"island total {a:7s} mean {t['mean']:.1f} sd {t['sd']:.1f} "
                             f"min {t['min']:.1f} max {t['max']:.1f}")
print(f"correlation between substations: {N['corr_min']:.2f} .. {N['corr_max']:.2f}, mean {N['corr_mean']:.2f}")
print("share of hours within one sigma:", {b: round(N[f'within1sd_{b}'], 3) for b in ("Downtown", "Pukele")})
print("\nsubstation   mu     sigma   cv    day-peak share")
for b, (m, s_) in N["bus_fit"].items():
    if m > 0:
        print(f"  {b:10s} {m:6.1f} {s_:6.1f} {s_/m:5.2f}  {N['peak_share'][b]:.1%}")
for tag, s in S.items():
    print(f"\n==== {tag}: N-0 max loading actual {s['n0_maxload']['actual']:.3f} random {s['n0_maxload']['random']:.3f}")
    for kind in ("N-0", "N-1", "N-2"):
        print(f"  {kind}: cases {s[f'{kind}_actual_cases']}, with loss actual "
              f"{s[f'{kind}_actual_cases_short']} random {s[f'{kind}_random_cases_short']}; "
              f"with a line at its limit actual {s[f'{kind}_actual_cases_limit']} random {s[f'{kind}_random_cases_limit']}")
    for r in s["short"]:
        print(f"   {r['kind']} {r['label']:48s} {r['arm']:6s} {r['hours']:5d}/{r['n']:5d} "
              f"{100*r['hours']/r['n']:6.2f}%  {r['mwh']:9.0f} MWh  worst {r['worst']:6.1f} | {r['areas']} | {r['lines']}")
    if tag == "base":
        for r in s["n1_limits"]:
            print(f"   N-1 limit: {r['label']:40s} {r['arm']:6s} {r['lines']}")
if "growth" in N:
    for arm, gg in N["growth"].items():
        print(f"\ngrowth {arm}: first line at limit {gg['first_line']} ({gg.get('first_lines')}), "
              f"first generation shortage {gg['first_gen']}, first wire shortage {gg['first_wire']} {gg['wire_areas']}")
        for r in gg["table"]:
            print(f"   g {r['level']:.1f} mean {r['mean_load_mw']:7.1f} peak {r['peak_load_mw']:7.1f} "
                  f"short {r['pct_short_network']:6.2f}% gen {r['pct_short_generation']:6.2f}% "
                  f"wires {r['pct_short_wires']:6.2f}% line-at-limit {r['pct_any_line_at_limit']:6.2f}%")

# ------------------------------------------------------------------ LaTeX rows
def tex_line_table(tag="base"):
    C, L = cont(tag)
    lines = [f'{b["from_bus"]}-{b["to_bus"]}' for b in BR]
    out = []
    for ln in lines:
        r0a = next(r for r in L if r["kind"] == "N-0" and r["arm"] == "actual" and r["line"] == ln)
        r0r = next(r for r in L if r["kind"] == "N-0" and r["arm"] == "random" and r["line"] == ln)
        def agg(kind, arm):
            rr = [r for r in L if r["kind"] == kind and r["arm"] == arm and r["line"] == ln]
            return sum(int(r["hours_at_limit"]) > 0 for r in rr), sum(int(r["hours_at_limit"]) for r in rr)
        c1a, h1a = agg("N-1", "actual"); c1r, h1r = agg("N-1", "random")
        c2a, h2a = agg("N-2", "actual"); c2r, h2r = agg("N-2", "random")
        out.append((h2a + h1a, h2r + h1r, ln, float(r0a["max_loading"]), float(r0r["max_loading"]),
                    c1a, h1a, c1r, h1r, c2a, h2a, c2r, h2r))
    out.sort(key=lambda x: (-x[0], -x[1], -x[3]))
    print("\n% line table (" + tag + ")")
    for (_, _, ln, m0a, m0r, c1a, h1a, c1r, h1r, c2a, h2a, c2r, h2r) in out:
        f = lambda c, h: "---" if c == 0 else f"{c} / \\num{{{h}}}"
        print(f"{ln.replace('-', '--')} & {100*m0a:.0f}\\% & {100*m0r:.0f}\\% & {f(c1a, h1a)} & {f(c1r, h1r)} "
              f"& {f(c2a, h2a)} & {f(c2r, h2r)} \\\\")

tex_line_table()
