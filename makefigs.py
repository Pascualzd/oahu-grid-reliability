#!/usr/bin/env python3
"""
makefigs.py -- the figures of the paper. Nothing is typed in by hand: every
number is read from ./data, ./sources or ./out (written by run_all.jl,
contingency.jl and stress.jl).

  fig1_map.pdf        O'ahu's 138 kV network, drawn on the real coastline
  fig2_gaussian.pdf   the bell curve behind the random draws
  fig3_normal.pdf     how full each line gets when every line is in service
  fig4_outages.pdf    which areas lose power when two lines are lost
  fig5_growth.pdf     how far demand can grow before something gives out

Run summarize.py first: fig3 reads its out/n0_lines.csv.

One message per figure, two colours, axes labelled in words.
"""
import csv, json, math, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data"); SRC = os.path.join(HERE, "sources")
O    = os.path.join(HERE, "out")
FIG  = os.path.join(HERE, "figs"); os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif", "font.size": 9.5, "axes.titlesize": 10,
    "axes.labelsize": 9.5, "legend.fontsize": 8.5, "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 130, "savefig.bbox": "tight", "pdf.fonttype": 42,
})
NAVY = "#1b3a6b"; RED = "#c1121f"; GREY = "#8a96a3"; GOLD = "#e9a020"
SEA = "#e4eef5"; LAND = "#f4f0e6"; COAST = "#b9ad93"

def rows(p): return list(csv.DictReader(open(p)))
def save(fig, name):
    fig.savefig(os.path.join(FIG, name), format="pdf"); plt.close(fig); print("  ", name)

BUSES = rows(f"{DATA}/network_buses.csv")
BR    = rows(f"{DATA}/network_branches.csv")
GENS  = rows(f"{DATA}/generators.csv")
XY    = {b["bus"]: (float(b["longitude"]), float(b["latitude"])) for b in BUSES}
GENMW = {}
for g in GENS: GENMW[g["bus"]] = GENMW.get(g["bus"], 0.0) + float(g["p_max_mw"])
LNAME = [f'{b["from_bus"]}-{b["to_bus"]}' for b in BR]
PRETTY = lambda s: s.replace("-", "–")
print("building figures ->", FIG)

# longitude is shrunk by cos(latitude) so the island has its true shape
ASPECT = 1 / math.cos(math.radians(21.45))

def island(ax, ccd_lines=True):
    g = json.load(open(f"{SRC}/census_cb2020_ccd_oahu_shoreline.geojson"))
    for f in g["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = np.array(poly[0])
            if ring[:, 0].min() < -158.4:          # the far Northwestern islands
                continue
            ax.add_patch(Polygon(ring, closed=True, facecolor=LAND,
                                 edgecolor=(COAST if not ccd_lines else "#d8cfbb"),
                                 lw=(1.0 if not ccd_lines else 0.5), zorder=0))
    ax.set_facecolor(SEA)
    ax.set_xlim(-158.30, -157.63); ax.set_ylim(21.24, 21.72)
    ax.set_aspect(ASPECT); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)

def routes():
    """HIFLD geometry: {branch index: [route, ...]}, a route = [lon/lat arrays]."""
    g = json.load(open(f"{SRC}/hifld_oahu_transmission_lines.geojson"))
    geo = {str(f["properties"]["ID"]): np.array(f["geometry"]["coordinates"]) for f in g["features"]}
    return {i: [[geo[lid.strip()] for lid in route.strip().split("+")]
                for route in b["hifld_ids"].split(";")] for i, b in enumerate(BR)}

