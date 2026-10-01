# =====================================================================
# stress.jl -- turn the demand dial up and watch what gives out first.
#
# The same LP, the same 8,760 recorded hours and the same 10,000 random draws.
# The only change is a growth factor g applied to every substation in every
# hour: demand x 1.0, 1.1, ..., 2.0.
#
# Two things can run out as g rises:
#   the GENERATORS  -- the island needs more MW than the 1,508 MW fleet has
#   the WIRES       -- the fleet has the MW, but a line cannot carry them
# To tell them apart, every case is solved twice:
#   network      the full model, line limits on
#   copper plate the same model with every line limit removed; any shortage
#                here is a shortage of generation, not of wires
# A shortage that appears in "network" but not in "copper plate" is caused by
# the wires. Only those are credited to an area in stress_by_bus.csv (when the
# generators are short, WHICH area the LP drops is arbitrary: every MWh of
# unserved demand has the same $10,000 price).
#
# Outputs (in out/ or out_<tag>/): stress_system.csv, stress_by_bus.csv,
# stress_by_line.csv
# =====================================================================
using Random, Statistics, Printf, CSV, DataFrames, JuMP, HiGHS, LinearAlgebra
include(joinpath(@__DIR__, "case.jl"))

const OUT    = outdir()
const N_SCEN = 10_000
const SEED   = 1
const LEVELS = round.(collect(1.0:0.1:2.0), digits = 1)

case = load_case()
D    = hourly_demand(case)
nbus = case.nbus; nlin = length(case.rate); ngen = length(case.pmax)

mu  = [mean(D[i, :]) for i in 1:nbus]
Cov = cov(D, dims = 2); E = eigen(Symmetric(Matrix(Cov)))
L   = E.vectors * Diagonal(sqrt.(max.(E.values, 0.0)))
rng = MersenneTwister(SEED); Dcor = zeros(nbus, N_SCEN); z = zeros(nbus)
for s in 1:N_SCEN
    for i in 1:nbus; z[i] = randn(rng); end
    Dcor[:, s] = max.(0.0, mu .+ L * z)
end
# optional local wiggle (NOISE > 0): the same draws as above, plus independent noise
sig  = [std(D[i, :]) for i in 1:nbus]
D    = add_local_noise(D, sig; seed = 2)
Dcor = add_local_noise(Dcor, sig; seed = 3)

function build(limits::Bool)
    m = Model(HiGHS.Optimizer); set_silent(m)
    @variable(m, P[1:ngen] >= 0); @variable(m, th[1:nbus]); @variable(m, S[1:nbus] >= 0)
    @expression(m, F[l in 1:nlin], BASE_MVA*case.sus[l]*(th[case.fbus[l]] - th[case.tbus[l]]))
    @constraint(m, [g in 1:ngen], P[g] <= case.pmax[g])
    @constraint(m, th[case.slack] == 0)
    limits && @constraint(m, [l in 1:nlin], -case.rate[l] <= F[l] <= case.rate[l])
    @constraint(m, bal[i in 1:nbus],
        sum(P[g] for g in 1:ngen if case.gen_bus[g]==i; init=0.0) + S[i]
        - sum(F[l] for l in 1:nlin if case.fbus[l]==i; init=0.0)
        + sum(F[l] for l in 1:nlin if case.tbus[l]==i; init=0.0) == 0.0)
    @constraint(m, sc[i in 1:nbus], S[i] <= 0.0)
    @objective(m, Min, sum(case.cost[g]*P[g] for g in 1:ngen) + VOLL*sum(S))
    (m = m, bal = bal, sc = sc, S = S, F = F)
end
net = build(true); cu = build(false)

function solve!(M, d)
    for i in 1:nbus
        set_normalized_rhs(M.bal[i], d[i]); set_normalized_rhs(M.sc[i], d[i])
    end
    optimize!(M.m)
    termination_status(M.m) == MOI.OPTIMAL || error("not optimal")
end

