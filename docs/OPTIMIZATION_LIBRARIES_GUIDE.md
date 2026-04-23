# Optimization Libraries Guide for Lineup Optimization

**Audience:** Data Scientists & ML Engineers
**Context:** Fantasy Football Lineup Optimization (Integer Linear Programming)

## TL;DR - Quick Comparison

| Library | Best For | Familiarity Factor | Setup Complexity |
|---------|----------|-------------------|------------------|
| **PuLP** | Quick prototypes, simple LP/ILP | 🟢 Beginner-friendly | 🟢 Minimal |
| **Pyomo** | Production systems, complex models | 🟡 Moderate | 🟡 Moderate |
| **OR-Tools** | Google-scale problems, CP/SAT | 🟡 Moderate | 🟢 Easy |
| **CVXPY** | Convex optimization, portfolio | 🟢 NumPy-like | 🟢 Easy |
| **scipy.optimize** | Simple constraints, quick hacks | 🟢 Very familiar | 🟢 Already installed |

**Our Choice:** **PuLP** - Best balance of simplicity, power, and ML engineer familiarity.

---

## Detailed Comparison

### 1. PuLP (Our Choice ✅)

**What it is:** Pure Python LP modeling library with automatic solver management

**Installation:**
```bash
# Using uv (recommended)
uv add pulp

# Using pip
pip install pulp
```

**Familiarity for Data Scientists:**
- 🟢 **Very Familiar**: Syntax similar to defining ML objectives
- 🟢 Reads like mathematical notation
- 🟢 No external solver installation required (ships with CBC solver)
- 🟢 Similar to scikit-learn's API philosophy (simple, explicit)

**Example - Fantasy Lineup Optimization:**
```python
from pulp import LpMaximize, LpProblem, LpVariable, lpSum

# Create problem (like defining a model)
prob = LpProblem("Lineup_Optimization", LpMaximize)

# Decision variables (binary: start or sit)
players = ["Mahomes", "McCaffrey", "Jefferson"]
projections = [25.5, 22.3, 18.7]
positions = ["QB", "RB", "WR"]

x = {player: LpVariable(f"x_{player}", cat="Binary") for player in players}

# Objective: Maximize projected points (like minimizing loss)
prob += lpSum([projections[i] * x[players[i]] for i in range(len(players))])

# Constraints (like regularization)
prob += lpSum([x[p] for p, pos in zip(players, positions) if pos == "QB"]) == 1  # Exactly 1 QB
prob += lpSum([x[p] for p in players]) <= 9  # Max 9 starters

# Solve (like model.fit())
prob.solve()

# Results
for player in players:
    if x[player].varValue == 1:
        print(f"Start: {player}")
```

**Pros:**
- ✅ Easiest to learn and read
- ✅ No external dependencies (solver included)
- ✅ Great error messages
- ✅ Active community
- ✅ Works out-of-the-box on Windows/Mac/Linux

**Cons:**
- ❌ Less performant than commercial solvers (fine for our use case)
- ❌ Limited to LP/ILP (no quadratic, no nonlinear)
- ❌ Fewer advanced features than Pyomo

**Best for:** Prototyping, educational use, small-to-medium problems (< 10K variables)

---

### 2. Pyomo

**What it is:** Python Optimization Modeling Objects - academic-grade optimization framework

**Installation:**
```bash
# Basic installation
uv add pyomo

# With solver (GLPK or CBC)
uv add pyomo glpk
```

The system-level `glpk` solver binary is installed separately — see *Optional: Better Solvers* below for `apt`/`brew` commands.

**Familiarity for Data Scientists:**
- 🟡 **Moderately Familiar**: More abstract, resembles TensorFlow 1.x graph building
- 🟡 Requires understanding of solver backends
- 🟡 More verbose than PuLP
- 🟢 Very powerful and flexible

**Example - Same Problem:**
```python
from pyomo.environ import ConcreteModel, Var, Objective, Constraint, Binary, maximize, SolverFactory

# Create model (like defining a computational graph)
model = ConcreteModel()

# Data
players = ["Mahomes", "McCaffrey", "Jefferson"]
projections = {players[i]: [25.5, 22.3, 18.7][i] for i in range(3)}
positions = {players[i]: ["QB", "RB", "WR"][i] for i in range(3)}

# Decision variables
model.x = Var(players, domain=Binary)

# Objective
model.obj = Objective(
    expr=sum(projections[p] * model.x[p] for p in players),
    sense=maximize
)

# Constraints
model.qb_constraint = Constraint(
    expr=sum(model.x[p] for p in players if positions[p] == "QB") == 1
)
model.total_constraint = Constraint(
    expr=sum(model.x[p] for p in players) <= 9
)

# Solve (need to specify solver)
solver = SolverFactory('glpk')
solver.solve(model)

# Results
for p in players:
    if model.x[p].value == 1:
        print(f"Start: {p}")
```