# =====================================================================
# fig1  the network on the real coastline
# =====================================================================
def fig1():
    fig, ax = plt.subplots(figsize=(7.4, 5.4))
    island(ax)
    R = routes()
    # where the "x n circuits" tag sits: fraction along the route, then an offset
    FRAC = {"Waiau-Koolau": 0.2}
    NOFF = {"Kahe-CEIP": (-0.019, -0.006), "CEIP-Kalaeloa": (0.013, 0.0),
            "Kahe-Halawa": (0.0, 0.015), "Ewa Nui-Waiau": (0.0, -0.012),
            "Waiau-Makalapa": (0.011, 0.007), "Waiau-Koolau": (0.0, 0.013),
            "Halawa-Downtown": (0.013, 0.0), "Koolau-Pukele": (0.014, 0.0)}
    for i, b in enumerate(BR):
        n = int(b["circuits"]); routes_ = b["hifld_ids"].split(";")
        per = n / len(routes_)                     # circuits carried by each drawn route
        for route in R[i]:
            for seg in route:
                ax.plot(seg[:, 0], seg[:, 1], color=NAVY, lw=0.4 + 1.5 * per,
                        solid_capstyle="round", zorder=2, alpha=0.9)
        if n > 1:                                  # say it in numbers too
            allp = np.vstack(R[i][0])
            mid = allp[int(FRAC.get(LNAME[i], 0.5) * (len(allp) - 1))]
            off = NOFF.get(LNAME[i], (0, 0))
            ax.text(mid[0] + off[0], mid[1] + off[1], f"\u00d7{n}", fontsize=7.2,
                    color=NAVY, ha="center", va="center", zorder=3,
                    bbox=dict(boxstyle="round,pad=0.08", fc=LAND, ec="none", alpha=0.9))
    # label placement: (dx, dy) in degrees, alignment
    LAB = {"Kahe": (-0.016, 0.016, "right"), "Kalaeloa": (-0.014, -0.016, "right"),
           "CEIP": (0.012, 0.004, "left"), "Ewa Nui": (-0.004, -0.019, "right"),
           "Waiau": (0.004, -0.035, "center"), "Wahiawa": (0.016, 0.014, "left"),
           "Halawa": (-0.004, 0.024, "center"), "Makalapa": (0.012, -0.018, "left"),
           "Downtown": (0.000, -0.024, "center"), "Koolau": (0.014, 0.012, "left"),
           "Pukele": (0.014, -0.012, "left")}
    for b in BUSES:
        nm = b["bus"]; x, y = XY[nm]; g = GENMW.get(nm, 0.0)
        if g > 0:
            ax.scatter([x], [y], s=35 + 0.16 * g, marker="s", color=GOLD,
                       edgecolor="black", lw=0.8, zorder=4)
        else:
            ax.scatter([x], [y], s=55, marker="o", color="white",
                       edgecolor="black", lw=1.1, zorder=4)
        dx, dy, ha = LAB[nm]
        txt = nm if g == 0 else f"{nm}\n{g:.0f} MW"
        ax.text(x + dx, y + dy, txt, ha=ha, va="center", fontsize=8.3, zorder=5,
                fontweight="bold", linespacing=0.95,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8))
    # places, for orientation
    for nm, (x, y) in {"Waiʻanae": (-158.19, 21.45), "North Shore": (-158.06, 21.62),
                       "Kailua / Kāneʻohe": (-157.74, 21.45),
                       "Waikīkī / Hāwaiʻi Kai": (-157.74, 21.265),
                       }.items():
        ax.text(x, y, nm, fontsize=7.6, style="italic", color="#6b5f45",
                ha="center", zorder=1)
    h = [Line2D([], [], color=NAVY, lw=0.4 + 1.5 * n, label=f"{n} circuit{'s' if n > 1 else ''} on the route")
         for n in (1, 2)]
    h += [Line2D([], [], marker="o", ls="", mfc="white", mec="black", ms=7, label="substation"),
          Line2D([], [], marker="s", ls="", mfc=GOLD, mec="black", ms=9,
                 label="substation with power plants\n(summer MW)")]
    ax.legend(handles=h, loc="upper right", frameon=True, framealpha=0.95, fontsize=7.8)
    ax.text(-158.295, 21.245, "Lines: HIFLD 138 kV routes.  Coast: U.S. Census 2020.",
            fontsize=6.8, color="#555")
    save(fig, "fig1_map.pdf")

fig1()

# =====================================================================
# fig2  the bell curve behind the random draws
# =====================================================================
def normal_pdf(x, m, s): return np.exp(-0.5 * ((x - m) / s) ** 2) / (s * math.sqrt(2 * math.pi))