srow = DataFrame(arm = String[], level = Float64[], n = Int[], mean_load_mw = Float64[],
                 peak_load_mw = Float64[],
                 pct_short_network = Float64[], pct_short_generation = Float64[],
                 pct_short_wires = Float64[], mwh_short_network = Float64[],
                 mwh_short_generation = Float64[], pct_any_line_at_limit = Float64[])
brow = DataFrame(arm = String[], level = Float64[], bus = String[],
                 pct_short_wires = Float64[], mwh_short_wires = Float64[])
lrow = DataFrame(arm = String[], level = Float64[], line = String[],
                 max_loading = Float64[], pct_at_limit = Float64[])

println("="^88)
println("GROWTH LADDER  (run: $(run_tag()))   fleet $(round(sum(case.pmax), digits=1)) MW")
println("="^88)
@printf("%-7s %5s %9s %9s | %8s %8s %8s | %s\n", "input", "g", "mean MW", "peak MW",
        "short %", "gen %", "wires %", "areas short because of the wires")
for (arm, Dm) in (("actual", D), ("random", Dcor))
    n = size(Dm, 2)
    for g in LEVELS
        sn = 0; sg = 0; sw = 0; en = 0.0; eg = 0.0; anyl = 0
        bs = zeros(Int, nbus); be = zeros(nbus); mx = zeros(nlin); pin = zeros(Int, nlin)
        for s in 1:n
            d = g .* Dm[:, s]
            solve!(net, d); shn = value.(net.S)
            u = [abs(value(net.F[l])) / case.rate[l] for l in 1:nlin]
            solve!(cu, d);  shc = value.(cu.S)
            a = sum(shn) > 1e-4; b = sum(shc) > 1e-4
            sn += a; sg += b; en += sum(shn); eg += sum(shc)
            mx .= max.(mx, u); pin .+= (u .>= 0.999); anyl += any(u .>= 0.999)
            if a && !b                              # the wires, not the generators
                sw += 1
                for i in 1:nbus
                    shn[i] > 1e-4 && (bs[i] += 1; be[i] += shn[i])
                end
            end
        end
        tot = vec(sum(g .* Dm, dims = 1))
        push!(srow, (arm, g, n, mean(tot), maximum(tot), 100sn/n, 100sg/n, 100sw/n,
                     en, eg, 100anyl/n))
        for i in 1:nbus
            push!(brow, (arm, g, case.bus_name[i], 100bs[i]/n, be[i]))
        end
        for l in 1:nlin
            push!(lrow, (arm, g, "$(case.bus_name[case.fbus[l]])-$(case.bus_name[case.tbus[l]])",
                         mx[l], 100pin[l]/n))
        end
        dark = [(case.bus_name[i], 100bs[i]/n) for i in sortperm(-bs) if bs[i] > 0]
        @printf("%-7s %5.1f %9.1f %9.1f | %8.2f %8.2f %8.2f | %s\n", arm, g, mean(tot),
                maximum(tot), 100sn/n, 100sg/n, 100sw/n,
                isempty(dark) ? "none" : join([@sprintf("%s %.2f%%", x[1], x[2]) for x in dark], ", "))
        flush(stdout)
    end
end
CSV.write(joinpath(OUT, "stress_system.csv"), srow)
CSV.write(joinpath(OUT, "stress_by_bus.csv"), brow)
CSV.write(joinpath(OUT, "stress_by_line.csv"), lrow)

println("\nFIRST LINE TO REACH ITS LIMIT, by growth factor:")
for arm in ("actual", "random")
    sub = lrow[(lrow.arm .== arm) .& (lrow.pct_at_limit .> 0), :]
    if nrow(sub) == 0
        println("  $arm: none up to $(maximum(LEVELS))x")
    else
        g1 = minimum(sub.level)
        println("  $arm: at $(g1)x -> ", join(sub[sub.level .== g1, :line], ", "))
    end
end
println("wrote -> ", OUT)
