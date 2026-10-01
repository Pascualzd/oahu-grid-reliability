#!/usr/bin/env python3
"""
check_numbers.py -- recompute every number quoted in paper.tex from the output files
and confirm the text says the same thing. Prints one line per claim; exits non-zero
if any claim fails.

    python3 check_numbers.py
"""
import csv, json, os, re, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D, O = os.path.join(HERE, "data"), os.path.join(HERE, "out")
RAW = open(os.path.join(HERE, "paper.tex")).read()
TEX = re.sub(r"[ \t]*\n[ \t]*", " ", RAW)
TEX = re.sub(r" +", " ", TEX)
norm = lambda t: re.sub(r"\s+", " ", t)
rows = lambda p: list(csv.DictReader(open(p)))
fails = 0

def claim(desc, value, text, fmt="{:.1f}"):
    """value: the recomputed number; text: the exact string the paper must contain."""
    global fails
    shown = fmt.format(value) if value is not None else ""
    text = norm(text)
    if fmt == "words":
        shown = {3: "three"}.get(value, str(value))
    ok = text in TEX and (value is None or shown in text.replace("{,}", ",").replace("\\,", "")
                          or shown.replace(",", "") in text.replace("{,}", "").replace(",", ""))
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {desc:58s} computed {shown:>12s}   text: {text[:60]}")

# ---- network and fleet
BR = rows(f"{D}/network_branches.csv"); GEN = rows(f"{D}/generators.csv")
claim("substations", len(rows(f"{D}/network_buses.csv")), "11 substations", "{:d}")
claim("corridors", len(BR), "16 corridors carrying 25 circuits", "{:d}")
claim("circuits", sum(int(b["circuits"]) for b in BR), "16 corridors carrying 25 circuits", "{:d}")
claim("fleet MW", sum(float(g["p_max_mw"]) for g in GEN), "\\SI{1508.1}{MW} in total", "{:.1f}")
claim("units", len(GEN), "24 dispatchable units", "{:d}")
for b in BR:
    row = [norm(l) for l in RAW.split("\n") if l.startswith(f'{b["from_bus"]}--{b["to_bus"]} ')]
    ok = row and f'& {b["circuits"]} & {float(b["length_mi"]):.2f}' in row[0].replace("  ", " ") \
         and f'{float(b["limit_mw"]):.1f}' in row[0]
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} Table 1 row {b['from_bus']}-{b['to_bus']}")
cost = {}
for g in GEN: cost.setdefault(g["technology"] + "@" + g["bus"], set()).add(round(float(g["varcost_usd_per_mwh"]), 2))
for k, v in cost.items():
    assert len(v) == 1, k
    val = v.pop(); claim(f"cost {k}", val, f"{val:.2f}", "{:.2f}")
for a, b, mw in (("Kalaeloa", "municipal_waste", 86.0), ("Kalaeloa", "combined_cycle", 220.0),
                 ("Kahe", "steam", 582.1), ("Waiau", "steam", 354.2), ("Wahiawa", "internal_combustion", 50.4),
                 ("Waiau", "combustion_turbine", 102.4), ("Kalaeloa", "combustion_turbine", 113.0)):
    got = sum(float(g["p_max_mw"]) for g in GEN if g["bus"] == a and g["technology"] == b)
    claim(f"MW {b} at {a}", got, f"{got:.1f}", "{:.1f}")

# ---- demand statistics
fit = {r["bus"]: (float(r["mu_mw"]), float(r["sigma_mw"])) for r in rows(f"{O}/bus_fit.csv")}
share = json.load(open(f"{D}/demand_build_report.json"))["peak_share"]
for b, (m, s) in fit.items():
    if m == 0: continue
    want = f"& {m:.1f} & {s:.1f} & {s/m:.2f} & {100*share[b]:.1f}\\% \\\\"
    ok = any(l.startswith(b + " ") and want in norm(l) for l in RAW.split("\n"))
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} Table 2 row {b:10s} {want}")
tot = {a: np.array([float(r["total_mw"]) for r in rows(f"{O}/draws_{a}.csv")]) for a in ("actual", "fitted", "corr")}
for a, lab in (("actual", "the recorded year"), ("fitted", "drawn \\emph{separately}"), ("corr", "drawn \\emph{together}")):
    t = tot[a]
    line = [l for l in RAW.split("\n") if lab in l and f"{t.mean():.1f}" in l][0]
    for v in (t.mean(), t.std(ddof=1), t.max()):
        claim(f"island {a}", v, f"{v:.1f}", "{:.1f}") if f"{v:.1f}" in line else (print(f"FAIL island {a} {v:.1f} not in row"), globals().__setitem__("fails", fails + 1))
    p1000 = 100 * (t > 1000).mean()
    ok = f"{p1000:.2f}" in line; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} island {a} share above 1000 MW {p1000:.2f}%")
