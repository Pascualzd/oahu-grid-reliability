#!/usr/bin/env python3
"""
demand_shapes.py -- hourly load shapes for homes, businesses and industry.
Imported by build_demand.py; nothing here is run on its own.

WHAT IT PROVIDES
  residential_shape(occ)          one home's hourly load, U.S. DOE reference house,
                                  Honolulu (OpenEI TMY3 profiles)
  commercial_shape(jobs, occ)     15 reference commercial buildings, Honolulu, blended
                                  by the jobs in each kind of business (LEHD LODES) x
                                  electricity per worker (EIA CBECS 2018, Tables C22, B1)
  sector_energy()                 O'ahu's 2021 sales by sector, EIA-861, utility
                                  "Hawaiian Electric Co Inc"
  emitted_hour_occupancy, _bucket calendar bookkeeping: each shape is indexed by
                                  (month, weekend?, hour)
  get(url, name)                  download a source file into sources/cache once
  COM_CNS, IND_CNS                the LODES job columns counted as commercial / industrial

Industry is flat. Each shape is scaled to unit annual energy; build_demand.py
multiplies it by the sector's share of the island's filed hourly load.

CALENDAR NOTE
The OpenEI reference-building runs use a year whose 1 January is a Sunday; 2021's is a
Friday. Both years are non-leap, so dates line up but weekdays are two days apart
(PROFILE_DOW_OFFSET = 2), checked against three buildings with a clear work week
(LargeOffice, PrimarySchool, Hospital).
"""

import csv, datetime, gzip, io, math, pathlib, sys, urllib.request
from collections import Counter, defaultdict

HERE      = pathlib.Path(__file__).resolve().parent
CACHE     = HERE / "sources" / "cache"   # downloads land here (see get)

YEAR          = 2021

# OpenEI's simulation year starts on a Sunday, 2021 on a Friday: shift weekdays by two.
PROFILE_DOW_OFFSET = 2
OPENEI        = "https://openei.org/datasets/files/961/pub"
HNL           = "USA_HI_Honolulu.Intl.AP.911820_TMY3"

# Commercial reference buildings, and the LODES sector whose employment sets
# each one's weight in the composite commercial shape.
#   CNS07 retail          CNS08 transport/warehouse   CNS15 education
#   CNS16 health care     CNS18 accommodation+food
#   offices: CNS09-14 and CNS17, CNS19, CNS20
OFFICE = ["CNS09","CNS10","CNS11","CNS12","CNS13","CNS14","CNS17","CNS19","CNS20"]
COM_BUILDINGS = {
    "LargeOffice":            (OFFICE,   0.40),
    "MediumOffice":           (OFFICE,   0.35),
    "SmallOffice":            (OFFICE,   0.25),
    "Stand-aloneRetail":      (["CNS07"], 0.45),
    "StripMall":              (["CNS07"], 0.30),
    "SuperMarket":            (["CNS07"], 0.25),
    "LargeHotel":             (["CNS18"], 0.30),
    "SmallHotel":             (["CNS18"], 0.15),
    "FullServiceRestaurant":  (["CNS18"], 0.30),
    "QuickServiceRestaurant": (["CNS18"], 0.25),
    "Hospital":               (["CNS16"], 0.60),
    "OutPatient":             (["CNS16"], 0.40),
    "PrimarySchool":          (["CNS15"], 0.50),
    "SecondarySchool":        (["CNS15"], 0.50),
    "Warehouse":              (["CNS08"], 1.00),
}
# Jobs are a headcount, not a load. Weighting the building blend by headcount
# alone assumes an office worker and a hotel worker stand for the same kilowatts,
# and they do not -- by a factor of five. These convert headcount into estimated
# electricity: EIA CBECS 2018 table C22 (electricity by principal building
# activity) divided by table B1 (workers by the same activity). kWh/worker/year.
#   https://www.eia.gov/consumption/commercial/data/2018/ce/pdf/c22.pdf
#   https://www.eia.gov/consumption/commercial/data/2018/bc/html/b1.php
# NATIONAL figures -- CBECS publishes no state breakout at this detail.
CBECS_KWH_PER_WORKER = {
    "FoodSales":   58_888,   #  54 bn kWh /    917k workers
    "Lodging":     36_179,   # 100 bn kWh /  2,764k
    "FoodService": 21_151,   #  61 bn kWh /  2,884k
    "Mercantile":  20_266,   # 180 bn kWh /  8,882k
    "Inpatient":   18_071,   #  65 bn kWh /  3,597k
    "Warehouse":   13_416,   #  95 bn kWh /  7,081k
    "Education":   12_343,   # 128 bn kWh / 10,370k
    "Outpatient":  10_134,   #  31 bn kWh /  3,059k
    "Office":       6_912,   # 227 bn kWh / 32,843k  <- the least intense of all
}
BUILDING_TO_CBECS = {
    "LargeOffice": "Office", "MediumOffice": "Office", "SmallOffice": "Office",
    "Stand-aloneRetail": "Mercantile", "StripMall": "Mercantile",
    "SuperMarket": "FoodSales",
    "LargeHotel": "Lodging", "SmallHotel": "Lodging",
    "FullServiceRestaurant": "FoodService", "QuickServiceRestaurant": "FoodService",
    "Hospital": "Inpatient", "OutPatient": "Outpatient",
    "PrimarySchool": "Education", "SecondarySchool": "Education",
    "Warehouse": "Warehouse",
}

