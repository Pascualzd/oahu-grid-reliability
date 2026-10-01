#!/usr/bin/env python3
"""
build_demand.py -- hourly demand at each 138 kV substation, 2021.

THE ISLAND TOTAL is Hawaiian Electric's filed 2021 hourly profile (IGP Inputs
Workbook 3, sources/oahu_load_components_2021.csv). It is preserved exactly.
Everything below only decides how that total is SPLIT between substations.

STEP 1 -- WHICH SUBSTATION SERVES WHICH NEIGHBOURHOOD
  Hawaiian Electric does not publish substation service territories. Each 2020
  census tract (population) and each census block (jobs) is assigned to its
  NEAREST load-serving 138 kV substation -- each substation serves its Voronoi
  cell, the rule the open European model PyPSA-Eur uses to split demand between
  substations (Hoersch, Hofmann, Schlachtberger, Brown, Energy Strategy Reviews
  22, 2018, Sec. 2.1 and 2.6). One geographic constraint is added: the Ko'olau range
  splits the island, so a windward tract can only go to a windward substation,
  and so on, by 2020 census county subdivision (CCD):

      Honolulu CCD    -> Pukele if the tract is one of the neighbourhoods PUC
                         D&O 23747 lists as Pukele's (Kahala, Kaimuki, Manoa,
                         Makiki, Waikiki): census tracts 1-35, which run east to
                         west from Hawaii Kai to Makiki, plus any tract east of
                         157.830 W; otherwise the nearest of Downtown, Makalapa,
                         Halawa. Tract 36 begins at Ala Moana, which the same
                         order lists under downtown's Kamoku substation.
      Ewa CCD         -> Ewa Nui, CEIP, Waiau, Halawa, Makalapa, Kahe, Wahiawa
      Waianae CCD     -> Kahe
      Wahiawa CCD     -> Wahiawa
      Waialua CCD     -> Wahiawa
      Koolauloa CCD   -> Koolau, Wahiawa
      Koolaupoko CCD  -> Koolau

  Kalaeloa is a switching station and is given no load.
  CHECK: the result is compared with the only filed substation shares on record,
  Hawai'i PUC Decision & Order 23747 (2007): at the 2002 day peak Pukele served
  about 17% of O'ahu's load, Koolau and Pukele together about 30%, and the
  downtown substations about 25%.

STEP 2 -- WHAT KIND OF LOAD, HOUR BY HOUR (unchanged method)
  Gross load is split into residential / commercial / industrial by EIA-861 2021
  sales shares for "Hawaiian Electric Co Inc" (O'ahu only), with OpenEI TMY3
  reference-building hourly shapes (Honolulu) for residential and commercial and a
  flat industrial profile. Residential follows 2020 population; commercial and
  industrial follow LEHD LODES 2021 jobs.

STEP 3 -- WHAT IS SUBTRACTED BEHIND THE METER, AND WHERE
  Net load = gross + rooftop PV + customer batteries + energy efficiency + TOU
  shift (reductions negative), each an hourly layer in Workbook 3. Each layer is
  charged to substations by its own sector split (charging it all by population
  would over-debit residential areas at midday):

    rooftop PV           residential / commercial / industrial shares of installed
                         distributed PV capacity for Hawaiian Electric Co Inc,
                         EIA-861 2021 (Net_Metering + Non_Net_Metering_Distributed)
    energy efficiency    residential / commercial shares of 2021 savings,
                         Hawaii Energy Efficiency Program, EIA-861 2021
                         (Energy_Efficiency)
    batteries            Workbook 3 already splits them: residential, commercial,
                         industrial; "other" follows population
    TOU shift            follows population
  Within a sector, residential follows population and commercial/industrial
  follow jobs, as in step 2.

    python3 build_demand.py      # writes data/bus_hourly_demand.csv
"""
import csv, datetime, gzip, json, math, pathlib, zipfile, warnings
from collections import defaultdict

import demand_shapes as ds

HERE = pathlib.Path(__file__).resolve().parent
SRC  = HERE / "sources"
OUT  = HERE / "data"
ds.CACHE = SRC / "cache"                       # OpenEI, LODES, EIA-861 live here
ds.CACHE.mkdir(parents=True, exist_ok=True)    # downloaded on first run if missing

