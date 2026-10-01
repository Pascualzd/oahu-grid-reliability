# =====================================================================
# run_all.jl -- ONE model, three demand inputs.
#
#   actual   the 8,760 recorded hourly nodal demand vectors
#   fitted   10,000 draws, each bus sampled independently from its own
#            fitted normal, truncated at zero
#   corr     10,000 draws from the fitted mean vector and the empirical
#            covariance of the record
#
# Every arm is the SAME LP object; only the right-hand side of the nodal
# balance (and the matching cap on local load shed) changes between solves.
#
# The thermal limit is split into two one-sided constraints so that the
# shadow price of each direction can be read off. That price is the
# congestion rent: the dollars per hour the objective would fall if that
# one wire were one MW thicker.
#
# Outputs per arm <A>:
#   draws_<A>.csv            one row per solve
#   util_by_line_<A>.csv     16 x N   |flow| / rating
#   flow_by_line_<A>.csv     16 x N   signed MW
#   mu_by_line_<A>.csv       16 x N   $/MWh shadow price of the rating
#   lmp_by_bus_<A>.csv       11 x N   $/MWh nodal price
#   shed_by_bus_<A>.csv      11 x N   MW of load dropped
#   demand_by_bus_<A>.csv    11 x N   MW of load offered
#   genbus_by_hour_<A>.csv   11 x N   MW produced at each bus
# =====================================================================

using Random, Statistics, Printf, CSV, DataFrames, JuMP, HiGHS, LinearAlgebra

include(joinpath(@__DIR__, "case.jl"))

const OUT      = outdir()          # out/ for the base run, out_<tag>/ otherwise
const VOLL_    = 10_000.0
const BASEMVA_ = 100.0
const N_SCEN   = 10_000
const SEED     = 1

case = load_case()
D    = hourly_demand(case)
nbus = case.nbus; nlin = length(case.rate); ngen = length(case.pmax); nh = size(D, 2)

# ---------------------------------------------------------------------
# the three demand inputs
# ---------------------------------------------------------------------
mu  = [mean(D[i, :]) for i in 1:nbus]
sig = [std(D[i, :])  for i in 1:nbus]
Cov = cov(D, dims = 2)
E   = eigen(Symmetric(Matrix(Cov)))
L   = E.vectors * Diagonal(sqrt.(max.(E.values, 0.0)))   # L*L' == Cov

rng = MersenneTwister(SEED)
Dfit = zeros(nbus, N_SCEN)
for s in 1:N_SCEN, i in 1:nbus
    Dfit[i, s] = max(0.0, mu[i] + sig[i] * randn(rng))
end
rng2 = MersenneTwister(SEED)
Dcor = zeros(nbus, N_SCEN)
z = zeros(nbus)
for s in 1:N_SCEN
    for i in 1:nbus; z[i] = randn(rng2); end
    v = mu .+ L * z
    Dcor[:, s] = max.(0.0, v)
end

ARMS = [("actual", D), ("fitted", Dfit), ("corr", Dcor)]

# ---------------------------------------------------------------------
# the model -- built once
# ---------------------------------------------------------------------
m = Model(HiGHS.Optimizer); set_silent(m)
@variable(m, P[1:ngen] >= 0)
@variable(m, theta[1:nbus])
@variable(m, S[1:nbus] >= 0)
@expression(m, F[l in 1:nlin],
    BASEMVA_ * case.sus[l] * (theta[case.fbus[l]] - theta[case.tbus[l]]))
@constraint(m, cap[g in 1:ngen], P[g] <= case.pmax[g])
@constraint(m, theta[case.slack] == 0)
@constraint(m, lim_p[l in 1:nlin],  F[l] <= case.rate[l])
@constraint(m, lim_n[l in 1:nlin], -F[l] <= case.rate[l])
@constraint(m, bal[i in 1:nbus],
    sum(P[g] for g in 1:ngen if case.gen_bus[g] == i; init = 0.0) + S[i]
    - sum(F[l] for l in 1:nlin if case.fbus[l] == i; init = 0.0)
    + sum(F[l] for l in 1:nlin if case.tbus[l] == i; init = 0.0) == 0.0)
@constraint(m, shedcap[i in 1:nbus], S[i] <= 0.0)
@objective(m, Min, sum(case.cost[g] * P[g] for g in 1:ngen) + VOLL_ * sum(S))

println("="^80)
@printf("ONE LP, THREE DEMAND INPUTS | %d buses  %d lines  %d generators\n", nbus, nlin, ngen)
@printf("fleet capacity %.1f MW   VOLL \$%.0f/MWh\n", sum(case.pmax), VOLL_)
println("="^80)

wide(key, vals, M, pfx) = begin
    df = DataFrame(key => vals)
    for j in 1:size(M, 2); df[!, Symbol("$(pfx)$(j)")] = M[:, j]; end
    df
end

