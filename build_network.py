#!/usr/bin/env python3
"""
build_network.py -- O'ahu's 138 kV transmission network, from public records.

Every substation, circuit and length below comes from a public document that
names the real substations and the real circuits; the two numbers the utility does
not publish (line rating and reactance) are stand-ins from the closest documented
source, and say so.

WHERE EACH PIECE COMES FROM

  Which substations exist, and where
      HIFLD "U.S. Electric Power Transmission Lines" (DHS/CISA), queried for
      O'ahu. Each 138 kV line carries the names of the two substations it joins
      (SUB_1, SUB_2); a substation's location is the line end that all of its
      lines share. File: sources/hifld_oahu_transmission_lines.geojson.

  Which substations are joined, and by how many circuits
      Hawaiian Electric's own single-line diagrams and filings, which name
      circuits one by one ("Waiau-Makalapa 1", "Waiau-Makalapa 2"). Where HECO
      names two circuits and HIFLD draws one line, HECO is followed. Where HECO
      is silent, HIFLD is followed. Every row below says which.

        [REZ]  Hawaiian Electric, Transmission Renewable Energy Zone Study,
               Nov 2021, Figs 30-36 (single-line diagrams of Halawa, Koolau,
               Wahiawa, Waiau, Makalapa; existing circuits drawn in black and
               named, e.g. "Kahe-Halawa #1", "Waiau-Makalapa 2") and Table 5-3.
        [RFP]  Hawaiian Electric, IGP RFP for Renewable Dispatchable Generation
               and Energy Storage, Appendix H, Attachment 1, p. 1: "Waiau-Ewa Nui 1
               and Waiau-Ewa Nui 2 138kV circuits".
        [AES]  Hawaiian Electric, PUC Docket 2016-0439 (application filed
               30 Dec 2016): the AES-CEIP 2 138 kV line carries power "from existing
               independent power producers AES, H-Power, and Kalaeloa, as well as
               from Hawaiian Electric's CIP CT-1 generating unit" (pp. 1-2).
        [PUC]  Hawai'i PUC Decision & Order No. 23747 (Docket 03-0417, 2007),
               East O'ahu Transmission Project: three 138 kV lines feed Koolau,
               two feed Pukele from Koolau, three from Halawa and Makalapa feed
               the downtown substations (Iwilei, School Street).

  How long each line is
      Measured along the HIFLD route geometry (great-circle, segment by
      segment). No routing factor is needed.

  How much each circuit carries (the RATING)
      Not published by Hawaiian Electric for existing lines. The closest
      documented stand-in is the conductor HECO draws for NEW 138 kV circuits on
      O'ahu: 795 kcmil all-aluminium conductor ("795 AAC", REZ Figs 30, 33, 36;
      Southwire code name "Arbutus"). Its allowable ampacity is 878 A (Southwire
      spec 80120, Table 2: conductor 75 C, ambient 25 C, emissivity 0.5, wind
      2 ft/s, in sun), so one circuit carries sqrt(3) x 138 kV x 878 A =
      209.9 MVA. The DC power flow treats the MVA rating as a MW limit, the
      usual convention.
      Two sourced alternatives are carried as a sensitivity (RATING_SCENARIOS):
        150 MW  3 x SIL of a typical 138 kV line, the loadability of a short line
                (University of Utah ECE 3600 notes, "Transmission Line Typical
                Values": SIL 50 MW; 629 A is the current at 3 x SIL)
        318.6 MW 1590 kcmil AAC ("Coreopsis"), 1,333 A (Southwire spec 80120),
                the conductor HECO labels on its NEW Kahe-Wahiawa, Halawa-Makalapa
                and Makalapa-Waiau circuits [REZ Figs 32, 34, 35]. (REZ Table 5-3
                prints "1950 AAC" for the Kahe-Wahiawa circuits; 1950 is not a
                standard AAC size and Fig 32 labels the same circuits 1590 AAC.)

  How easily power flows down each line (the REACTANCE)
      0.48 ohm/km = 0.7725 ohm/mi, the typical series reactance (omega L) of a
      138 kV line with one conductor per phase (University of Utah ECE 3600
      notes, same table). Synthetic-grid builders compute the same quantity from
      X = 2 pi f 2e-7 ln(GMD/GMR) per metre (Gegner, Birchfield, Xu, Shetye,
      Overbye, "A Methodology for the Creation of Geographically Realistic
      Synthetic Power Flow Models", IEEE PECI 2016, Sec. IV.A).
      Because every line gets the SAME ohms-per-mile, this number cancels out of
      the DC power flow: flows depend only on RATIOS of reactances, which are
      ratios of lengths. Its exact value changes nothing in the results.

THREE SIMPLIFICATIONS, ALL STATED IN THE PAPER
  * The downtown substations -- Iwilei and School Street (the two the PUC names
    as serving downtown), plus Archer, Kewalo and Kamoku -- are merged into one
    bus, "Downtown". HIFLD draws only Kewalo, and no public source gives how
    they are wired to each other. The three
    138 kV lines that feed downtown from outside -- "three 138kv transmission
    lines providing power from the Halawa and Makalapa Substations" [PUC, p. 7]
    -- are kept.
  * AES (a switching station; the AES coal plant retired in 2022) and Kalaeloa
    are 0.46 mile apart (their HIFLD line ends) and are merged into one bus,
    "Kalaeloa".
  * The "Kahe-Makalapa" circuit terminates in a breaker bay at Halawa [REZ
    Figs 30, 33, 36], so electrically it is a third Kahe-Halawa circuit
    followed by the Halawa-Makalapa line [HIFLD].

    python3 build_network.py            # writes data/network_*.csv
"""
import csv, json, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC  = HERE / "sources" / "hifld_oahu_transmission_lines.geojson"
OUT  = HERE / "data"; OUT.mkdir(exist_ok=True)