**Pros:**
- ✅ Industry-standard for academic optimization
- ✅ Supports wide range of problem types (LP, ILP, QP, NLP, MINLP)
- ✅ Can switch solvers easily (CPLEX, Gurobi, GLPK, CBC)
- ✅ Better for large-scale problems
- ✅ Excellent documentation

**Cons:**
- ❌ Steeper learning curve
- ❌ Requires separate solver installation
- ❌ More verbose syntax
- ❌ Error messages can be cryptic

**Best for:** Production systems, research, complex multi-stage optimization

---

### 3. Google OR-Tools

**What it is:** Google's optimization toolkit (focus on constraint programming)

**Installation:**
```bash
uv add ortools
```

**Familiarity for Data Scientists:**
- 🟡 **Moderately Familiar**: Similar to defining TensorFlow operations
- 🟢 Excellent documentation and examples
- 🟢 Very Pythonic API

**Example:**
```python
from ortools.linear_solver import pywraplp

# Create solver
solver = pywraplp.Solver.CreateSolver('SCIP')

# Variables
players = ["Mahomes", "McCaffrey", "Jefferson"]
projections = [25.5, 22.3, 18.7]
positions = ["QB", "RB", "WR"]

x = {p: solver.BoolVar(f'x_{p}') for p in players}

# Objective
solver.Maximize(sum(projections[i] * x[players[i]] for i in range(3)))

# Constraints
solver.Add(sum(x[p] for p, pos in zip(players, positions) if pos == "QB") == 1)
solver.Add(sum(x[p] for p in players) <= 9)

# Solve
status = solver.Solve()

if status == pywraplp.Solver.OPTIMAL:
    for p in players:
        if x[p].solution_value() == 1:
            print(f"Start: {p}")
```

**Pros:**
- ✅ Fast (Google-scale performance)
- ✅ Excellent for constraint programming (CP-SAT solver)
- ✅ Great documentation
- ✅ Supports scheduling, routing problems
- ✅ Active development

**Cons:**
- ❌ Slightly different paradigm (CP vs pure LP)
- ❌ Can be overkill for simple LP problems
- ❌ Larger dependency size

**Best for:** Large-scale problems, scheduling, routing, when you need speed

---

### 4. CVXPY

**What it is:** Convex optimization library with NumPy-like syntax

**Installation:**
```bash
uv add cvxpy
```

**Familiarity for Data Scientists:**
- 🟢 **Very Familiar**: NumPy-style syntax, feels like writing ML code
- 🟢 Great for portfolio optimization
- 🟢 Disciplined Convex Programming (prevents mistakes)

**Example:**
```python
import cvxpy as cp
import numpy as np

# Data
players = ["Mahomes", "McCaffrey", "Jefferson"]
projections = np.array([25.5, 22.3, 18.7])
positions = np.array([0, 1, 2])  # 0=QB, 1=RB, 2=WR

# Variables (binary)
x = cp.Variable(3, boolean=True)

# Objective (CVXPY minimizes by default, so negate)
objective = cp.Maximize(projections @ x)

# Constraints
constraints = [
    x[positions == 0] == 1,  # 1 QB (NumPy-style indexing!)
    cp.sum(x) <= 9,
]

# Solve
prob = cp.Problem(objective, constraints)
prob.solve()

# Results
for i, player in enumerate(players):
    if x.value[i] == 1:
        print(f"Start: {player}")
```

**Pros:**
- ✅ Most familiar to ML engineers (NumPy syntax)
- ✅ Prevents non-convex formulations (disciplined)
- ✅ Great for portfolio optimization with risk
- ✅ Can interface with multiple solvers

**Cons:**
- ❌ Limited to convex problems (ILP is not convex, requires MICP solver)
- ❌ Overkill for simple ILP
- ❌ Can be slower for pure integer problems

**Best for:** Portfolio optimization, risk-adjusted lineups, ML engineers who love NumPy

---

### 5. scipy.optimize

**What it is:** SciPy's optimization module (part of SciPy stack)

**Installation:**
```bash
# Already installed with most data science setups
uv add scipy
```

**Familiarity for Data Scientists:**
- 🟢 **Very Familiar**: Everyone knows scipy
- 🟡 Limited ILP support (only via linear_sum_assignment or MILP)
- 🟢 Good for continuous optimization

