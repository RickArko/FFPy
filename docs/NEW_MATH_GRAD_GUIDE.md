# FFPy for a New Math Grad

This is an optional companion guide for a new contributor with a strong math background and limited production Python experience.

It does not replace the main happy path. Start with `README.md`, `QUICKSTART.md`, and `CONTRIBUTING.md` as written. Come here when you want the "why does this repo matter?" version.

## Why This Repo Is a Good Fit

If you are coming from math, this repo is not "just a fantasy football app."

It is a compact, friendly systems project where you can practice:

- turning raw domain rules into code (`src/ffpy/scoring.py`)
- building a simple predictive baseline from historical data (`src/ffpy/projections.py`)
- expressing a real decision problem as binary optimization (`src/ffpy/optimizer.py`)
- working with local data infrastructure (`src/ffpy/database.py`, `src/ffpy/cli.py`)
- shipping something people can actually run and inspect (`src/ffpy/app.py`)

That mix is unusually good for a recent grad because it sits between theory and product:

- enough math to be interesting
- enough engineering to teach good habits
- enough UI and tooling to make the work feel real

## The Mental Model

You can think of FFPy as five layers:

1. `scoring.py`
   Takes a vector of football stats and maps it to fantasy points.
   This is the cleanest "math to code" layer in the repo.

2. `database.py`
   Stores observed historical outcomes.
   This is your empirical substrate.

3. `projections.py`
   Estimates future performance from past performance.
   Right now this is a simple baseline model, which is a feature, not a bug.

4. `optimizer.py`
   Solves "which lineup should I start?" as a constrained optimization problem.
   This is the most direct OR / applied math component.

5. `app.py`
   Makes the outputs visible and interactive.
   This is where analysis becomes a tool someone can use.

If you only remember one thing, remember this:

The repo is strongest when you treat it as an end-to-end decision system, not just an ML experiment.

## First 90 Minutes

If I were onboarding you personally, I would ask you to do exactly this:

```bash
make bootstrap
make test
make db.mock SEASON=2024
make run
make notebook
```

Then I would have you read files in this order:

1. `src/ffpy/scoring.py`
2. `tests/test_scoring.py`
3. `src/ffpy/optimizer.py`
4. `tests/test_optimizer.py`
5. `src/ffpy/projections.py`
6. `src/ffpy/database.py`
7. `src/ffpy/cli.py`
8. `src/ffpy/app.py`

Why this order works:

- `scoring.py` is deterministic and easy to reason about
- `optimizer.py` shows the repo's most interesting mathematical structure
- `projections.py` introduces modeling without too much framework overhead
- `database.py` and `cli.py` show how the project becomes operational
- `app.py` becomes much easier once you know what data it is presenting

## How To Translate Your Math Background

Here is the shortest bridge from math language to repo language:

- fantasy scoring = a rule-based function over a stat vector
- projection = an estimator under uncertainty
- optimizer = maximize a linear objective over binary decision variables with constraints
- consistency = a rough dispersion proxy
- data loading = building the dataset your model depends on
- Streamlit = a lightweight decision dashboard

You do not need to begin by asking, "Where is the deep learning?"

A better first question is:

"What is the decision, what is the objective, what are the constraints, and how do we know the estimate is any good?"

That is the right instinct for this codebase.

## What Is Worth Learning Here

The repo teaches several good habits that matter far beyond sports analytics:

- Baselines first. The historical projection model is intentionally simple enough to inspect.
- Clear interfaces. The CLI, app, database, and optimizer are separated well enough to study independently.
- Local-first development. You can run the stack without needing a cloud deployment story on day one.
- Testing behavior, not hype. The existing test suite is small but points in the right direction.
- Optimization as product logic. Many grads see optimization only in class; here it directly drives a user-facing decision.

## Good First Contributions for You

If you are a new math grad, these are the highest-leverage contributions to target first.

### 1. Make projection experiments more reproducible

`src/ffpy/projections.py` injects random variance into outputs. That is fine for realism, but awkward for testing and evaluation.

A strong contribution would be:

- add an optional `random_seed` or `numpy.random.Generator`
- make the stochastic part explicit
- add tests that separate deterministic behavior from "sampling" behavior

Why this is good:

- it teaches API design
- it improves scientific hygiene
- it is mathematically simple but engineering-relevant

### 2. Add an evaluation loop for projections

Right now the repository has a projection generator, but the learning experience would improve a lot if contributors could answer:

"How good is this model versus a naive baseline?"

Useful additions:

- a notebook or script that compares projected points to actual points
- error metrics like MAE, RMSE, and rank correlation
- position-level breakdowns
- a simple "recent average" baseline versus the current weighted model

This is one of the best "math grad" tasks because it connects statistics, experimentation, and product usefulness.

### 3. Strengthen optimizer explainability

The optimizer already does something genuinely interesting. A nice next step is helping new contributors understand why a lineup was chosen.

Examples:

- expose which constraint was binding
- show why a bench player lost to a starter
- summarize team-limit or FLEX effects
- compare optimal lineups under different scoring settings

This turns the optimizer from a black box into a teaching tool.

### 4. Add a domain glossary

A math grad may understand constrained optimization faster than fantasy football jargon.

A small but high-value doc would define terms like:

- PPR
- FLEX
- superflex
- DST
- stack / team limit
- pick'em
- opponent / home-away context

This sounds minor, but it removes a real barrier for analytically strong newcomers.

### 5. Build a "theory to code" notebook

One of the best teaching artifacts would be a notebook that walks through:

- scoring as a weighted sum
- projections as weighted historical averages
- lineup selection as integer programming
- uncertainty, bias, variance, and leakage in plain language

This would make the repo much more legible to students coming from math, stats, OR, or physics.

## What Not To Start With

I would not begin with:

- ESPN integration internals
- Streamlit page polish
- API edge cases
- large refactors across the whole repo

Those are real tasks, but they are not the best learning path.

Start where the mathematical structure is cleanest:

- scoring
- projections
- optimizer
- evaluation

## A Very Good First Week

If you want a concrete first week plan:

### Day 1

- run the project locally
- read `scoring.py` and `optimizer.py`
- run the example scripts

### Day 2

- inspect the tests
- change one scoring rule locally and see what breaks
- trace how a projection reaches the app

### Day 3

- read `projections.py`
- identify the current modeling assumptions
- write down what would count as a fair baseline comparison

### Day 4

- open the notebooks
- inspect the mock database outputs
- compute one or two simple evaluation metrics by hand

### Day 5

- choose one small contribution
- write tests first if you can
- open a small PR with a clear explanation of the tradeoff

If you do just that much, you will already understand more of the repo than many casual contributors.

## Questions You Should Be Asking

These are excellent questions in this project:

- What exactly is being optimized?
- Which assumptions are encoded as constants?
- What data would cause leakage if I used it carelessly?
- How stable are the projections week to week?
- How do scoring settings change the optimizer's behavior?
- What is deterministic, and what is stochastic?
- What should be tested at the unit level versus the integration level?

## What I Would Improve In The Repo

If the goal is to make FFPy an even better learning repository for recent grads, I would prioritize:

1. An explicit contributor ladder.
   Example: "read-only tour", "first doc PR", "first test PR", "first modeling PR", "first CLI PR".

2. A model evaluation workflow.
   New contributors should be able to measure whether a modeling change helped.

3. A domain glossary.
   Sports vocabulary is an unnecessary source of friction for quantitatively strong beginners.

4. A deterministic projections mode.
   This would improve debugging, trust, and testability.

5. A single architecture page.
   One diagram or one short doc showing data flow from ingest to projection to optimization to UI would pay off quickly.

6. A small set of curated starter issues.
   Something like "2-hour", "half-day", and "weekend" tasks would make the repo much more approachable.

7. A benchmark page for baselines.
   Even a humble table comparing sample, historical average, and weighted recent average would teach excellent habits.

## What I Would Say To You Directly

If you are the new math grad reading this:

You do not need to show up with perfect software-engineering instincts on day one.

What matters most is that you can reason clearly, test your assumptions, and explain tradeoffs.

That is already a huge part of good ML and good open-source work.

This repository is a nice place to practice turning that mindset into shipped code.

The right first contribution is not the most ambitious one.
It is the smallest change that makes the system clearer, more testable, more reproducible, or more measurable.