KV, BASE_MVA = 138.0, 100.0
ZBASE = KV**2 / BASE_MVA                      # 190.44 ohm
X_OHM_PER_MI = 0.48 * 1.609344                # 0.7725 ohm/mi
AMPACITY_795_AAC = 878.0                      # A, Southwire spec 80120
RATING_PER_CIRCUIT = math.sqrt(3) * KV * AMPACITY_795_AAC / 1000.0   # 209.9 MW
RATING_SCENARIOS = {"low_150": 150.0,
                    "base_795AAC": RATING_PER_CIRCUIT,
                    "high_1590AAC": math.sqrt(3) * KV * 1333.0 / 1000.0}

# ---------------------------------------------------------------- buses
# name -> (HIFLD substation names that locate it, what it is, what it serves)
BUSES = {
  "Kahe":      (["KAHE 1", "KAHE 2"], "Kahe generating station switchyard",
                "Waianae coast (via 46 kV)"),
  "Kalaeloa":  (["KALAELOA", "AES"], "AES switching station and Kalaeloa plant",
                "none -- generation only"),
  "CEIP":      (["CEIP"], "Campbell Estate Industrial Park substation",
                "Campbell Industrial Park, Kapolei"),
  "Ewa Nui":   (["EWA NUI"], "Ewa Nui substation", "Ewa, Ewa Beach, Kapolei"),
  "Waiau":     (["WAIAU 1"], "Waiau generating station and substation",
                "Pearl City, Waipahu, Mililani"),
  "Wahiawa":   (["WAHIAWA"], "Wahiawa substation",
                "Wahiawa, Schofield, the North Shore"),
  "Halawa":    (["HAIAWA"], "Halawa substation", "Aiea, Halawa, Moanalua"),
  "Makalapa":  (["MAKALAPA"], "Makalapa substation",
                "Pearl Harbor, Hickam, Salt Lake"),
  "Downtown":  (["KEWALO"], "Iwilei, School St, Archer, Kewalo, Kamoku (merged)",
                "downtown, Kalihi, Kaka'ako, Ala Moana"),
  "Koolau":    (["KOOLAU"], "Koolau substation", "Kaneohe, Kailua, the windward coast"),
  "Pukele":    (["PUKELE"], "Pukele substation",
                "Manoa, Kaimuki, Waikiki, Kahala, Hawaii Kai"),
}

