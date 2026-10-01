# =====================================================================
# redispatch.jl -- what the optimiser does when one of the two export lines
# east of Kalaeloa (Kalaeloa-Ewa Nui, CEIP-Ewa Nui) is lost.
#
# For every recorded hour it solves the network with all lines in service
# and with the one line out, and, in the hours where the other export line is
# at its rating, records: output by power-plant substation in both cases,
# the extra running cost, and the island demand. Writes out/redispatch.csv.
# =====================================================================
using Statistics, Printf, CSV, DataFrames, JuMP, HiGHS
include(joinpath(@__DIR__, "case.jl"))

const OUT = outdir()
case = load_case(); D = hourly_demand(case)
nbus = case.nbus; nlin = length(case.rate); ngen = length(case.pmax)
ncir = Int.(CSV.read(joinpath(DATA, "network_branches.csv"), DataFrame).circuits)
lname = ["$(case.bus_name[case.fbus[l]])-$(case.bus_name[case.tbus[l]])" for l in 1:nlin]
PLANTS = ("Kahe", "Waiau", "Kalaeloa", "Wahiawa")

function build(out)
    k = copy(ncir); for l in out; k[l] -= 1; end
    frac = [k[l] / ncir[l] for l in 1:nlin]; sus = case.sus .* frac; rate = case.rate .* frac
    m = Model(HiGHS.Optimizer); set_silent(m)
    @variable(m, P[1:ngen] >= 0); @variable(m, th[1:nbus]); @variable(m, S[1:nbus] >= 0)
    @expression(m, F[l in 1:nlin], BASE_MVA * sus[l] * (th[case.fbus[l]] - th[case.tbus[l]]))
    @constraint(m, [g in 1:ngen], P[g] <= case.pmax[g]); @constraint(m, th[case.slack] == 0)
    @constraint(m, [l in 1:nlin], -rate[l] <= F[l] <= rate[l])
    @constraint(m, bal[i in 1:nbus],
        sum(P[g] for g in 1:ngen if case.gen_bus[g] == i; init = 0.0) + S[i]
        - sum(F[l] for l in 1:nlin if case.fbus[l] == i; init = 0.0)
        + sum(F[l] for l in 1:nlin if case.tbus[l] == i; init = 0.0) == 0.0)
    @constraint(m, sc[i in 1:nbus], S[i] <= 0.0)
    @objective(m, Min, sum(case.cost[g] * P[g] for g in 1:ngen) + VOLL * sum(S))
    (m = m, bal = bal, sc = sc, P = P, F = F, rate = rate)
end
plant_mw(M) = Dict(b => sum(value(M.P[g]) for g in 1:ngen
                            if case.bus_name[case.gen_bus[g]] == b; init = 0.0) for b in PLANTS)

rows = DataFrame(line_lost = String[], line_full = String[], hours_full = Int[],
                 extra_cost_usd_per_full_hour = Float64[],
                 island_mw_min_when_full = Float64[], island_mw_max_when_not_full = Float64[])
for b in PLANTS
    rows[!, Symbol("$(b)_mw_n0")] = Float64[]; rows[!, Symbol("$(b)_mw_n1")] = Float64[]
end
idx(nm) = findfirst(==(nm), lname)
for (lost, full) in (("Kalaeloa-Ewa Nui", "CEIP-Ewa Nui"), ("CEIP-Ewa Nui", "Kalaeloa-Ewa Nui"))
    l, w = idx(lost), idx(full)
    A = build(Int[]); B = build([l])
    n = 0; cost = 0.0; tfull = Float64[]; tnot = Float64[]
    s0 = Dict(b => 0.0 for b in PLANTS); s1 = copy(s0)
    for h in 1:size(D, 2)
        for M in (A, B)
            for i in 1:nbus
                set_normalized_rhs(M.bal[i], D[i, h]); set_normalized_rhs(M.sc[i], D[i, h])
            end
            optimize!(M.m); termination_status(M.m) == MOI.OPTIMAL || error("not optimal")
        end
        if abs(value(B.F[w])) >= 0.999 * B.rate[w]
            n += 1; cost += objective_value(B.m) - objective_value(A.m); push!(tfull, sum(D[:, h]))
            g0 = plant_mw(A); g1 = plant_mw(B)
            for b in PLANTS; s0[b] += g0[b]; s1[b] += g1[b]; end
        else
            push!(tnot, sum(D[:, h]))
        end
    end
    r = Any[lost, full, n, cost / n, minimum(tfull), maximum(tnot)]
    for b in PLANTS; push!(r, s0[b] / n); push!(r, s1[b] / n); end
    push!(rows, r)
    @printf("%s lost: %s full in %d h, +\$%.0f per full hour; Kahe %.1f -> %.1f, Waiau %.1f -> %.1f, Kalaeloa %.1f -> %.1f MW\n",
            lost, full, n, cost / n, s0["Kahe"] / n, s1["Kahe"] / n, s0["Waiau"] / n, s1["Waiau"] / n,
            s0["Kalaeloa"] / n, s1["Kalaeloa"] / n)
    @printf("   island demand: lowest when full %.0f MW, highest when not full %.0f MW\n", minimum(tfull), maximum(tnot))
end
CSV.write(joinpath(OUT, "redispatch.csv"), rows)