claim("island sd (Table 2 total)", tot["actual"].std(ddof=1), "\\textbf{124.9}")
claim("island mean (Table 2 total)", tot["actual"].mean(), "\\textbf{743.9}")
claim("random max as % above recorded peak", 100 * (tot["corr"].max() / tot["actual"].max() - 1),
      "\\SI{1216}{MW}, \\SI{15}{\\percent} above the", "{:.0f}")
claim("share of draws above recorded peak", 100 * (tot["corr"] > tot["actual"].max()).mean(),
      "\\SI{0.56}{\\percent} of draws exceed that peak", "{:.2f}")
H = rows(f"{D}/bus_hourly_demand.csv")
for b, txt in (("Downtown", "\\SI{61}{\\percent} of Downtown's hours"), ("Pukele", "\\SI{65}{\\percent} of Pukele's")):
    x = np.array([float(r[f"load_{b}_mw"]) for r in H]); m, s = fit[b]
    claim(f"within 1 sigma {b}", 100 * np.mean(np.abs(x - m) <= s), txt, "{:.0f}")
x = np.array([float(r["load_Downtown_mw"]) for r in H])
claim("Downtown min", x.min(), "from \\SI{192}{MW} to \\SI{370}{MW}", "{:.0f}")
claim("Downtown max", x.max(), "from \\SI{192}{MW} to \\SI{370}{MW}", "{:.0f}")
claim("Downtown hours above one circuit", int((x > 209.9).sum()), "above \\SI{209.9}{MW} in 8,661 of the", "{:d}")
cor = rows(f"{O}/bus_corr.csv")
cv = [float(r[k]) for r in cor for k in r if k not in ("bus", r["bus"], "Kalaeloa") and r["bus"] != "Kalaeloa"]
claim("correlation min", min(cv), "(from \\num{0.47} to \\num{1.00}, average \\num{0.86})", "{:.2f}")
claim("correlation mean", float(np.mean(cv)), "(from \\num{0.47} to \\num{1.00}, average \\num{0.86})", "{:.2f}")
X = np.array([[float(r[c]) for c in H[0] if c.startswith("load_")] for r in H])
w = np.linalg.eigvalsh(np.cov(X.T)); rank = int((w > 1e-6 * w.max()).sum())
claim("rank of covariance", rank, "$\\Sigma$ has rank three", "words")

# ---- contingencies (base)
C = rows(f"{O}/contingency.csv"); L = rows(f"{O}/contingency_lines.csv")
def c(kind, arm): return [r for r in C if r["kind"] == kind and r["arm"] == arm]
claim("N-2 cases", len(c("N-2", "actual")), "Of the 128 ways to lose two circuits", "{:d}")
claim("N-1 cases", len(c("N-1", "actual")), "(16 distinct cases", "{:d}")
claim("N-0 short", sum(int(r["hours_short"]) for r in c("N-0", "actual") + c("N-0", "random")),
      "\\textbf{never} --- 0 of \\num{8760} hours, 0 of", "{:d}")
n1 = sum(int(r["hours_short"]) > 0 for r in c("N-1", "actual") + c("N-1", "random"))
ok = n1 == 0 and "\\textbf{never leaves demand unserved}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} N-1 cases with lost demand = {n1} (text: never leaves demand unserved)")
claim("N-2 cases short, recorded", sum(int(r["hours_short"]) > 0 for r in c("N-2", "actual")),
      "\\textbf{7 leave demand unserved in the recorded", "{:d}")
claim("N-2 cases short, random", sum(int(r["hours_short"]) > 0 for r in c("N-2", "random")),
      "year, and 10 in", "{:d}")
