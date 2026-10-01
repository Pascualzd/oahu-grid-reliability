# Where every number comes from

Every input the model uses is listed here with its value, its source, and whether it is
**measured** (a public record of Oʻahu's own grid), a **stand-in** (Oʻahu's own value is
not public, so the closest documented value is used), a **utility forecast**, or an
**assumption**. The same table is Appendix A of `paper.pdf`.

## The network — `build_network.py` → `data/network_buses.csv`, `data/network_branches.csv`

| Input | Value used | Source | Kind |
|---|---|---|---|
| Substations and locations | 11 buses | HIFLD *Electric Power Transmission Lines* (DHS/CISA), 138 kV lines on Oʻahu; each line names its two substations; a substation sits where all its lines meet. File: `sources/hifld_oahu_transmission_lines.geojson` ([service](https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0), queried 2026-09-22) | measured |
| Which substations are joined | 16 corridors | HIFLD; Hawaiian Electric *Transmission REZ Study* (Nov 2021) single-line diagrams Figs 30–36 ([PDF](https://www.hawaiianelectric.com/documents/clean_energy_hawaii/integrated_grid_planning/stakeholder_engagement/working_groups/solution_evaluation_and_optimization/20211105_transmission_renewable_energy_zone_study.pdf)); Hawaiʻi PUC D&O 23747, Docket 03-0417 (2007) pp. 7–11 ([PDF](https://files.hawaii.gov/dcca/dca/dno/dno2007/23747.pdf)) | measured |
| Circuits per corridor | 1–3, 25 total | REZ Figs 30–36 and Table 10-3 (e.g. "Kahe-Halawa #1/#2", "Waiau-Makalapa 1/2", "Ko`olau-Waiau #1/#2"); PUC D&O 23747 ("Two 138kv transmission lines currently feed the Pukele Substation from the Koolau Substation"; "three 138kv transmission lines providing power from the Halawa and Makalapa Substations"); IGP RFP Appendix H, Attachment 1, worked example ("Waiau-Ewa Nui 1 and Waiau-Ewa Nui 2 138kV circuits", [PDF](https://www.hawaiianelectric.com/documents/clean_energy_hawaii/selling_power_to_the_utility/competitive_bidding/igp_rfp/igp_rfp_appx_h_interconnection_facilities_cost_and_schedule.pdf)); PUC Docket 2016-0439 application ("Kahe-CEIP 1&2", AES–CEIP 2, [PDF](https://www.hawaiianelectric.com/documents/about_us/investing_in_the_future/dkt_2016_0439_20161230_application_AES_CEIP_2_138_kV_OH_line_relocation.pdf)); otherwise the number of HIFLD routes | measured |
| Line lengths | 2.15–20.69 mi | measured along the HIFLD route geometry | measured |
| Per-circuit rating | 209.9 MW | one 795 kcmil AAC conductor per phase — what the REZ study draws for its new 138 kV circuits into Halawa (Figs 30, 33, 36); 878 A, Southwire spec 80120 Table 2 (75 °C conductor, 25 °C air, 2 ft/s wind, sun, [spec](https://cabletechsupport.southwire.com/en/cablespec/download_spec/?spec=80120)); √3 × 138 kV × 878 A | **stand-in** |
| Rating, low sensitivity | 150 MW | 3 × SIL of a typical 138 kV line (SIL = 50 MW), Univ. of Utah ECE 3600 notes, "Transmission Line Typical Values" ([PDF](https://my.ece.utah.edu/~ece3600/Notes_TransmissionLines_S23.pdf)) | stand-in |
| Rating, high sensitivity | 318.6 MW | 1590 kcmil AAC, 1,333 A (Southwire 80120), the conductor REZ Figs 32, 34, 35 label on planned new Kahe–Wahiawa and Makalapa circuits (REZ Table 5-3 prints "1950 AAC" for the same Kahe–Wahiawa circuits, not a standard size) | stand-in |
| Line reactance | 0.48 Ω/km | typical ωL of a 138 kV line, one conductor per phase (Utah notes, same table); same quantity as X = 2πf·2e-7·ln(GMD/GMR) used by Gegner et al., IEEE PECI 2016. Cancels out of the DC flows because it is the same per mile everywhere | stand-in |
| Merged buses | Downtown (Iwilei, School St, Archer, Kewalo, Kamoku); Kalaeloa (AES + Kalaeloa, 0.46 mi apart) | PUC D&O 23747 names the downtown substations; HIFLD draws only Kewalo | simplification |

Known limits of the rating stand-in: the REZ study re-conductors some existing lines *to*
double-bundled 795 AAC (Table 5-3), so those lines carry less than that today; and the 2016
AES–CEIP 2 application specifies 1780 kcmil ACSS for the relocated section (p. 7), so the
CEIP–Kalaeloa corridor is probably rated higher than modelled.

## The generators — `build_generators.py` → `data/generators.csv`

| Input | Value used | Source | Kind |
|---|---|---|---|
| Units and summer capacity | 24 units, 1,508.1 MW | EIA Form 860, 2024 ([data](https://www.eia.gov/electricity/data/eia860/)); file `sources/oahu_generators_eia.csv` | measured |
| Heat rates | per plant | EIA Form 923, 2024 ([data](https://www.eia.gov/electricity/data/eia923/)) | measured |
| Fuel prices | 2024 forecast | Hawaiian Electric, Final Oʻahu IGP Inputs Workbook 3, filed 2022-03-31 ([XLSX](https://www.hawaiianelectric.com/documents/clean_energy_hawaii/integrated_grid_planning/20220331_final_oahu_inputs_workbook_3_revised.xlsx)) | utility forecast |
| Variable O&M, CC / CT / engines | $2 / $7 / $31 per MWh | Hawaiian Electric, *2021 IGP Inputs and Assumptions* (Aug 2021), Tables A-9 and A-10, 2024 row, pp. A-10–A-11 — values for **new** units ([PDF](https://www.hawaiianelectric.com/documents/clean_energy_hawaii/integrated_grid_planning/stakeholder_engagement/working_groups/forecast_assumptions/20210818_finaligp_inputs_and_assumptions.pdf)) | stand-in |
| Variable O&M, oil steam / waste | $0.88 / $6.94 per MWh (2019$) | U.S. EPA Power Sector Modeling Platform v6, Summer 2021 Reference Case, Table 4-8 ([PDF](https://www.epa.gov/system/files/documents/2021-09/chapter-4-generating-resources.pdf)) | stand-in |
| H-Power fuel cost | $0/MWh | burns municipal waste | assumption |
| Plant → substation | Kahe, Waiau (own switchyards); Schofield → Wahiawa (nearest); H-Power, Kalaeloa, CIP CT-1 → Kalaeloa | PUC Docket 2016-0439: AES–CEIP 2 carries power "from existing independent power producers AES, H-Power, and Kalaeloa, as well as from Hawaiian Electric's CIP CT-1 generating unit" (pp. 1–2) | measured |
| Penalty for unserved demand | $10,000/MWh | MISO value of lost load, raised from $3,500 and approved by FERC in 2025 ([RTO Insider](https://www.rtoinsider.com/102108-ferc-approves-miso-value-lost-load-increase/)) | stand-in |
| Power base | 100 MVA | MATPOWER convention (Zimmerman et al., IEEE TPWRS 2011) | convention |

## Demand — `build_demand.py`, `demand_shapes.py` → `data/bus_hourly_demand.csv`

| Input | Value used | Source | Kind |
|---|---|---|---|
| Island hourly load, 2021 | 8,760 values, net of rooftop PV, customer batteries, efficiency, TOU | IGP Inputs Workbook 3 (link above); file `sources/oahu_load_components_2021.csv` | measured (filed) |
| Population | 2020 census tracts, Honolulu County | U.S. Census 2020 via TIGERweb ([service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer)); `sources/tigerweb_2020_tracts_honolulu.json` | measured |
| Jobs by sector | 2021 census blocks | LEHD LODES8, Hawaiʻi WAC + crosswalk ([data](https://lehd.ces.census.gov/data/lodes/LODES8/hi/)) | measured |
| Sector split, rooftop-PV and efficiency shares | 2021 | EIA Form 861, utility "Hawaiian Electric Co Inc" ([data](https://www.eia.gov/electricity/data/eia861/)) | measured |
| Hourly shapes | 1 home, 15 commercial building types, Honolulu | OpenEI / DOE reference buildings, TMY3 Honolulu ([files](https://openei.org/datasets/files/961/pub)); electricity per worker from EIA CBECS 2018, Tables C22 and B1 | stand-in |
| Which substation serves whom | nearest load-serving substation on the same side of the Koʻolau range (by 2020 county subdivision) | Voronoi catchments as in PyPSA-Eur (Hörsch et al., *Energy Strategy Reviews* 22, 2018); Pukele's neighbourhoods "Kahala, Kaimuki, Manoa, Makiki, and Waikiki" from PUC D&O 23747 p. 9, extended east to Hawaiʻi Kai | method |
| How the pieces combine | d_b(t) = Σ_s k_b,s · N_s(t), i.e. D = K N: N_s(t) is the island's hourly load of sector s (filed total × EIA-861 share × hourly shape, minus that sector's share of rooftop PV, efficiency and batteries); k_b,s is substation b's share of island people / commercial jobs / industrial jobs | method (makes Σ rank 3) |
| Local variation per substation | f = 0.10, 0.25, 0.50 of each substation's σ (sensitivity only) | none published — Hawaiian Electric does not publish hourly substation load | sensitivity |
| Check / sensitivity shares | Pukele 17 %, Koolau + Pukele 30 %, Iwilei + School St + HPP 25 % | PUC D&O 23747 pp. 7–9 (17 % and 25 % at the 2002 day peak) | filed (2002) |
| County subdivisions and shoreline (map) | 2020 | Census TIGERweb CCDs; Census cartographic boundary file `cb_2020_15_cousub_500k` ([ZIP](https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_15_cousub_500k.zip)) | measured |

## Sources considered and not used

* **Texas A&M "Hawaii40"** ([page](https://electricgrids.engr.tamu.edu/hawaii40/)): 37 buses
  on Oʻahu's footprint, but the page states "This case is synthetic and does not model the
  actual grid", so none of its line data are used.
* **OpenStreetMap power lines**: the Overpass API was not reachable from the build
  environment; HIFLD gives the same line geometry with substation names.

## The random draws

Each substation's hourly demand is summarised by its mean μ and standard deviation σ
(`out/bus_fit.csv`); the eleven are joined by their 11 × 11 covariance matrix Σ
(`out/bus_corr.csv` holds the correlations). Draws are d = max(0, μ + L z), z ~ N(0, I),
L Lᵀ = Σ, with L from an eigendecomposition (Σ has rank 3). Seed 1, 10,000 draws.