def fig2():
    H = rows(f"{DATA}/bus_hourly_demand.csv")
    fit = {r["bus"]: (float(r["mu_mw"]), float(r["sigma_mw"])) for r in rows(f"{O}/bus_fit.csv")}
    tot = {a: np.array([float(r["total_mw"]) for r in rows(f"{O}/draws_{a}.csv")])
           for a in ("actual", "fitted", "corr")}
    fig, axs = plt.subplots(1, 3, figsize=(7.4, 2.7))
    for k, (ax, b) in enumerate(zip(axs[:2], ("Downtown", "Pukele"))):
        x = np.array([float(r[f"load_{b}_mw"]) for r in H]); m, s = fit[b]
        hh, _, _ = ax.hist(x, bins=40, density=True, color=GREY, alpha=0.55,
                           label="recorded hours")
        xs = np.linspace(x.min() - 0.3 * s, x.max() + 0.3 * s, 300)
        ax.plot(xs, normal_pdf(xs, m, s), color=NAVY, lw=1.8, label="Gaussian")
        ax.set_title(f"{b}\n$\\mu$ = {m:.0f} MW,  $\\sigma$ = {s:.0f} MW", fontsize=9)
        ax.set_xlabel("demand (MW)"); ax.set_yticks([])
        ax.set_ylim(0, 1.32 * max(hh.max(), normal_pdf(m, m, s)))
        if k == 0:
            ax.legend(frameon=False, fontsize=7.4, loc="upper left")
    ax = axs[2]
    bins = np.linspace(380, 1260, 34)
    hh, _, _ = ax.hist(tot["actual"], bins=bins, density=True, color=GREY, alpha=0.55,
                       label="recorded hours")
    top = hh.max()
    for a, col, ls, lab in (("corr", NAVY, "-", "random, correlated"),
                            ("fitted", RED, "--", "random, independent")):
        h, e = np.histogram(tot[a], bins=bins, density=True); top = max(top, h.max())
        ax.step(e[:-1], h, where="post", color=col, ls=ls, lw=1.5,
                label=f"{lab} ($\\sigma$ {tot[a].std(ddof=1):.0f})")
    ax.set_title(f"island total\nrecorded $\\sigma$ = {tot['actual'].std(ddof=1):.0f} MW", fontsize=9)
    ax.set_xlabel("total demand (MW)"); ax.set_yticks([]); ax.set_ylim(0, 1.45 * top)
    ax.legend(frameon=False, fontsize=6.8, loc="upper left")
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig2_gaussian.pdf")

fig2()

# =====================================================================
# fig3  every line in service: how full does each one get?
# =====================================================================
def fig3():
    N0 = rows(f"{O}/n0_lines.csv")                   # written by summarize.py
    get = lambda arm, col: np.array([float(r[col]) for r in N0 if r["arm"] == arm])
    names = [f'{r["from"]}-{r["to"]}' for r in N0 if r["arm"] == "actual"]
    amax, amean, cmax = get("actual", "max_loading"), get("actual", "mean_loading"), get("corr", "max_loading")
    order = np.argsort(amax)
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.barh(y + 0.19, 100 * amax[order], height=0.36, color=NAVY,
            label="highest hour of the recorded year")
    ax.barh(y - 0.19, 100 * cmax[order], height=0.36, color=GOLD,
            label="highest of the 10,000 random draws")
    ax.scatter(100 * amean[order], y + 0.19, marker="|", s=90, color="white",
               zorder=3)
    ax.axvline(100, color=RED, lw=1.2, ls="--")
    ax.text(99, len(names) - 0.4, "rating", color=RED, ha="right", fontsize=8.5)
    ax.set_yticks(y); ax.set_yticklabels([PRETTY(names[i]) for i in order], fontsize=8)
    ax.set_xlim(0, 105); ax.set_xlabel("loading = flow / rating (%)")
    h, l = ax.get_legend_handles_labels()
    h.append(Line2D([], [], marker="|", ls="", color=GREY, ms=9, mew=2))
    l.append("average recorded hour (white tick)")
    ax.legend(h, l, frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.13),
              ncol=3, fontsize=7.6, handlelength=1.5, columnspacing=1.2)
    save(fig, "fig3_normal.pdf")