ELIGIBLE = {
    "Honolulu":   ["Downtown", "Pukele", "Makalapa", "Halawa"],
    "Ewa":        ["Ewa Nui", "CEIP", "Waiau", "Halawa", "Makalapa", "Kahe", "Wahiawa"],
    "Waianae":    ["Kahe"],
    "Wahiawa":    ["Wahiawa"],
    "Waialua":    ["Wahiawa"],
    "Koolauloa":  ["Koolau", "Wahiawa"],
    "Koolaupoko": ["Koolau"],
}
OAHU = (21.20, 21.75, -158.35, -157.60)        # lat lo/hi, lon lo/hi


def miles(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def in_ring(lon, lat, ring):
    ins = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def ccd_of(lon, lat, ccds):
    for name, polys in ccds:
        for poly in polys:
            if in_ring(lon, lat, poly[0]) and not any(in_ring(lon, lat, h) for h in poly[1:]):
                return name
    return None


def eia861(fn, want):
    """Read one EIA-861 2021 sheet row for a named utility; return {column label: value}."""
    import pandas as pd
    warnings.filterwarnings("ignore")
    z = zipfile.ZipFile(ds.CACHE / "f8612021.zip")
    df = pd.read_excel(z.open(fn), sheet_name=0, header=None)
    return df, df[df.apply(lambda r: r.astype(str).str.strip().eq(want).any(), axis=1)]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    print("building substation-level hourly demand\n")
    # three files are read directly below; fetch them into sources/cache on a first run
    ds.get("https://www.eia.gov/electricity/data/eia861/archive/zip/f8612021.zip", "f8612021.zip")
    ds.get("https://lehd.ces.census.gov/data/lodes/LODES8/hi/hi_xwalk.csv.gz", "hi_xwalk.csv.gz")
    ds.get("https://lehd.ces.census.gov/data/lodes/LODES8/hi/wac/hi_wac_S000_JT00_2021.csv.gz",
           "hi_wac_S000_JT00_2021.csv.gz")

    # ------------------------------------------------ geography
    buses = list(csv.DictReader(open(OUT / "network_buses.csv")))
    xy = {b["bus"]: (float(b["latitude"]), float(b["longitude"])) for b in buses}
    load_buses = [b["bus"] for b in buses if b["bus"] != "Kalaeloa"]

    gj = json.load(open(SRC / "tigerweb_2020_ccd_honolulu.geojson"))
    ccds = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        ccds.append((f["properties"]["NAME"].replace(" CCD", ""), polys))

    def nearest(lat, lon, ccd, tract=None):
        if ccd == "Honolulu":
            base = int(tract[5:9]) if tract else 999            # tract code 004100 -> 41
            if base <= 35 or lon > -157.830:
                return "Pukele"
            return min(["Downtown", "Makalapa", "Halawa"], key=lambda b: miles((lat, lon), xy[b]))
        return min(ELIGIBLE[ccd], key=lambda b: miles((lat, lon), xy[b]))

    pop = defaultdict(float); tract_bus = {}
    tr = json.load(open(SRC / "tigerweb_2020_tracts_honolulu.json"))["features"]
    skipped = 0
    for f in tr:
        a = f["attributes"]; lat, lon = float(a["INTPTLAT"]), float(a["INTPTLON"])
        if not (OAHU[0] < lat < OAHU[1] and OAHU[2] < lon < OAHU[3]):
            skipped += int(a["POP100"]); continue
        c = ccd_of(lon, lat, ccds)
        if c is None:                                    # offshore internal point
            c = min(ccds, key=lambda cc: min(miles((lat, lon), (p[1], p[0]))
                                             for poly in cc[1] for p in poly[0]))[0]
        b = nearest(lat, lon, c, a["GEOID"]); tract_bus[a["GEOID"]] = b
        pop[b] += int(a["POP100"])
    print(f"  tracts: {len(tract_bus)} on O'ahu, {sum(pop.values()):,.0f} people "
          f"({skipped:,} outside O'ahu skipped)")

    blk = {}
    with gzip.open(ds.CACHE / "hi_xwalk.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            if r["cty"] == "15003":
                blk[r["tabblk2020"]] = (float(r["blklatdd"]), float(r["blklondd"]),
                                        r["ctycsubname"].split(" CCD")[0])
    jobs = defaultdict(lambda: defaultdict(int)); island = defaultdict(int)
    with gzip.open(ds.CACHE / "hi_wac_S000_JT00_2021.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            g = blk.get(r["w_geocode"])
            if not g or not (OAHU[0] < g[0] < OAHU[1] and OAHU[2] < g[1] < OAHU[3]):
                continue
            b = nearest(g[0], g[1], g[2], r["w_geocode"][:11])
            for c in ds.COM_CNS + ds.IND_CNS:
                v = int(r[c]); jobs[b][c] += v; island[c] += v

    tp = sum(pop.values())
    ci = sum(island[c] for c in ds.COM_CNS); ii = sum(island[c] for c in ds.IND_CNS)
    a_res = {b: pop[b] / tp for b in load_buses}
    a_com = {b: sum(jobs[b][c] for c in ds.COM_CNS) / ci for b in load_buses}
    a_ind = {b: sum(jobs[b][c] for c in ds.IND_CNS) / ii for b in load_buses}

    # ------------------------------------------------ behind-the-meter sector splits
    _, nm = eia861("Net_Metering_2021.xlsx", "Hawaiian Electric Co Inc")
    _, dg = eia861("Non_Net_Metering_Distributed_2021.xlsx", "Hawaiian Electric Co Inc")
    _, ee = eia861("Energy_Efficiency_2021.xlsx", "Hawaii Energy Efficiency Program")
    nm = nm.iloc[0]; dg = dg.iloc[0]; ee = ee.iloc[0]
    # Net_Metering: PV capacity MW in cols 6..9 (Res, Com, Ind, Transp)
    # Non_Net_Metering_Distributed: PV MW in cols 10..14 (Res, Com, Ind, Transp, Direct)
    # Energy_Efficiency: incremental annual savings MWh in cols 5..8 (Res, Com, Ind, Transp)
    pv_res = num(nm[6]) + num(dg[10])
    pv_com = num(nm[7]) + num(dg[11]) + num(dg[14])
    pv_ind = num(nm[8]) + num(dg[12])
    pv_t = pv_res + pv_com + pv_ind
    ee_res, ee_com = num(ee[5]), num(ee[6]) + num(ee[7])
    ee_t = ee_res + ee_com
    s_pv = {"res": pv_res / pv_t, "com": pv_com / pv_t, "ind": pv_ind / pv_t}
    s_ee = {"res": ee_res / ee_t, "com": ee_com / ee_t, "ind": 0.0}
    print(f"  rooftop PV by sector (EIA-861 2021, HECO): res {pv_res:.1f} MW  "
          f"com {pv_com:.1f} MW  ind {pv_ind:.1f} MW  -> {s_pv['res']:.1%} / "
          f"{s_pv['com']:.1%} / {s_pv['ind']:.1%}")
    print(f"  efficiency savings by sector (EIA-861 2021, Hawaii Energy): res "
          f"{ee_res:,.0f} MWh  com {ee_com:,.0f} MWh -> {s_ee['res']:.1%} / {s_ee['com']:.1%}")

    key = {"res": a_res, "com": a_com, "ind": a_ind}
    def split(v, shares):
        return {b: v * sum(shares[s] * key[s][b] for s in shares) for b in load_buses}

    # ------------------------------------------------ shapes and sector energy
    f_res, f_com, f_ind = ds.sector_energy()
    rows = list(csv.DictReader(open(SRC / "oahu_load_components_2021.csv")))
    stamps = [datetime.datetime.fromisoformat(r["timestamp_hst"]).replace(tzinfo=None)
              for r in rows]
    keys = [ds._bucket(t) for t in stamps]
    occ = ds.emitted_hour_occupancy(stamps)
    sh_res = ds.residential_shape(occ)
    sh_com = ds.commercial_shape(island, occ)
    flat = 1.0 / len(rows)

    out = []; n_clip = 0; clip_mwh = 0.0; pinned = defaultdict(int); worst_resid = 0.0
    for r, k in zip(rows, keys):
        gross = float(r["gross_load_mw"]); net = float(r["net_load_mw"])
        w_res, w_com, w_ind = f_res * sh_res.get(k, 0.0), f_com * sh_com.get(k, 0.0), f_ind * flat
        W = w_res + w_com + w_ind
        g = {"res": w_res / W * gross, "com": w_com / W * gross, "ind": w_ind / W * gross}
        d = {b: sum(g[s] * key[s][b] for s in g) for b in load_buses}
        layers = {
            "dgpv":  (float(r["dgpv_mw"]), s_pv),
            "ee":    (float(r["energy_efficiency_mw"]), s_ee),
            "rbess": (float(r["residential_dbess_mw"]), {"res": 1.0}),
            "cbess": (float(r["commercial_dbess_mw"]), {"com": 1.0}),
            "ibess": (float(r["industrial_dbess_mw"]), {"ind": 1.0}),
            "obess": (float(r["other_dbess_mw"]), {"res": 1.0}),
            "tou":   (float(r["tou_shift_mw"]), {"res": 1.0}),
        }
        bundle = sum(v for v, _ in layers.values())
        worst_resid = max(worst_resid, abs(gross + bundle - net))
        for v, sh in layers.values():
            for b, x in split(v, sh).items():
                d[b] += x
        neg = sum(-v for v in d.values() if v < 0)
        if neg > 0:
            n_clip += 1; clip_mwh += neg
            for b, v in d.items():
                if v < 0: pinned[b] += 1
            d = {b: max(v, 0.0) for b, v in d.items()}
        s = sum(d.values())
        d = {b: v * net / s for b, v in d.items()}
        out.append((r["hour"], r["timestamp_hst"], net, d))

    all_buses = [b["bus"] for b in buses]
    with open(OUT / "bus_hourly_demand.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hour", "timestamp_hst", "net_load_mw"] + [f"load_{b}_mw" for b in all_buses])
        for h, ts, net, d in out:
            w.writerow([h, ts, f"{net:.4f}"] + [f"{d.get(b, 0.0):.4f}" for b in all_buses])

    # ------------------------------------------------ reports
    print(f"\n  layer bookkeeping: gross + layers = net to within {worst_resid:.2e} MW")
    print(f"  negative-load clipping: {n_clip} of {len(out)} hours, "
          f"{clip_mwh:.1f} MWh moved; buses pinned: {dict(pinned) or 'none'}")
    mean = {b: sum(d[b] for *_, d in out) / len(out) for b in load_buses}
    tot = sum(mean.values())
    # PUC D&O 23747 compares shares at the 2002 DAY peak: take the 50 highest-load
    # daytime (10:00-16:00) hours of 2021
    day = [o for o in out if 10 <= datetime.datetime.fromisoformat(o[1]).hour <= 16]
    top = sorted(day, key=lambda o: -o[2])[:50]
    peak = {b: sum(o[3][b] for o in top) / sum(o[2] for o in top) for b in load_buses}
    print(f"\n  {'substation':10s} {'people':>9s} {'com jobs':>9s} {'ind jobs':>9s} "
          f"{'mean MW':>8s} {'share':>7s} {'day-peak share':>15s}")
    for b in load_buses:
        print(f"  {b:10s} {pop[b]:9,.0f} {sum(jobs[b][c] for c in ds.COM_CNS):9,d} "
              f"{sum(jobs[b][c] for c in ds.IND_CNS):9,d} {mean[b]:8.1f} "
              f"{mean[b]/tot:7.1%} {peak[b]:15.1%}")
    print("\n  CHECK against Hawai'i PUC D&O 23747 (2002 day peak):")
    print(f"    Pukele             model {peak['Pukele']:.1%}   filed ~17%")
    print(f"    Koolau + Pukele    model {peak['Koolau']+peak['Pukele']:.1%}   filed ~30%")
    print(f"    Downtown           model {peak['Downtown']:.1%}   filed ~25%")
    json.dump({"peak_share": peak, "mean_mw": mean, "clip_hours": n_clip,
               "clip_mwh": clip_mwh, "pinned": dict(pinned), "pv_split": s_pv,
               "ee_split": s_ee, "people": dict(pop),
               "com_jobs": {b: sum(jobs[b][c] for c in ds.COM_CNS) for b in load_buses},
               "ind_jobs": {b: sum(jobs[b][c] for c in ds.IND_CNS) for b in load_buses}},
              open(OUT / "demand_build_report.json", "w"), indent=1)


if __name__ == "__main__":
    main()
