# =====================================================================
# case.jl -- the test system, loaded from the CSV files in ./data
#
# Everything the linear program needs and nothing it does not:
#   substations, lines (susceptance and thermal rating), generators
#   (location, capacity, cost), and the hourly demand at every substation.
#
# Files, all in ./data, all written by the build_*.py scripts:
#   network_buses.csv      bus, latitude, longitude          (build_network.py)
#   network_branches.csv   from_bus, to_bus, x_pu, limit_mw,
#                          limit_low_mw, limit_high_mw       (build_network.py)
#   generators.csv         name, technology, bus, p_max_mw,
#                          varcost_usd_per_mwh               (build_generators.py)
#   bus_hourly_demand.csv  hour, load_<bus>_mw, 8,760 rows   (build_demand.py)
#
# THREE SWITCHES, all environment variables, all for the sensitivity runs:
#   RATING = "low" | "base" (default) | "high"
#            150 MW, 209.9 MW or 318.7 MW per circuit (see build_network.py)
#   DEMAND = "model" (default) | "puc"
#            "puc" reads bus_hourly_demand_puc.csv, the same hours re-weighted so
#            the substation shares match those HECO filed for the 2002 day peak
#            (see build_demand_puc.py)
#   NOISE  = "0" (default) | e.g. "0.25"
#            adds an independent local wiggle to every substation, in every hour
#            and every random draw: d_b + NOISE * sigma_b * eta, eta ~ N(0, 1).
#            The demand file is built from three island-wide sector curves, so its
#            covariance matrix has rank 3; real substations also move on their own
#            (local weather, one large customer, switching). This term stands in
#            for that, and makes the covariance full rank (see add_local_noise).
# Results of a sensitivity run go to out_<tag>/ instead of out/.
# =====================================================================

using CSV, DataFrames, Statistics, Random

const DATA     = joinpath(@__DIR__, "data")
const VOLL     = 10_000.0     # $/MWh for unserved demand: MISO's value, FERC-approved 2025
const BASE_MVA = 100.0        # per-unit base, the MATPOWER convention
const SLACK    = "Waiau"      # angle reference; any bus gives identical flows
const RATING   = get(ENV, "RATING", "base")
const DEMAND   = get(ENV, "DEMAND", "model")
const NOISE    = parse(Float64, get(ENV, "NOISE", "0"))

"The name of this run: base, low, high, puc, puc_low, noise25, ..."
function run_tag()
    parts = String[]
    DEMAND == "puc" && push!(parts, "puc")
    RATING != "base" && push!(parts, RATING)
    NOISE > 0 && push!(parts, "noise$(round(Int, 100 * NOISE))")
    isempty(parts) ? "base" : join(parts, "_")
end
"Where this run writes its results."
outdir() = (d = joinpath(@__DIR__, run_tag() == "base" ? "out" : "out_$(run_tag())");
            mkpath(d); d)

struct Case
    nbus     :: Int
    bus_name :: Vector{String}
    slack    :: Int
    gen_name :: Vector{String}
    gen_tech :: Vector{String}
    gen_bus  :: Vector{Int}
    pmax     :: Vector{Float64}
    cost     :: Vector{Float64}
    fbus     :: Vector{Int}
    tbus     :: Vector{Int}
    sus      :: Vector{Float64}
    rate     :: Vector{Float64}
end

function load_case(; rating::String = RATING)
    busdf = CSV.read(joinpath(DATA, "network_buses.csv"),    DataFrame)
    brdf  = CSV.read(joinpath(DATA, "network_branches.csv"), DataFrame)
    gendf = CSV.read(joinpath(DATA, "generators.csv"),       DataFrame)
    idx   = Dict(String(b) => i for (i, b) in enumerate(busdf.bus))
    col   = rating == "low"  ? :limit_low_mw  :
            rating == "high" ? :limit_high_mw : :limit_mw
    Case(
        nrow(busdf), String.(busdf.bus), idx[SLACK],
        String.(gendf.name), String.(gendf.technology),
        [idx[String(b)] for b in gendf.bus],
        Float64.(gendf.p_max_mw), Float64.(gendf.varcost_usd_per_mwh),
        [idx[String(b)] for b in brdf.from_bus],
        [idx[String(b)] for b in brdf.to_bus],
        1 ./ Float64.(brdf.x_pu),
        Float64.(brdf[!, col]),
    )
end

"""
    hourly_demand(case)

The demand matrix: one row per substation, one column per hour of 2021, MW.
"""
function hourly_demand(case::Case)
    f  = DEMAND == "puc" ? "bus_hourly_demand_puc.csv" : "bus_hourly_demand.csv"
    df = CSV.read(joinpath(DATA, f), DataFrame)
    D  = Matrix{Float64}(undef, case.nbus, nrow(df))
    for (i, b) in enumerate(case.bus_name)
        D[i, :] = Float64.(df[!, Symbol("load_$(b)_mw")])
    end
    return D
end

"""
    add_local_noise(Dm, sigma; seed)

Give every substation its own independent wiggle, hour by hour (or draw by draw):
    d_b  ->  max(0, d_b + NOISE * sigma_b * eta_b),   eta_b ~ N(0, 1), independent.
With NOISE = 0 it returns Dm unchanged. sigma_b is the substation's own standard
deviation in the recorded year, so NOISE is "how big the local wiggle is, as a
share of the substation's usual swing". The covariance of the result is
Sigma + diag((NOISE * sigma)^2): full rank for every substation that has load.
"""
function add_local_noise(Dm::AbstractMatrix, sigma::AbstractVector; seed::Int)
    NOISE == 0 && return Dm
    rng = MersenneTwister(seed)
    out = similar(Dm)
    for s in axes(Dm, 2), i in axes(Dm, 1)
        out[i, s] = max(0.0, Dm[i, s] + NOISE * sigma[i] * randn(rng))
    end
    out
end