fig3()

# =====================================================================
# fig4  two lines lost: which areas lose power, and how often
# =====================================================================
AREA = {"Pukele": "East Honolulu", "Downtown": "Downtown",
        "Koolau": "Windward + East Honolulu",
        "Wahiawa": "Wahiaw\u0101 / North Shore", "Makalapa": "Pearl Harbor"}

def fig4():
    import summarize_labels as SLB
    C = rows(f"{O}/contingency.csv")
    cases = {}
    for r in C:
        if r["kind"] != "N-2": continue
        cases.setdefault(r["outage"], {})[r["arm"]] = r
    keep = [(k, v) for k, v in cases.items()
            if int(v["actual"]["hours_short"]) > 0 or int(v["random"]["hours_short"]) > 0]
    def area(v):
        a = (v["actual"]["areas_short"] or v["random"]["areas_short"]).split(";")[0].split()[0]
        return AREA["Koolau"] if a in ("Koolau",) or ("Koolau" in v["random"]["areas_short"]
                                                       and "Pukele" in v["random"]["areas_short"]) else AREA[a]
    pa = lambda v: 100 * int(v["actual"]["hours_short"]) / int(v["actual"]["n"])
    pr = lambda v: 100 * int(v["random"]["hours_short"]) / int(v["random"]["n"])
    keep.sort(key=lambda kv: (pr(kv[1]) + pa(kv[1])))
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    y = np.arange(len(keep)); FLOOR = 0.006
    va = [max(pa(v), FLOOR) for _, v in keep]; vr = [max(pr(v), FLOOR) for _, v in keep]
    ax.barh(y + 0.19, va, height=0.36, color=NAVY, label="recorded year (share of 8,760 hours)")
    ax.barh(y - 0.19, vr, height=0.36, color=GOLD, label="random draws (share of 10,000)")
    for i, (_, v) in enumerate(keep):
        if pa(v) == 0:
            ax.text(FLOOR * 1.15, i + 0.19, "never", va="center", fontsize=6.8, color=NAVY)
    ax.set_xscale("log"); ax.set_xlim(FLOOR, 160)
    ax.set_xticks([0.01, 0.1, 1, 10, 100]); ax.set_xticklabels(["0.01%", "0.1%", "1%", "10%", "100%"])
    ax.set_yticks(y)
    ax.set_yticklabels([f"{SLB.short(k)}  \u2192  {area(v)}" for k, v in keep], fontsize=8)
    ax.set_xlabel("how often some demand cannot be served (log scale)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.35, -0.13), ncol=2, fontsize=7.8)
    save(fig, "fig4_outages.pdf")

fig4()

# =====================================================================
# fig5  demand grows: what gives out first, the wires or the generators?
# =====================================================================
def fig5():
    p = f"{O}/stress_system.csv"
    if not os.path.exists(p):
        print("   (fig5 skipped: run stress.jl first)"); return
    S = rows(p)
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 2.9), sharey=True)
    for ax, arm, title in zip(axs, ("actual", "random"),
                              ("recorded year × growth", "random draws × growth")):
        r = [x for x in S if x["arm"] == arm]
        g = [float(x["level"]) for x in r]
        ax.plot(g, [float(x["pct_any_line_at_limit"]) for x in r], color=NAVY, ls="--",
                marker="o", ms=3, lw=1.4, label="a line reaches its rating")
        ax.plot(g, [float(x["pct_short_generation"]) for x in r], color=GOLD,
                marker="s", ms=3, lw=1.8, label="demand lost: not enough generators")
        ax.plot(g, [float(x["pct_short_wires"]) for x in r], color=RED,
                marker="^", ms=3.5, lw=1.8, label="demand lost: the wires")
        ax.set_title(title); ax.set_xlabel("growth factor $g$ on every demand")
        ax.set_xticks([1.0, 1.2, 1.4, 1.6, 1.8, 2.0])
        ax.grid(axis="y", color="#e5e5e5", lw=0.6)
    axs[0].set_ylabel("share of hours / draws (%)")
    axs[0].legend(frameon=False, fontsize=7.4, loc="upper left")
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig5_growth.pdf")

fig5()