# ---------------------------------------------------------------- circuits
# (from, to, circuits, [HIFLD route(s)], circuit-count source, existence source)
# A route is a list of HIFLD line IDs laid end to end; parallel routes are averaged.
CORRIDORS = [
  ("Kahe", "CEIP",       2, [["157870"], ["157872"]],
   "HIFLD: two in-service 138 kV lines", "HIFLD; [AES] names Kahe-CEIP 1"),
  ("CEIP", "Kalaeloa",   2, [["157868"], ["157869"]],
   "[AES]: AES-CEIP 1 and AES-CEIP 2", "[AES]; HIFLD"),
  ("Kalaeloa", "Ewa Nui",1, [["157866"]], "HIFLD", "HIFLD"),
  ("CEIP", "Ewa Nui",    1, [["157867"]], "HIFLD", "HIFLD"),
  ("Ewa Nui", "Waiau",   2, [["158246"]],
   "[RFP] and [REZ] Fig 34: Waiau-Ewa Nui 1 and 2", "HIFLD; [RFP]; [REZ]"),
  ("Kahe", "Waiau",      1, [["157880"]], "HIFLD", "HIFLD"),
  ("Kahe", "Halawa",     3, [["158245"], ["157881"]],
   "[REZ] Figs 30/33/36: Kahe-Halawa 1, 2 and Kahe-Makalapa terminate at Halawa",
   "[REZ]; HIFLD"),
  ("Kahe", "Wahiawa",    1, [["175125", "175126", "167159"]],
   "[REZ] Fig 32: one existing circuit, Akau-Wahiawa (Kahe-Akau-Hema-Wahiawa)", "[REZ]; HIFLD"),
  ("Wahiawa", "Waiau",   1, [["157874"]],
   "[REZ] Fig 32 and Table 5-3: one existing Waiau-Wahiawa circuit", "[REZ]; HIFLD"),
  ("Waiau", "Makalapa",  2, [["158247"]],
   "[REZ] Fig 34: Waiau-Makalapa 1 and 2", "[REZ]; HIFLD"),
  ("Waiau", "Koolau",    2, [["157877"], ["158250"]],
   "[REZ] Fig 31 names Waiau-Koolau 2; HIFLD two routes; [PUC]: three lines feed Koolau", "[REZ]; [PUC]; HIFLD"),
  ("Halawa", "Koolau",   1, [["158249", "158248", "157878"]],
   "[REZ] Figs 30/31; [PUC]: third line into Koolau", "[REZ]; [PUC]; HIFLD"),
  ("Halawa", "Makalapa", 1, [["156103"]],
   "HIFLD (continuation of the Kahe-Makalapa circuit beyond Halawa, [REZ] Figs 30, 33)", "HIFLD"),
  ("Halawa", "Downtown", 2, [["156104"]],
   "[REZ] Figs 30/33/36: Halawa-Iwilei and Halawa-School", "[REZ]; [PUC]; HIFLD"),
  ("Makalapa", "Downtown", 1, [["157876"]],
   "[PUC]: three lines from Halawa and Makalapa feed downtown", "[PUC]; HIFLD"),
  ("Koolau", "Pukele",   2, [["157879"], ["157378"]],
   "[PUC]: two 138 kV lines feed Pukele from Koolau", "[PUC]; [REZ] Fig 31; HIFLD"),
]