n0 = {arm: {r["line"]: float(r["max_loading"]) for r in L if r["kind"] == "N-0" and r["arm"] == arm} for arm in ("actual", "random")}
claim("N-0 CEIP-Ewa Nui recorded", 100 * n0["actual"]["CEIP-Ewa Nui"], "at \\SI{72.6}{\\percent} in its", "{:.1f}")
claim("N-0 CEIP-Ewa Nui random", 100 * n0["random"]["CEIP-Ewa Nui"], "\\SI{73.0}{\\percent} in the heaviest random", "{:.1f}")
claim("N-0 Kalaeloa-Ewa Nui", 100 * n0["actual"]["Kalaeloa-Ewa Nui"], "Kalaeloa--Ewa Nui (\\SI{68}{\\percent})", "{:.0f}")
claim("N-0 Halawa-Downtown rec", 100 * n0["actual"]["Halawa-Downtown"], "Halawa--Downtown (\\SI{62}{\\percent} recorded", "{:.0f}")
claim("N-0 Halawa-Downtown rand", 100 * n0["random"]["Halawa-Downtown"], "\\SI{67}{\\percent} random)", "{:.0f}")
claim("N-0 Waiau-Makalapa rand", 100 * n0["random"]["Waiau-Makalapa"], "\\SI{61}{\\percent} against \\SI{52}{\\percent}", "{:.0f}")
claim("N-0 Waiau-Makalapa rec", 100 * n0["actual"]["Waiau-Makalapa"], "\\SI{61}{\\percent} against \\SI{52}{\\percent}", "{:.0f}")
def pin(outage, arm, line):
    return next(int(r["hours_at_limit"]) for r in L if r["outage"] == outage and r["arm"] == arm and r["line"] == line)
for o, ln, arm, txt in (("Kalaeloa-Ewa Nui", "CEIP-Ewa Nui", "actual", "\\num{3401} (\\SI{38.8}{\\percent})"),
                        ("Kalaeloa-Ewa Nui", "CEIP-Ewa Nui", "random", "\\num{4235} (\\SI{42.4}{\\percent})"),
                        ("CEIP-Ewa Nui", "Kalaeloa-Ewa Nui", "actual", "\\num{2359} (\\SI{26.9}{\\percent})"),
                        ("CEIP-Ewa Nui", "Kalaeloa-Ewa Nui", "random", "\\num{2523} (\\SI{25.2}{\\percent})"),
                        ("one of 2 Halawa-Downtown", "Halawa-Downtown", "random", "32 (\\SI{0.32}{\\percent})"),
                        ("one of 2 CEIP-Kalaeloa", "CEIP-Kalaeloa", "random", "17 (\\SI{0.17}{\\percent})"),
                        ("one of 2 Waiau-Makalapa", "Waiau-Makalapa", "random", "4 (\\SI{0.04}{\\percent})")):
    claim(f"N-1 {o} -> {ln} {arm}", pin(o, arm, ln), txt, "{:d}")
def short(o, arm):
    r = next(r for r in C if r["outage"] == o and r["arm"] == arm)
    return 100 * int(r["hours_short"]) / int(r["n"]), float(r["mwh_short"]), float(r["worst_mw"])
T = [("two of 2 Koolau-Pukele", "100\\% & 99.99\\% & \\num{854579} & \\SI{163}{MW}"),
     ("two of 2 Halawa-Downtown", "98.9\\% & 97.4\\% & \\num{590276} & \\SI{160}{MW}"),
     ("Halawa-Downtown + Makalapa-Downtown", "98.9\\% & 97.4\\% & \\num{590709} & \\SI{160}{MW}"),
     ("Kahe-Wahiawa + Wahiawa-Waiau", "36.8\\% & 43.1\\% & \\num{41750} & \\SI{29}{MW}"),
     ("two of 2 Waiau-Koolau", "7.9\\% & 4.9\\% & \\num{6893} & \\SI{31}{MW}"),
     ("Waiau-Koolau + Halawa-Koolau", "7.9\\% & 4.9\\% & \\num{6927} & \\SI{31}{MW}"),
     ("Waiau-Makalapa + Halawa-Downtown", "0.01\\% & 0.53\\% & 5 & \\SI{5}{MW}"),
     ("Kahe-Halawa + Waiau-Makalapa", "0 & 0.33\\% & 0 & ---"),
     ("Waiau-Makalapa + Waiau-Koolau", "0 & 0.08\\% & 0 & ---"),
     ("Halawa-Koolau + Halawa-Downtown", "0 & 0.01\\% & 0 & ---")]