**Example (using `milp` - Mixed Integer Linear Programming):**
```python
from scipy.optimize import milp, LinearConstraint, Bounds
import numpy as np

# Data
projections = np.array([25.5, 22.3, 18.7])  # Mahomes, McCaffrey, Jefferson
positions = np.array([0, 1, 2])  # 0=QB, 1=RB, 2=WR

# Objective (scipy minimizes, so negate)
c = -projections

# Constraints: Ax <= b
# Constraint 1: QB == 1
A_eq = np.array([[1, 0, 0]])  # Only first player (QB)
b_eq = np.array([1])

# Constraint 2: Total <= 9
A_ub = np.array([[1, 1, 1]])
b_ub = np.array([9])

# Bounds: all binary
bounds = Bounds(lb=0, ub=1)

# Integer constraints
integrality = np.ones(3)  # All integer

# Solve
result = milp(c=c, constraints=LinearConstraint(A_ub, -np.inf, b_ub),
              bounds=bounds, integrality=integrality)

print(f"Optimal lineup: {result.x}")
```

**Pros:**
- ✅ Already installed in most environments
- ✅ Familiar API for scipy users
- ✅ Good for simple problems

**Cons:**
- ❌ More complex to formulate constraints (matrix form)
- ❌ Less expressive than PuLP/Pyomo
- ❌ Newer MILP interface (added in scipy 1.9)
- ❌ Not as powerful as dedicated solvers

**Best for:** Quick experiments when you already have scipy

---

## Head-to-Head: PuLP vs Pyomo

### When to Choose PuLP ✅

Use PuLP when:
- ✅ You want to get started quickly (< 5 min setup)
- ✅ Your problem is pure LP or ILP (no quadratic terms)
- ✅ You value **readability** over performance
- ✅ You're prototyping or teaching
- ✅ You have < 10,000 variables (our problem: ~50 players)
- ✅ You don't want to manage external solvers
- ✅ You're on Windows (easier setup)

### When to Choose Pyomo

Use Pyomo when:
- ✅ You need quadratic or nonlinear constraints
- ✅ You're building a production system
- ✅ You need to benchmark multiple solvers (CPLEX, Gurobi, etc.)
- ✅ Problem size > 100K variables
- ✅ You have academic solver licenses
- ✅ You need advanced features (decomposition, multi-stage)

### Side-by-Side Code Comparison

**PuLP** (More Pythonic):
```python
# Define
prob = LpProblem("Fantasy", LpMaximize)
x = {p: LpVariable(f"x_{p}", cat="Binary") for p in players}

# Objective
prob += lpSum([proj[i] * x[players[i]] for i in range(len(players))])

# Constraint
prob += lpSum([x[p] for p in qb_players]) == 1

# Solve
prob.solve()

# Result
for p in players:
    if x[p].varValue == 1:
        print(f"Start {p}")
```

**Pyomo** (More Formal):
```python
# Define
model = ConcreteModel()
model.x = Var(players, domain=Binary)

# Objective
model.obj = Objective(
    expr=sum(proj[p] * model.x[p] for p in players),
    sense=maximize
)

# Constraint
model.qb_constraint = Constraint(
    expr=sum(model.x[p] for p in qb_players) == 1
)

# Solve
solver = SolverFactory('glpk')
solver.solve(model)

# Result
for p in players:
    if model.x[p].value == 1:
        print(f"Start {p}")
```

### Performance Comparison (Fantasy Lineup)

For our use case (9 starters, ~20 bench players, ~50 free agents):

| Library | Solve Time | Setup Difficulty | Code Lines |
|---------|-----------|-----------------|------------|
| PuLP | ~10ms | Easy | ~30 |
| Pyomo | ~15ms | Moderate | ~40 |
| OR-Tools | ~5ms | Easy | ~35 |
| CVXPY | ~20ms | Easy | ~25 |
| scipy.milp | ~25ms | Hard | ~45 |

**All are fast enough** - solve time is negligible for this problem size.

---

## Recommendation for FFPy

### Why We Choose PuLP

1. **ML Engineer Familiarity**: Syntax is intuitive, reads like objective function + constraints
2. **Zero Configuration**: Ships with CBC solver, works out-of-the-box
3. **Readability**: Code is self-documenting (important for open-source)
4. **Sufficient Performance**: 10ms solve time for 50-100 players
5. **Cross-Platform**: Works seamlessly on Windows/Mac/Linux
6. **Community**: Large user base, good Stack Overflow coverage