IND_CNS = ["CNS01","CNS02","CNS03","CNS04","CNS05","CNS06"]
COM_CNS = [f"CNS{i:02d}" for i in range(7, 21)]


def get(url, name):
    p = CACHE / name
    if not p.exists():
        print(f"  downloading {name} ...", flush=True)
        urllib.request.urlretrieve(url, p)
    return p


# ---------------------------------------------------------------- shapes
def _bucket(ts):
    """(month, is_weekend, hour) -- the only key a sector shape is indexed by."""
    return (ts.month, 1 if ts.weekday() >= 5 else 0, ts.hour)


def emitted_hour_occupancy(stamps):
    """
    (month, is_weekend, hour) -> how many of the load file's hours land in that bucket.

    A shape is looked up once per hour of the load file, so the energy it delivers
    over the year is sum_k occupancy[k] * shape[k]. Normalising by this count (and
    not by the bare sum over the 576 buckets) makes every shape deliver exactly one
    unit of energy over the hours actually used. The count is taken from the load
    file's own timestamps, which are hour-ENDING (2021-01-01T01:00 .. 2022-01-01T00:00),
    so it cannot drift from the hours the caller iterates.
    """
    return Counter(_bucket(ts) for ts in stamps)


def _unit_annual_energy(lk, occ):
    """Rescale a bucket -> mean kW lookup so it sums to 1.0 over the emitted hours."""
    e = sum(occ.get(k, 0) * v for k, v in lk.items()) or 1.0
    return {k: v / e for k, v in lk.items()}


def read_profile(path):
    """
    Read an OpenEI file into a (month, is_weekend, hour) -> mean kW lookup.

    Returns the raw bucket means. Normalising them is the caller's job, against
    emitted_hour_occupancy() built from the load file's own timestamps.
    """
    tot = defaultdict(float); cnt = defaultdict(int)
    with open(path, newline="") as f:
        rd = csv.reader(f); hdr = next(rd)
        col = next(i for i, c in enumerate(hdr) if c.startswith("Electricity:Facility")
                   and "Hourly" in c)
        for i, row in enumerate(rd):
            if len(row) <= col or not row[col]:
                continue
            stamp = row[0].strip()                    # "01/01  01:00:00"
            mm = int(stamp[:2]); dd = int(stamp[3:5]); hh = int(stamp.split()[1][:2])
            hh = 0 if hh == 24 else hh
            # Dates carry over from the non-leap reference calendar to 2021;
            # weekdays do NOT. See PROFILE_DOW_OFFSET at the top of this file.
            dow = (_dow(YEAR, mm, dd) + PROFILE_DOW_OFFSET) % 7
            k = (mm, 1 if dow >= 5 else 0, hh)
            tot[k] += float(row[col]); cnt[k] += 1
    return {k: tot[k] / cnt[k] for k in tot}