for o, txt in T:
    pa, mwh, worst = short(o, "actual"); pr, _, _ = short(o, "random")
    fa = "100" if pa == 100 else ("0" if pa == 0 else (f"{pa:.2f}" if pa < 0.1 else f"{pa:.1f}"))
    fr = f"{pr:.2f}" if (pr < 1 or pr > 99.9) else f"{pr:.1f}"
    want = f"{fa}\\% & {fr}\\%".replace("0\\% &", "0 &") if pa == 0 else f"{fa}\\% & {fr}\\%"
    ok = txt in TEX and txt.startswith(want) and (f"{mwh:.0f}" in txt) and (pa == 0 or f"{worst:.0f}" in txt)
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} Table 3 {o:40s} rec {pa:.2f}% rand {pr:.2f}% MWh {mwh:.0f} worst {worst:.1f}")

# ---- growth
S = rows(f"{O}/stress_system.csv")
def g(arm, lev, col): return next(float(r[col]) for r in S if r["arm"] == arm and float(r["level"]) == lev)
claim("growth: wires at 2.0 recorded", g("actual", 2.0, "pct_short_wires"), "only \\SI{3.0}{\\percent} of recorded", "{:.1f}")
claim("growth: wires at 2.0 random", g("random", 2.0, "pct_short_wires"), "\\SI{1.3}{\\percent} of random", "{:.1f}")
claim("growth: generators at 2.0 recorded", g("actual", 2.0, "pct_short_generation"), "\\SI{42}{\\percent} and \\SI{47}{\\percent}", "{:.0f}")
claim("growth: generators at 2.0 random", g("random", 2.0, "pct_short_generation"), "\\SI{42}{\\percent} and \\SI{47}{\\percent}", "{:.0f}")
first = lambda arm, col: next(float(r["level"]) for r in S if r["arm"] == arm and float(r[col]) > 0)
claim("first gen shortage recorded", first("actual", "pct_short_generation"), "generators too small in some hour (fleet \\SI{1508}{MW})    & $g = 1.5$ & $g = 1.3$")
claim("first gen shortage random", first("random", "pct_short_generation"), "& $g = 1.5$ & $g = 1.3$")
claim("first line at limit recorded", first("actual", "pct_any_line_at_limit"), "a line reaches its rating                                 & $g = 1.6$ & $g = 1.5$")
claim("first line at limit random", first("random", "pct_any_line_at_limit"), "& $g = 1.6$ & $g = 1.5$")
claim("first wire shortage recorded", first("actual", "pct_short_wires"), "demand lost because of the wires                          & $g = 1.7$ & $g = 1.6$")
claim("first wire shortage random", first("random", "pct_short_wires"), "& $g = 1.7$ & $g = 1.6$")
SL = rows(f"{O}/stress_by_line.csv")
m2 = next(float(r["max_loading"]) for r in SL if r["arm"] == "actual" and r["line"] == "CEIP-Ewa Nui" and float(r["level"]) == 2.0)
claim("CEIP-Ewa Nui under growth, recorded", 100 * m2, "peaks at \\SI{95}{\\percent} of it", "{:.0f}")
m3 = max(float(r["max_loading"]) for r in SL if r["arm"] == "random" and r["line"] == "CEIP-Ewa Nui")
claim("CEIP-Ewa Nui under growth, random", 100 * m3, "and \\SI{97}{\\percent} in the random draws", "{:.0f}")
GB = next(r for r in rows(f"{O}/n0_genbus.csv") if r["bus"] == "Kalaeloa" and r["arm"] == "actual")
claim("Kalaeloa bus output, lowest recorded hour", float(GB["min_mw"]), "deliver their\n\\SI{306}{MW} in every recorded hour", "{:.0f}")
claim("Kalaeloa bus output, highest recorded hour", float(GB["max_mw"]), "\\SI{306}{MW} in every recorded hour", "{:.0f}")

