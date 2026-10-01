#!/usr/bin/env python3
"""
build_generators.py -- the 24 dispatchable units, their cost, and their bus.

CAPACITY  EIA Form 860, 2024, summer capacity (sources/oahu_generators_eia.csv).

FUEL COST  EIA Form 923 2024 heat rate x Hawaiian Electric's 2024 fuel-price
           forecast (IGP Inputs Workbook 3). The source file stores it inside a total
           that includes a placeholder VOM (PLACEHOLDER_VOM below); the placeholder is
           subtracted to recover the fuel cost.

VARIABLE O&M (VOM) -- the non-fuel cost of each MWh, from published values,
           Hawai'i-specific wherever one exists:

    combined cycle        $2/MWh   Hawaiian Electric, 2021 IGP Inputs & Assumptions,
                                   Table A-9, 2024 value
    combustion turbine    $7/MWh   same document, Table A-10, 2024
    internal combustion  $31/MWh   same document, Table A-10, 2024
    oil/gas steam       $0.88/MWh  U.S. EPA Power Sector Modeling Platform v6, Summer
                                   2021 Reference Case, Table 4-8 (existing oil/gas steam,
                                   no SO2/NOx/Hg control, 2019$); HECO publishes no value
                                   for its existing steam units
    municipal waste     $6.94/MWh  same EPA table, "Landfill Gas / Municipal Solid Waste"
    (The HECO values are for NEW units of each type, pp. A-10 and A-11; they are
     the closest published Hawai'i numbers for the existing ones.)

           VOM is small next to fuel ($94-$240/MWh) and none of these changes reorders
           the fleet's merit order.

BUS        Each plant is attached to the 138 kV substation it feeds:
             Kahe units          -> Kahe
             Waiau units         -> Waiau
             Schofield           -> Wahiawa   (nearest 138 kV substation, 2.4 mi)
             H-Power, Kalaeloa,
             CIP CT-1            -> Kalaeloa  (AES switching station: the AES-CEIP 2
                                              line carries power "from existing
                                              independent power producers AES, H-Power,
                                              and Kalaeloa, as well as from Hawaiian
                                              Electric's CIP CT-1 generating unit",
                                              HECO, PUC Docket 2016-0439, pp. 1-2)
"""
import csv, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC  = HERE / "sources" / "oahu_generators_eia.csv"
OUT  = HERE / "data"

PLACEHOLDER_VOM = {"steam": 5.0, "combustion_turbine": 4.5, "combined_cycle": 4.0,
           "internal_combustion": 5.0, "municipal_waste": 10.0}
NEW_VOM = {"steam": 0.88, "combustion_turbine": 7.0, "combined_cycle": 2.0,
           "internal_combustion": 31.0, "municipal_waste": 6.94}
VOM_SRC = {
 "steam": "EPA Power Sector Modeling Platform v6 (Summer 2021), Table 4-8, O/G steam, 2019$",
 "combustion_turbine": "HECO 2021 IGP Inputs & Assumptions, Table A-10 (CT, 2024)",
 "combined_cycle": "HECO 2021 IGP Inputs & Assumptions, Table A-9 (CC, 2024)",
 "internal_combustion": "HECO 2021 IGP Inputs & Assumptions, Table A-10 (ICE, 2024)",
 "municipal_waste": "EPA Power Sector Modeling Platform v6 (Summer 2021), Table 4-8, Landfill Gas/MSW, 2019$",
}
PLANT_BUS = {"765": "Kahe", "766": "Waiau", "60328": "Wahiawa",
             "10334": "Kalaeloa", "54646": "Kalaeloa", "56329": "Kalaeloa"}
BUS_SRC = {
 "Kahe": "Kahe generating station is the Kahe 138 kV switchyard",
 "Waiau": "Waiau generating station is the Waiau 138 kV substation",
 "Wahiawa": "nearest 138 kV substation to the Schofield plant (EIA-860 coordinates)",
 "Kalaeloa": "HECO PUC Docket 2016-0439: AES-CEIP 2 carries AES, H-Power, Kalaeloa, CIP CT-1",
}


def main():
    rows = list(csv.DictReader(open(SRC)))
    out = []
    for r in rows:
        tech = r["technology"]
        fuel = float(r["varcost_usd_per_mwh"]) - PLACEHOLDER_VOM[tech]
        vc = fuel + NEW_VOM[tech]
        bus = PLANT_BUS[r["plant_code"]]
        out.append({"name": r["name"], "technology": tech, "plant_code": r["plant_code"],
                    "bus": bus, "p_max_mw": r["p_max_mw"],
                    "fuel_usd_per_mwh": f"{fuel:.4f}", "vom_usd_per_mwh": f"{NEW_VOM[tech]:.2f}",
                    "varcost_usd_per_mwh": f"{vc:.4f}",
                    "capacity_source": r["capacity_source"],
                    "fuel_source": "EIA-923 2024 heat rate x HECO IGP Workbook 3 2024 fuel price",
                    "vom_source": VOM_SRC[tech], "bus_source": BUS_SRC[bus]})
    with open(OUT / "generators.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    seen = {}
    for g in out:
        k = (g["technology"], g["bus"])
        seen.setdefault(k, [0.0, float(g["varcost_usd_per_mwh"])])[0] += float(g["p_max_mw"])
    print(f"{'technology':20s} {'bus':9s} {'MW':>7s} {'$/MWh':>8s}")
    for (t, b), (mw, vc) in sorted(seen.items(), key=lambda kv: kv[1][1]):
        print(f"{t:20s} {b:9s} {mw:7.1f} {vc:8.2f}")
    print(f"total {sum(float(g['p_max_mw']) for g in out):.1f} MW")


if __name__ == "__main__":
    main()
