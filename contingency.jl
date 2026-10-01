# =====================================================================
# contingency.jl -- what happens when a line is lost.
#
# Hawaiian Electric's planning rule, as quoted by the Hawai'i PUC (D&O 23747,
# Docket 03-0417, 2007, p. 6): "no transmission component shall exceed its
# emergency rating with one generating unit on overhaul, one transmission line
# out for maintenance and loss of a second transmission line." That is a
# two-line (N-2) test. This script asks the same question of the model.
#
# For every outage the SAME dispatch LP is re-solved on the damaged network,
# for every hour of the recorded year and every one of the 10,000 random draws.
# Losing one of n parallel circuits leaves (n-1)/n of the corridor's rating and
# susceptance; losing the last one removes the corridor.
#
#   N-0   nothing out
#   N-1   each circuit out, one at a time        (16 distinct cases)
#   N-2   every pair of circuits out             (128 distinct cases)
#
# The optimiser re-dispatches the generators after the outage. Demand is shed
# only if no re-dispatch can serve it. Normal ratings are used throughout: no
# emergency ratings are published, so the N-2 results are CONSERVATIVE (a real
# line may carry more than its normal rating for a few hours).
#
# The 46 kV sub-transmission network is NOT modelled. On O'ahu it can move some
# load between neighbouring 138 kV substations (e.g. Pukele <-> Archer/Kamoku,
# built after D&O 23747), so an area that "loses power" here would in reality
# lose part of it, or lose it only until switching is done.
#
# Outputs (in out/ or out_<tag>/):
#   contingency.csv          one row per (outage, input): hours short, MWh short
#   contingency_lines.csv    ... and per line: highest loading, hours at the limit
#   contingency_buses.csv    ... and per substation: hours short, MWh short
# =====================================================================
using Random, Statistics, Printf, CSV, DataFrames, JuMP, HiGHS, LinearAlgebra
include(joinpath(@__DIR__, "case.jl"))

const OUT    = outdir()
const N_SCEN = 10_000
const SEED   = 1

case = load_case()
D    = hourly_demand(case)
nbus = case.nbus; nlin = length(case.rate); ngen = length(case.pmax)
br   = CSV.read(joinpath(DATA, "network_branches.csv"), DataFrame)
ncir = Int.(br.circuits)
lname = ["$(case.bus_name[case.fbus[l]])-$(case.bus_name[case.tbus[l]])" for l in 1:nlin]

# the correlated random draws, regenerated exactly as in run_all.jl
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

function build(out::Vector{Int})
    k = copy(ncir); for l in out; k[l] -= 1; end
    frac = [k[l] / ncir[l] for l in 1:nlin]
    sus = case.sus .* frac; rate = case.rate .* frac
    m = Model(HiGHS.Optimizer); set_silent(m)
    @variable(m, P[1:ngen] >= 0); @variable(m, th[1:nbus]); @variable(m, S[1:nbus] >= 0)
    @expression(m, F[l in 1:nlin], BASE_MVA * sus[l] * (th[case.fbus[l]] - th[case.tbus[l]]))
    @constraint(m, [g in 1:ngen], P[g] <= case.pmax[g])
    @constraint(m, th[case.slack] == 0)
    # an isolated bus has a free angle; pin every bus whose lines are all gone
    for i in 1:nbus
        if all(sus[l] == 0 for l in 1:nlin if case.fbus[l] == i || case.tbus[l] == i)
            i != case.slack && @constraint(m, th[i] == 0)
        end
    end
    @constraint(m, [l in 1:nlin], -rate[l] <= F[l] <= rate[l])
    @constraint(m, bal[i in 1:nbus],
        sum(P[g] for g in 1:ngen if case.gen_bus[g] == i; init = 0.0) + S[i]
        - sum(F[l] for l in 1:nlin if case.fbus[l] == i; init = 0.0)
        + sum(F[l] for l in 1:nlin if case.tbus[l] == i; init = 0.0) == 0.0)
    @constraint(m, sc[i in 1:nbus], S[i] <= 0.0)
    @objective(m, Min, sum(case.cost[g] * P[g] for g in 1:ngen) + VOLL * sum(S))
    return m, bal, sc, S, F, rate
end