# ---- sensitivity
def sens(tag):
    d = O if tag == "base" else os.path.join(HERE, f"out_{tag}")
    CC = rows(f"{d}/contingency.csv"); LL = rows(f"{d}/contingency_lines.csv")
    out = {}
    for arm in ("actual", "random"):
        out[f"n0_{arm}"] = max(float(r["max_loading"]) for r in LL if r["kind"] == "N-0" and r["arm"] == arm)
        for k in ("N-1", "N-2"):
            out[f"{k}_{arm}"] = sum(int(r["hours_short"]) > 0 for r in CC if r["kind"] == k and r["arm"] == arm)
    for key, o in (("pk", "two of 2 Koolau-Pukele"), ("dt", "two of 2 Halawa-Downtown"),
                   ("wh", "Kahe-Wahiawa + Wahiawa-Waiau"), ("wk", "two of 2 Waiau-Koolau")):
        r = next(r for r in CC if r["outage"] == o and r["arm"] == "actual")
        out[key] = 100 * int(r["hours_short"]) / int(r["n"])
    return out
SS = {t: sens(t) for t in ("low", "base", "high", "puc")}
row = lambda k, f: " & ".join(f(SS[t]) for t in ("low", "base", "high", "puc"))
pct = lambda v: ("100\\%" if abs(v - 100) < 1e-9 else ("0\\%" if v == 0 else f"{v:.1f}\\%"))
checks = [
 ("N-0: highest loading & " + row("n0", lambda s: f"{100*s['n0_actual']:.0f}\\% ({100*s['n0_random']:.0f}\\%)")),
 ("N-1: cases that lose demand (of 16) & " + row("", lambda s: f"{s['N-1_actual']} ({s['N-1_random']})")),
 ("N-2: cases that lose demand (of 128) & " + row("", lambda s: f"{s['N-2_actual']} ({s['N-2_random']})")),
 ("both Koolau--Pukele $\\to$ East Honolulu & " + row("", lambda s: pct(s["pk"]))),
 ("both Halawa--Downtown $\\to$ Downtown & " + row("", lambda s: pct(s["dt"]))),
 ("Kahe--Wahiawa + Wahiawa--Waiau $\\to$ Wahiaw\\=a & " + row("", lambda s: pct(s["wh"]))),
 ("both Waiau--Koolau $\\to$ Windward + E. Honolulu & " + row("", lambda s: pct(s["wk"]))),
]
for want in checks:
    ok = want in TEX; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} Table 5: {want}")
# downtown under low rating after one circuit lost
lowC = rows(os.path.join(HERE, "out_low", "contingency.csv"))
r = next(r for r in lowC if r["outage"] == "one of 2 Halawa-Downtown" and r["arm"] == "actual")
claim("low rating: one downtown circuit lost", 100 * int(r["hours_short"]) / int(r["n"]),
      "short in \\SI{30}{\\percent} of hours", "{:.0f}")

# ---- demand shares vs PUC
rep = json.load(open(f"{D}/demand_build_report.json"))["peak_share"]
claim("Pukele day-peak share", 100 * rep["Pukele"], "(our table: \\SI{14.1}{\\percent}", "{:.1f}")
claim("Koolau+Pukele share", 100 * (rep["Pukele"] + rep["Koolau"]), "ours: \\SI{20.3}{\\percent})", "{:.1f}")
claim("Downtown share", 100 * rep["Downtown"], "(ours: \\SI{38.4}{\\percent}", "{:.1f}")

# ---- total solves
n_cases = 1 + 16 + 128
total = (28760 + 7 * n_cases * (8760 + 10000)           # run_all; contingency x 7 runs
         + 2 * 11 * 2 * (8760 + 10000) + 2 * 2 * 8760)   # stress x 2 runs; redispatch
claim("total LPs solved", total, "\\num{19930640}", "{:d}")

# ---- re-dispatch after losing an export line (redispatch.jl)
RD = {r["line_lost"]: r for r in rows(f"{O}/redispatch.csv")}
k = RD["Kalaeloa-Ewa Nui"]
claim("Kahe gives up (MW)", float(k["Kahe_mw_n0"]) - float(k["Kahe_mw_n1"]), "Kahe gives up \\SI{61}{MW}", "{:.0f}")
claim("Waiau adds (MW)", float(k["Waiau_mw_n1"]) - float(k["Waiau_mw_n0"]), "\\SI{61}{MW} on average in the pinned hours and Waiau adds the same", "{:.0f}")
claim("Kalaeloa unchanged", float(k["Kalaeloa_mw_n1"]), "(they stay at \\SI{306}{MW})", "{:.0f}")
claim("extra cost per pinned hour", float(k["extra_cost_usd_per_full_hour"]), "cost of \\$491 per pinned hour", "{:.0f}")
hi = max(float(r["island_mw_max_when_not_full"]) for r in RD.values())
lo = min(float(r["island_mw_min_when_full"]) for r in RD.values())
claim("full in every hour above (MW)", hi, "more than \\SI{833}{MW}", "{:.0f}")
claim("full in no hour below (MW)", lo, "in none below \\SI{756}{MW}", "{:.0f}")

