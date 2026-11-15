"""Every plan is optimal, proved two ways that do not rest on the solver's word (O35).

1. A certificate computed here from the solver's primal and dual values (`engine.certificate`): the plan is feasible,
   the duals are feasible, and the two objectives meet. That is the definition of an LP optimum.
2. The same LP solved again by a different algorithm (HiGHS interior point; the plans use dual simplex): the same
   objective.

Checked on every solve of every built-in scenario, including each stage of a priority order and the tie-break stage."""
from dataclasses import replace

import pytest
from scipy.optimize import linprog as real_linprog

from redwheel import engine, scenarios as sc

CASES = [sc.CASE_A, sc.CASE_B, sc.CASE_E1, sc.CASE_E2, sc.CASE_E3, sc.CASE_E4, sc.CASE_E5, sc.CASE_P1,
         replace(sc.CASE_B, key="B+E3", changes=sc.CASE_E3.changes, parent="B")]


@pytest.fixture(scope="module")
def solves():
    log = {}
    key = {"now": None}

    def checked(c, **kw):
        sol = real_linprog(c, **kw)
        cert = engine.certificate(c, kw["A_ub"], kw["b_ub"], kw["A_eq"], kw["b_eq"], kw["bounds"], sol)
        ipm = real_linprog(c, **{**kw, "method": "highs-ipm"})
        cert["ipm_solved"] = ipm.status == 0
        cert["ipm_diff"] = abs(ipm.fun - sol.fun) / max(1.0, abs(sol.fun))
        log.setdefault(key["now"], []).append(cert)
        return sol

    mp = pytest.MonkeyPatch()
    mp.setattr(engine, "linprog", checked)
    try:
        for case in CASES:
            key["now"] = case.key
            sc.run_case(case)
    finally:
        mp.undo()
    return log


@pytest.mark.parametrize("key", [c.key for c in CASES])
def test_every_solve_is_certified_optimal(solves, key):
    for cert in solves[key]:
        assert cert["primal"] < 1e-6, cert                    # the plan meets every row and bound
        assert cert["dual"] < 1e-6, cert                      # the duals are feasible
        assert cert["gap"] < 1e-9, cert                       # and the two objectives meet


@pytest.mark.parametrize("key", [c.key for c in CASES])
def test_a_second_algorithm_finds_the_same_optimum(solves, key):
    for cert in solves[key]:
        assert cert["ipm_solved"] and cert["ipm_diff"] < 1e-7, cert


def test_the_certificate_fails_a_plan_that_is_not_optimal():
    """The certificate is not a formality: on a tiny LP, a feasible point that is not the optimum shows a gap, and a
    point that breaks a row or a bound shows the violation."""
    import numpy as np
    from types import SimpleNamespace
    c = np.array([1.0, 1.0])
    A_ub, b_ub = np.array([[-1.0, -1.0]]), np.array([-2.0])           # x + y >= 2
    A_eq, b_eq = np.zeros((0, 2)), np.zeros(0)
    bounds = np.array([[0.0, np.inf], [0.0, np.inf]])
    sol = real_linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    assert engine.certificate(c, A_ub, b_ub, A_eq, b_eq, bounds, sol)["gap"] < 1e-12
    worse = SimpleNamespace(x=np.array([2.0, 1.0]), ineqlin=sol.ineqlin, eqlin=sol.eqlin, lower=sol.lower, upper=sol.upper)
    assert engine.certificate(c, A_ub, b_ub, A_eq, b_eq, bounds, worse)["gap"] > 0.1
    short = SimpleNamespace(x=np.array([0.5, 0.5]), ineqlin=sol.ineqlin, eqlin=sol.eqlin, lower=sol.lower, upper=sol.upper)
    assert engine.certificate(c, A_ub, b_ub, A_eq, b_eq, bounds, short)["primal"] == pytest.approx(1.0)   # x + y = 1 < 2
    below = SimpleNamespace(x=np.array([3.0, -1.0]), ineqlin=sol.ineqlin, eqlin=sol.eqlin, lower=sol.lower, upper=sol.upper)
    assert engine.certificate(c, A_ub, b_ub, A_eq, b_eq, bounds, below)["primal"] == pytest.approx(1.0)   # y below its bound