for (tag, Dm) in ARMS
    N = size(Dm, 2)
    rows = DataFrame(draw = Int[], total_mw = Float64[], ens_mw = Float64[],
                     cost_usd = Float64[], fuel_usd = Float64[],
                     buses_shed = Int[], lines_atlim = Int[],
                     max_line_util = Float64[], congestion_rent_usd = Float64[])
    U = zeros(nlin, N); FL = zeros(nlin, N); MU = zeros(nlin, N)
    SH = zeros(nbus, N); GB = zeros(nbus, N); LMP = zeros(nbus, N)
    t0 = time()
    for s in 1:N
        d = view(Dm, :, s)
        for i in 1:nbus
            set_normalized_rhs(bal[i], d[i]); set_normalized_rhs(shedcap[i], d[i])
        end
        optimize!(m)
        termination_status(m) in (MOI.OPTIMAL, MOI.LOCALLY_SOLVED) ||
            error("$tag draw $s: $(termination_status(m))")
        fl  = [value(F[l]) for l in 1:nlin]
        u   = [abs(fl[l]) / case.rate[l] for l in 1:nlin]
        sh  = value.(S)
        pg  = value.(P)
        # shadow price of the rating, positive when the wire binds either way
        mul = [abs(dual(lim_p[l])) + abs(dual(lim_n[l])) for l in 1:nlin]
        lmp = [dual(bal[i]) for i in 1:nbus]
        gb  = zeros(nbus); for g in 1:ngen; gb[case.gen_bus[g]] += pg[g]; end
        U[:, s] = u; FL[:, s] = fl; MU[:, s] = mul
        SH[:, s] = sh; GB[:, s] = gb; LMP[:, s] = lmp
        fuel = sum(case.cost[g] * pg[g] for g in 1:ngen)
        push!(rows, (s, sum(d), sum(sh), objective_value(m), fuel,
                     count(>(1e-4), sh), count(>=(0.999), u), maximum(u),
                     sum(mul[l] * case.rate[l] for l in 1:nlin)))
    end
    @printf("\n%-7s %6d solves in %.1f s\n", tag, N, time() - t0)
    CSV.write(joinpath(OUT, "draws_$(tag).csv"), rows)
    lmeta = DataFrame(line = 1:nlin,
                      from = [case.bus_name[case.fbus[l]] for l in 1:nlin],
                      to   = [case.bus_name[case.tbus[l]] for l in 1:nlin],
                      rate_mw = case.rate)
    for (M, nm) in ((U, "util"), (FL, "flow"), (MU, "mu"))
        df = copy(lmeta)
        for s in 1:N; df[!, Symbol("d$(s)")] = M[:, s]; end
        CSV.write(joinpath(OUT, "$(nm)_by_line_$(tag).csv"), df)
    end
    CSV.write(joinpath(OUT, "shed_by_bus_$(tag).csv"),   wide("bus", case.bus_name, SH,  "d"))
    CSV.write(joinpath(OUT, "demand_by_bus_$(tag).csv"), wide("bus", case.bus_name, Matrix(Dm), "d"))
    CSV.write(joinpath(OUT, "genbus_by_hour_$(tag).csv"),wide("bus", case.bus_name, GB,  "d"))
    CSV.write(joinpath(OUT, "lmp_by_bus_$(tag).csv"),    wide("bus", case.bus_name, LMP, "d"))

    @printf("  island load   mean %7.2f  sd %6.2f  max %7.2f\n",
            mean(rows.total_mw), std(rows.total_mw), maximum(rows.total_mw))
    @printf("  unserved      %d / %d draws (%.3f%%), %.3f MW total\n",
            count(>(1e-4), rows.ens_mw), N, 100*count(>(1e-4), rows.ens_mw)/N, sum(rows.ens_mw))
    @printf("  any wire pinned  %.2f%% of draws\n", 100*count(>(0), rows.lines_atlim)/N)
    @printf("  congestion rent  mean \$%.0f/h   max \$%.0f/h\n",
            mean(rows.congestion_rent_usd), maximum(rows.congestion_rent_usd))
end

# fleet + network reference tables, written once
gen = DataFrame(name = case.gen_name, bus = [case.bus_name[b] for b in case.gen_bus],
                tech = case.gen_tech, pmax_mw = case.pmax,
                cost_usd_mwh = case.cost)
CSV.write(joinpath(OUT, "fleet.csv"), gen)
net = DataFrame(line = 1:nlin,
                from = [case.bus_name[case.fbus[l]] for l in 1:nlin],
                to   = [case.bus_name[case.tbus[l]] for l in 1:nlin],
                susceptance_pu = case.sus, rate_mw = case.rate)
CSV.write(joinpath(OUT, "network.csv"), net)
CSV.write(joinpath(OUT, "bus_fit.csv"),
          DataFrame(bus = case.bus_name, mu_mw = mu, sigma_mw = sig,
                    cv = [mu[i] > 0 ? sig[i]/mu[i] : 0.0 for i in 1:nbus]))
CSV.write(joinpath(OUT, "bus_corr.csv"),
          DataFrame(hcat(case.bus_name, cor(D, dims = 2)),
                    vcat(:bus, Symbol.(case.bus_name))))
println("\nwrote -> ", OUT)