# ---- demand as D = K N (the equation in section 2.1)
rep = json.load(open(f"{D}/demand_build_report.json"))
bl = [b for b in fit if fit[b][0] > 0]
Dm = np.array([[float(r[f"load_{b}_mw"]) for b in bl] for r in H]).T
Kk = np.column_stack([np.array([rep[k][b] for b in bl], float) / sum(rep[k][b] for b in bl)
                      for k in ("people", "com_jobs", "ind_jobs")])
Nn, *_ = np.linalg.lstsq(Kk, Dm, rcond=None)
ok = np.abs(Dm - Kk @ Nn).max() < 1e-3; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} demand is exactly K N (max residual {np.abs(Dm - Kk @ Nn).max():.1e} MW)")
for i, b in enumerate(bl):
    want = f"{b} & {100*Kk[i,0]:.1f} & {100*Kk[i,1]:.1f} & {100*Kk[i,2]:.1f}"
    ok = norm(want) in TEX or any(norm(want).replace(" & ", " & ", 3) in norm(l) for l in RAW.split("\n"))
    ok = ok or any((f"{b} " in l or f"& {b} " in l) and f"{100*Kk[i,0]:.1f} & {100*Kk[i,1]:.1f} & {100*Kk[i,2]:.1f}" in norm(l) for l in RAW.split("\n"))
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} recipe {b}: {100*Kk[i,0]:.1f} / {100*Kk[i,1]:.1f} / {100*Kk[i,2]:.1f}")
for j, v in enumerate(("147", "215", "382")):
    claim(f"bucket {j} mean MW", Nn[j].mean(), f"\\SI{{{v}}}{{MW}}", "{:.0f}")
w = np.sort(np.linalg.eigvalsh(np.cov(Dm)))[::-1]
claim("eigenvalue 1", w[0], "\\num{2295}, \\num{452} and \\SI{17}{MW^2}", "{:.0f}")
claim("eigenvalue 2", w[1], "\\num{2295}, \\num{452} and \\SI{17}{MW^2}", "{:.0f}")
claim("eigenvalue 3", w[2], "\\num{2295}, \\num{452} and \\SI{17}{MW^2}", "{:.0f}")
ix = {b: i for i, b in enumerate(bl)}
A = np.column_stack([Dm[ix[x]] for x in ("Downtown", "Wahiawa", "CEIP")])
cc, *_ = np.linalg.lstsq(A, Dm[ix["Pukele"]], rcond=None)
for v in cc:
    claim("Pukele as a mix of three", abs(v), f"{abs(v):.3f}", "{:.3f}")
rt = Dm[ix["Koolau"]] / Dm[ix["Wahiawa"]]
claim("Koolau/Wahiawa min ratio", rt.min(), "between\n0.95 and 1.00 times", "{:.2f}")
claim("industry share of 2021 sales", 42.13, "Industry is \\SI{42}{\\percent}", "{:.0f}")
claim("industry share of net load", 100 * Nn[2].mean() / Nn.mean(0).sum() if False else 100 * Nn[2].mean() / Nn.mean(1).sum(),
      "(\\SI{51}{\\percent} of net load", "{:.0f}")

# ---- local variation (noise_stats.jl, contingency.jl and stress.jl with NOISE)
NS = {(float(r["noise"]), r["arm"]): r for r in rows(f"{O}/noise_stats.csv")}
thin = " & ".join("\\SI{" + (f"{np.sqrt(max(float(NS[(f, 'actual')]['smallest_eig_mw2']), 0)):.2f}" if f else "0") + "}{MW}"
                  for f in (0.0, 0.1, 0.25, 0.5))
