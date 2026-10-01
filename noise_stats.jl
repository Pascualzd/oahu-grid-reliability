# =====================================================================
# noise_stats.jl -- what the local wiggle does to the demand inputs.
#
# Regenerates, for each NOISE level, exactly the demand matrices contingency.jl
# solves (same seeds), and reports: island mean and spread, the average and the
# largest correlation between two substations, and the rank of the covariance
# matrix. Writes out/noise_stats.csv. Run with no environment variables.
# =====================================================================
using Random, Statistics, Printf, CSV, DataFrames, LinearAlgebra
include(joinpath(@__DIR__, "case.jl"))

case = load_case(); D0 = hourly_demand(case); nbus = case.nbus
mu  = [mean(D0[i, :]) for i in 1:nbus]; sig = [std(D0[i, :]) for i in 1:nbus]
E   = eigen(Symmetric(Matrix(cov(D0, dims = 2))))
L   = E.vectors * Diagonal(sqrt.(max.(E.values, 0.0)))
rng = MersenneTwister(1); C0 = zeros(nbus, 10_000); z = zeros(nbus)
for s in 1:10_000
    for i in 1:nbus; z[i] = randn(rng); end
    C0[:, s] = max.(0.0, mu .+ L * z)
end
load = [i for i in 1:nbus if sig[i] > 0]                 # Kalaeloa has no load
names = case.bus_name
iw, ik = findfirst(==("Wahiawa"), names), findfirst(==("Koolau"), names)

function noisy(Dm, f, seed)
    f == 0 && return Dm
    r = MersenneTwister(seed); out = similar(Dm)
    for s in axes(Dm, 2), i in axes(Dm, 1)
        out[i, s] = max(0.0, Dm[i, s] + f * sig[i] * randn(r))
    end
    out
end

rows = DataFrame(noise = Float64[], arm = String[], island_mean_mw = Float64[],
                 island_sd_mw = Float64[], mean_corr = Float64[], min_corr = Float64[],
                 corr_wahiawa_koolau = Float64[], rank = Int[], smallest_eig_mw2 = Float64[])
for f in (0.0, 0.10, 0.25, 0.50)
    for (arm, Dm) in (("actual", noisy(D0, f, 2)), ("random", noisy(C0, f, 3)))
        X = Dm[load, :]; tot = vec(sum(Dm, dims = 1))
        R = cor(X, dims = 2); off = [R[a, b] for a in axes(R, 1), b in axes(R, 2) if a < b]
        w = eigvals(Symmetric(cov(X, dims = 2)))
        rk = count(>(1e-6 * maximum(w)), w)      # below this is rounding and clipping at zero
        push!(rows, (f, arm, mean(tot), std(tot), mean(off), minimum(off),
                     cor(Dm[iw, :], Dm[ik, :]), rk, minimum(w)))
        @printf("f=%.2f %-6s island sd %6.1f  mean corr %.3f  Wahiawa-Koolau %.3f  rank %d  smallest eig %.3g\n",
                f, arm, std(tot), mean(off), cor(Dm[iw, :], Dm[ik, :]), rk, minimum(w))
    end
end
CSV.write(joinpath(@__DIR__, "out", "noise_stats.csv"), rows)