def seg_miles(coords):
    L = 0.0
    for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
        p1, p2 = math.radians(y1), math.radians(y2)
        a = (math.sin((p2 - p1) / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(math.radians(x2 - x1) / 2) ** 2)
        L += 2 * 3958.8 * math.asin(math.sqrt(a))
    return L


def main():
    gj = json.load(open(SRC))
    feats = {f["properties"]["ID"]: f for f in gj["features"]}

    def length(fid):
        g = feats[fid]["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        return sum(seg_miles(p) for p in parts)

    # substation locations: the line end all of a substation's lines share
    ends = []
    for f in gj["features"]:
        p, g = f["properties"], f["geometry"]
        if p["VOLTAGE"] != 138:
            continue
        cs = g["coordinates"] if g["type"] == "LineString" else \
             [c for part in g["coordinates"] for c in part]
        ends.append((p["SUB_1"], p["SUB_2"], tuple(cs[0]), tuple(cs[-1])))
    close = lambda a, b: abs(a[0] - b[0]) < 0.004 and abs(a[1] - b[1]) < 0.004
    loc = {}
    for s1, s2, a, b in ends:
        for n in (s1, s2):
            if n in loc:
                continue
            cands = [(x, y) for u, v, x, y in ends if n in (u, v)]
            pts = [q for ab in cands for q in ab]
            loc[n] = max(pts, key=lambda q: sum(close(q, ab[0]) or close(q, ab[1])
                                                for ab in cands))

    with open(OUT / "network_buses.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bus", "latitude", "longitude", "hifld_names", "what_it_is",
                    "serves", "location_source"])
        for b, (names, what, serves) in BUSES.items():
            lon, lat = loc[names[0]]
            w.writerow([b, f"{lat:.5f}", f"{lon:.5f}", "; ".join(names), what, serves,
                        "HIFLD transmission lines: shared line end of the named substation"])

    print(f"per-circuit rating: sqrt(3) x {KV:.0f} kV x {AMPACITY_795_AAC:.0f} A = "
          f"{RATING_PER_CIRCUIT:.1f} MW   reactance {X_OHM_PER_MI:.4f} ohm/mi\n")
    print(f"{'#':>2} {'from':9s} {'to':9s} {'n':>2} {'miles':>7} {'x_pu':>9} {'MW':>7}")
    with open(OUT / "network_branches.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["branch", "from_bus", "to_bus", "circuits", "length_mi", "x_pu",
                    "limit_mw", "limit_low_mw", "limit_high_mw", "hifld_ids",
                    "circuit_count_source", "existence_source", "length_source",
                    "reactance_source", "rating_source"])
        for i, (a, b, n, routes, csrc, esrc) in enumerate(CORRIDORS, 1):
            L = sum(sum(length(f) for f in r) for r in routes) / len(routes)
            x = X_OHM_PER_MI * L / ZBASE / n             # n identical circuits in parallel
            print(f"{i:2d} {a:9s} {b:9s} {n:2d} {L:7.2f} {x:9.5f} {n*RATING_PER_CIRCUIT:7.1f}")
            w.writerow([i, a, b, n, f"{L:.3f}", f"{x:.6f}",
                        f"{n*RATING_PER_CIRCUIT:.1f}",
                        f"{n*RATING_SCENARIOS['low_150']:.1f}",
                        f"{n*RATING_SCENARIOS['high_1590AAC']:.1f}",
                        "; ".join("+".join(r) for r in routes), csrc, esrc,
                        "HIFLD route geometry, great-circle segment sum",
                        "0.48 ohm/km typical 138 kV (Univ. of Utah ECE 3600); "
                        "uniform per mile, so it cancels from DC flows",
                        "795 AAC per circuit, as drawn for new 138 kV circuits [REZ Figs 30, 33, 36]; 878 A (Southwire spec 80120)"])
    tot = sum(c[2] for c in CORRIDORS)
    print(f"\n{len(BUSES)} buses, {len(CORRIDORS)} corridors, {tot} circuits")


if __name__ == "__main__":
    main()