ok = f"thinnest direction of the demand cloud & {thin}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} Table noise: thinnest direction {thin}")
mc = " & ".join(f"{float(NS[(f, 'actual')]['mean_corr']):.2f}" for f in (0.0, 0.1, 0.25, 0.5))
ok = f"average correlation between substations & {mc}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} Table noise: mean correlation {mc}")
wk = " & ".join(f"{float(NS[(f, 'actual')]['corr_wahiawa_koolau']):.3f}" for f in (0.0, 0.1, 0.25, 0.5))
ok = f"Wahiaw\\=a--Koolau correlation & {wk}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} Table noise: Wahiawa-Koolau {wk}")
sd = " & ".join(f"\\SI{{{float(NS[(f, 'actual')]['island_sd_mw']):.1f}}}{{MW}}" for f in (0.0, 0.1, 0.25, 0.5))
ok = f"spread of the island total, $\\sigma$ & {sd}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} Table noise: island sd {sd}")
NT = {"base": sens("base")}
for t in ("noise10", "noise25", "noise50"): NT[t] = sens(t)
order = ("base", "noise10", "noise25", "noise50")
for label, fn in (("N-1: cases that lose demand (of 16) & ", lambda s: f"{s['N-1_actual']} ({s['N-1_random']})"),
                  ("N-2: cases that lose demand (of 128) & ", lambda s: f"{s['N-2_actual']} ({s['N-2_random']})"),
                  ("both Koolau--Pukele $\\to$ East Honolulu & ", lambda s: pct(s["pk"])),
                  ("both Halawa--Downtown $\\to$ Downtown & ", lambda s: pct(s["dt"])),
                  ("Kahe--Wahiawa + Wahiawa--Waiau $\\to$ Wahiaw\\=a & ", lambda s: pct(s["wh"])),
                  ("both Waiau--Koolau $\\to$ Windward + E. Honolulu & ", lambda s: pct(s["wk"]))):
    want = label + " & ".join(fn(NT[t]) for t in order)
    ok = want in TEX; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} Table noise: {want}")
def ph(t):
    d = O if t == "base" else os.path.join(HERE, f"out_{t}")
    CC = rows(f"{d}/contingency.csv")
    a = next(r for r in CC if r["outage"] == "Kahe-Halawa + Waiau-Makalapa" and r["arm"] == "actual")["hours_short"]
    b = next(r for r in CC if r["outage"] == "Kahe-Halawa + Waiau-Makalapa" and r["arm"] == "random")["hours_short"]
    return f"{a} h ({b})"
want = "1 Kahe--Halawa + 1 Waiau--Makalapa $\\to$ Pearl Harbor & " + " & ".join(ph(t) for t in order)
ok = want in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} Table noise: {want}")
SN = rows(os.path.join(HERE, "out_noise50", "stress_system.csv"))
fn50 = lambda arm, col: next(float(r["level"]) for r in SN if r["arm"] == arm and float(r[col]) > 0)
want = (f"growth: generators first short at & $g=1.5$ (1.3) & & & $g={fn50('actual','pct_short_generation'):.1f}$ "
        f"({fn50('random','pct_short_generation'):.1f})")
ok = want in TEX; fails += not ok; print(f"{'ok  ' if ok else 'FAIL'} {want}")
want = (f"growth: wires first cost demand at & $g=1.7$ (1.6) & & & $g={fn50('actual','pct_short_wires'):.1f}$ "
        f"({fn50('random','pct_short_wires'):.1f})")
ok = want in TEX; fails += not ok; print(f"{'ok  ' if ok else 'FAIL'} {want}")
claim("island spread rise at f=0.5", float(NS[(0.5, 'actual')]['island_sd_mw']) - float(NS[(0.0, 'actual')]['island_sd_mw']),
      "rises by at most \\SI{2.7}{MW}", "{:.1f}")
mv = max(abs(NT["noise50"][k] - NT["base"][k]) for k in ("pk", "dt", "wh", "wk"))
ok = mv <= 3.2 and "\\SI{3.2}{percentage points}" in TEX; fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} largest move of the four areas {mv:.2f} pp (text: at most 3.2)")
C50 = [r for r in rows(os.path.join(HERE, "out_noise50", "contingency.csv")) if r["kind"] == "N-2" and r["arm"] == "random" and int(r["hours_short"]) > 0]
claim("rare cases at f=0.5 (1-2 draws)", sum(int(r["hours_short"]) <= 2 for r in C50), "at $f = 0.5$ (against 10 without the wiggle), 21 do so", "{:d}")

print(f"\n{fails} claim(s) failed")
sys.exit(1 if fails else 0)
