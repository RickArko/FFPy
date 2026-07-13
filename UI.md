# User Interface (UI)


## Run the App Locally

```bash
uv run ffpy-web --host 0.0.0.0 --port 8000
```


Saved the plan to .ai/plans/db-deploys.md.

How I recommend you proceed
Today (5 min) — Phase 1 in the plan: seed production ADP manually so Draft Help works now:

fly ssh console -a ffpy-pickem -C "ffpy-db migrate"
fly ssh console -a ffpy-pickem -C "ffpy-db load-adp --season 2026"
Next PR to main — Phase 2:

Merge/cherry-pick 7c5619f (lazy ADP auto-fetch on Draft Help)
Add to fly.toml:
[deploy]
  release_command = "ffpy-db migrate"
Then — Phase 3: add post-deploy load-adp to .github/workflows/ci-cd.yml so every CI → prod deploy refreshes reference data without SSH.

Later — Phase 4: optional weekly scheduled ADP refresh during draft season.

The plan doc includes a mermaid architecture diagram, data-category tables, feature→data requirements, checklists, and explicit non-goals (don’t run full-data on Fly, don’t wipe the volume). Style matches your other plans like cfb/college_expansion.md (headers, tables, diagrams, phased checklists, repo links).

Want me to implement Phase 2 + 3 in the repo next?