### Migration Path

If you outgrow PuLP, it's easy to migrate:

**PuLP → Pyomo:**
- Same modeling paradigm
- Replace `LpProblem` → `ConcreteModel`
- Replace `lpSum` → `sum`
- Add solver backend

**PuLP → OR-Tools:**
- Similar syntax
- Replace `LpVariable` → `BoolVar`
- Minimal refactoring

**PuLP → CVXPY:**
- Rewrite constraints in NumPy style
- Good for risk-adjusted optimization later

---

## Advanced Topics

### Risk-Adjusted Optimization (Future)

For variance-constrained portfolios (Phase 4):

**Use CVXPY** for elegant risk modeling:
```python
import cvxpy as cp

# Maximize expected points - λ * variance
objective = cp.Maximize(expected_points @ x - lambda_risk * cp.quad_form(x, cov_matrix))
```

**Or Pyomo** with quadratic solver:
```python
# Quadratic penalty on variance
model.obj = Objective(
    expr=sum(proj[p] * model.x[p] for p in players) -
         lambda_risk * sum((model.x[p] - avg) ** 2 for p in players)
)
```

### Multi-Week Optimization

For playoff optimization across weeks 15-17:

**Pyomo** is better suited (multi-stage modeling):
```python
model.weeks = Set(initialize=[15, 16, 17])
model.x = Var(model.weeks, players, domain=Binary)

# Constraint: Can't start same player if injured
model.injury_constraint = Constraint(...)
```

---

## Installation Instructions

### For PuLP (Recommended)

**Using uv (modern, fast):**
```bash
cd FFPy
uv add pulp
```

**Using pip:**
```bash
pip install pulp
```

**Verify installation:**
```bash
python -c "import pulp; print(pulp.pulpTestAll())"
```

**No additional solver needed** - PuLP ships with COIN-OR CBC solver.

### Optional: Better Solvers

For faster solve times (optional):

**GLPK (open-source):**
```bash
# Linux / Windows (WSL)
sudo apt-get install glpk-utils

# Mac
brew install glpk
```

**CPLEX (academic license - IBM):**
- Free for academics: https://www.ibm.com/academic
- 10-100x faster than CBC
- Install + configure in PuLP:
```python
prob.solve(pulp.CPLEX_CMD())
```

**Gurobi (commercial - free academic):**
- Free for academics: https://www.gurobi.com/academia
- Fastest commercial solver
```python
prob.solve(pulp.GUROBI_CMD())
```

---

## Quick Start Example

```python
from pulp import *

# Sample data
players = ["Mahomes", "Allen", "McCaffrey", "Jefferson", "Kelce"]
positions = ["QB", "QB", "RB", "WR", "TE"]
projections = [25.5, 24.2, 22.3, 18.7, 16.5]

# Create problem
prob = LpProblem("My_Lineup", LpMaximize)

# Decision variables
x = {p: LpVariable(f"start_{p}", cat="Binary") for p in players}

# Objective: maximize points
prob += lpSum([projections[i] * x[players[i]] for i in range(len(players))])

# Constraints
prob += lpSum([x[p] for p, pos in zip(players, positions) if pos == "QB"]) == 1  # 1 QB
prob += lpSum([x[p] for p, pos in zip(players, positions) if pos == "RB"]) >= 2  # 2+ RB
prob += lpSum(x.values()) == 9  # 9 total starters

# Solve
prob.solve()

# Print results
print(f"Status: {LpStatus[prob.status]}")
print(f"Total Points: {value(prob.objective):.1f}")
for p in players:
    if x[p].varValue == 1:
        print(f"  ✓ {p} ({positions[players.index(p)]}): {projections[players.index(p)]}")
```

---

## Further Reading

- **PuLP Documentation**: https://coin-or.github.io/pulp/
- **Pyomo Book**: "Pyomo - Optimization Modeling in Python" (Springer)
- **OR-Tools Guide**: https://developers.google.com/optimization
- **CVXPY Tutorial**: https://www.cvxpy.org/tutorial/
- **Fantasy Optimization**: "Daily Fantasy Sports Lineup Optimization" (Csirmaz et al.)

---

## Summary

For FFPy lineup optimization:
- **Use PuLP** - perfect balance of simplicity and power
- **Consider Pyomo** if you need production-grade features later
- **Try CVXPY** for risk-adjusted portfolios (Phase 4)
- **Avoid scipy.milp** unless you really want minimal dependencies

**Bottom line:** PuLP gives us 90% of the power with 10% of the complexity.