function run(out::Vector{Int}, Dm)
    m, bal, sc, S, F, rate = build(out)
    n = size(Dm, 2)
    shed = zeros(nbus); bhours = zeros(Int, nbus); bworst = zeros(nbus)
    nshort = 0; worst = 0.0; pinned = zeros(Int, nlin); maxu = zeros(nlin)
    for s in 1:n
        for i in 1:nbus
            set_normalized_rhs(bal[i], Dm[i, s]); set_normalized_rhs(sc[i], Dm[i, s])
        end
        optimize!(m)
        termination_status(m) == MOI.OPTIMAL || error("not optimal: $out, $s")
        sh = value.(S); e = sum(sh)
        shed .+= sh
        for i in 1:nbus
            if sh[i] > 1e-4; bhours[i] += 1; bworst[i] = max(bworst[i], sh[i]); end
        end
        if e > 1e-4; nshort += 1; worst = max(worst, e); end
        for l in 1:nlin
            rate[l] > 0 || continue
            u = abs(value(F[l])) / rate[l]
            maxu[l] = max(maxu[l], u)
            u >= 0.999 && (pinned[l] += 1)
        end
    end
    (n = n, nshort = nshort, mwh = sum(shed), worst = worst, shed = shed,
     bhours = bhours, bworst = bworst, pinned = pinned, maxu = maxu, rate = rate)
end

rows  = DataFrame(kind = String[], outage = String[], arm = String[], n = Int[],
                  hours_short = Int[], mwh_short = Float64[], worst_mw = Float64[],
                  areas_short = String[], lines_at_limit = String[])
lrows = DataFrame(kind = String[], outage = String[], arm = String[], line = String[],
                  rate_left_mw = Float64[], max_loading = Float64[], hours_at_limit = Int[])
brows = DataFrame(kind = String[], outage = String[], arm = String[], bus = String[],
                  hours_short = Int[], mwh_short = Float64[], worst_mw = Float64[])
function record!(kind, label, arm, r)
    bs = join(["$(case.bus_name[i]) $(r.bhours[i])" for i in sortperm(-r.bhours) if r.bhours[i] > 0], "; ")
    lp = join(["$(lname[l]) $(r.pinned[l])" for l in sortperm(-r.pinned) if r.pinned[l] > 0], "; ")
    push!(rows, (kind, label, arm, r.n, r.nshort, r.mwh, r.worst, bs, lp))
    for l in 1:nlin
        push!(lrows, (kind, label, arm, lname[l], r.rate[l], r.maxu[l], r.pinned[l]))
    end
    for i in 1:nbus
        push!(brows, (kind, label, arm, case.bus_name[i], r.bhours[i], r.shed[i], r.bworst[i]))
    end
end

println("="^80); println("CONTINGENCIES  (run: $(run_tag()))"); println("="^80)
t0 = time()
base_a = run(Int[], D); base_c = run(Int[], Dcor)
record!("N-0", "none", "actual", base_a); record!("N-0", "none", "random", base_c)
@printf("N-0: short hours actual %d, random %d\n", base_a.nshort, base_c.nshort)

for l in 1:nlin
    lab = ncir[l] > 1 ? "one of $(ncir[l]) $(lname[l])" : lname[l]
    ra = run([l], D); rc = run([l], Dcor)
    record!("N-1", lab, "actual", ra); record!("N-1", lab, "random", rc)
    @printf("  N-1 %-30s actual %4d h %9.1f MWh | random %5d  (%.0fs)\n",
            lab, ra.nshort, ra.mwh, rc.nshort, time() - t0); flush(stdout)
end

println("\nN-2 (printed only when some demand is lost):")
circuits = [(l, c) for l in 1:nlin for c in 1:ncir[l]]
seen2 = Set{Vector{Int}}()
for i in 1:length(circuits), j in i+1:length(circuits)
    li, lj = circuits[i][1], circuits[j][1]
    key = sort([li, lj]); key in seen2 && continue; push!(seen2, key)
    lab = li == lj ? "two of $(ncir[li]) $(lname[li])" : "$(lname[li]) + $(lname[lj])"
    ra = run(key, D); rc = run(key, Dcor)
    record!("N-2", lab, "actual", ra); record!("N-2", lab, "random", rc)
    if ra.nshort > 0 || rc.nshort > 0
        @printf("  N-2 %-44s actual %4d h %9.1f MWh | random %5d  (%.0fs)\n",
                lab, ra.nshort, ra.mwh, rc.nshort, time() - t0); flush(stdout)
    end
end
CSV.write(joinpath(OUT, "contingency.csv"), rows)
CSV.write(joinpath(OUT, "contingency_lines.csv"), lrows)
CSV.write(joinpath(OUT, "contingency_buses.csv"), brows)
@printf("\n%d outage cases (%d rows) in %.0f s -> %s\n", length(seen2) + nlin + 1,
        nrow(rows), time() - t0, OUT)