def _dow(y, m, d):
    return (__import__("datetime").date(y, m, d).weekday())


def commercial_shape(jobs_total, occ):
    """
    Energy-weighted composite of the fifteen commercial reference buildings.

    Each weight is (assumed mix within the job category) x (FILED LODES job count)
    x (CBECS electricity per worker). That last factor is what stops a headcount
    standing in for a load: offices hold 39.5% of O'ahu's commercial jobs but only
    18.4% of its estimated commercial electricity.

    Every component building, and the composite they blend into, is normalised to
    one unit of annual energy over the hours in `occ` (see emitted_hour_occupancy).
    """
    parts, wts = [], []
    for b, (cns, w) in COM_BUILDINGS.items():
        p = get(f"{OPENEI}/COMMERCIAL_LOAD_DATA_E_PLUS_OUTPUT/{HNL}/"
                f"RefBldg{b}New2004_v1.3_7.1_1A_USA_FL_MIAMI.csv", f"com_{b}.csv")
        parts.append(_unit_annual_energy(read_profile(p), occ))    # unit-energy shape
        wts.append(w * sum(jobs_total[c] for c in cns)
                     * CBECS_KWH_PER_WORKER[BUILDING_TO_CBECS[b]])
    W = sum(wts) or 1.0
    keys = set().union(*[set(p) for p in parts])
    comp = {k: sum(p.get(k, 0.0) * w for p, w in zip(parts, wts)) / W for k in keys}
    # A weighted average of unit-annual-energy shapes already carries unit annual
    # energy, so this second pass is a ~1e-16 no-op in practice. It is kept because
    # it is the only line that GUARANTEES the composite the caller gets sums to 1.0
    # over the year even if some component were ever missing a bucket.
    return _unit_annual_energy(comp, occ)


def residential_shape(occ):
    p = get(f"{OPENEI}/RESIDENTIAL_LOAD_DATA_E_PLUS_OUTPUT/BASE/{HNL}_BASE.csv",
            "res_base.csv")
    return _unit_annual_energy(read_profile(p), occ)


# ---------------------------------------------------------------- sector energy
def sector_energy():
    """O'ahu-only sector shares: EIA-861, utility 'Hawaiian Electric Co Inc'."""
    try:
        import pandas as pd, zipfile
    except ImportError:
        sys.exit("pandas + openpyxl required")
    z = zipfile.ZipFile(get("https://www.eia.gov/electricity/data/eia861/archive/zip/"
                            f"f861{YEAR}.zip", f"f861{YEAR}.zip"))
    d = pd.read_excel(z.open(f"Sales_Ult_Cust_{YEAR}.xlsx"), header=None, skiprows=3).iloc[:, :24]
    d.columns = ["year","unum","uname","part","svc","dtype","state","own","ba",
                 "res_rev","res_mwh","res_cust","com_rev","com_mwh","com_cust",
                 "ind_rev","ind_mwh","ind_cust","tra_rev","tra_mwh","tra_cust",
                 "tot_rev","tot_mwh","tot_cust"]
    h = d[d.uname.astype(str).str.strip() == "Hawaiian Electric Co Inc"]
    g = {k: float(pd.to_numeric(h[k], errors="coerce").fillna(0).sum())
         for k in ("res_mwh", "com_mwh", "ind_mwh")}
    t = sum(g.values())
    return g["res_mwh"] / t, g["com_mwh"] / t, g["ind_mwh"] / t
