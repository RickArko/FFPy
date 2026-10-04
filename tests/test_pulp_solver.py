"""CBC → HiGHS fallback for lineup optimization on hosts without a usable CBC."""

from __future__ import annotations

from pulp import LpMaximize, LpProblem, LpVariable


def test_ensure_lineup_solver_selects_usable_backend() -> None:
    from ffpy.pulp_solver import ensure_lineup_solver

    backend = ensure_lineup_solver(force=True)
    assert backend in {"cbc", "highs"}


def test_highs_fallback_forced_when_cbc_unusable(monkeypatch) -> None:
    import pulp
    import pulp.apis.coin_api as coin_api
    import ffpy.pulp_solver as solver

    original_pulp = pulp.PULP_CBC_CMD
    original_coin = coin_api.PULP_CBC_CMD
    monkeypatch.setattr(solver, "_cbc_binary_runs", lambda _path: False)
    try:
        backend = solver.ensure_lineup_solver(force=True)
        assert backend == "highs"
        from pulp import PULP_CBC_CMD

        prob = LpProblem("probe", LpMaximize)
        x = LpVariable("x", lowBound=0, upBound=1, cat="Binary")
        prob += x
        status = prob.solve(PULP_CBC_CMD(msg=False))
        assert status == 1
        assert x.value() == 1.0
    finally:
        pulp.PULP_CBC_CMD = original_pulp
        coin_api.PULP_CBC_CMD = original_coin
        solver._CONFIGURED = False
        solver._BACKEND = "unset"
        solver.ensure_lineup_solver(force=True)
