# TaskMatchEscrow

A GenLayer Intelligent Contract that combines semantic worker-matching with a trustless, judged task escrow. Workers register their skills as free text; task posters find the best-matching worker via vector similarity search, fund an escrow for that worker, and payment releases automatically once GenLayer's AI-validator consensus confirms the submitted deliverable satisfies the task.

## Why it is useful

Most escrow primitives assume the buyer already knows who to hire. TaskMatchEscrow removes that gap: it maintains a semantic registry of worker skills (via embeddings, not keyword tags), so a task poster can describe what they need in plain language and get back ranked candidate workers by actual meaning-based similarity — then fund and settle the job with the same contract, with no off-chain matching platform and no manual payment release.

This is a reusable pattern for any DAO, bounty board, or marketplace that needs both **discovery** (who can do this?) and **trustless settlement** (did they actually do it?) in one primitive.

## Why this needs GenLayer

- **Semantic matching** requires comparing meaning, not exact keywords — a deterministic hash or string match cannot tell "Python backend developer" and "builds APIs in Django" are related skills. Embeddings + vector search solve this deterministically, with no consensus round needed for the math itself.
- **Judging deliverable completion** is inherently a natural-language judgment call — "does this webpage satisfy the task requirement" isn't reducible to a numeric check, and no single party (buyer or worker) can be trusted to self-report honestly with real money on the line.

## Non-determinism budget

Only one non-deterministic operation exists: the deliverable-judgment step in `_judge()`, which fetches the submitted URL via `gl.nondet.web.render` and asks an LLM to classify it as `SATISFIED` or `UNSATISFIED`. This is wrapped in `gl.eq_principle.prompt_comparative` with an explicit principle: validators must agree on the exact categorical token, never on incidental wording. Everything else — embeddings, vector search, state transitions, fund movement — is fully deterministic.

## Protocol flow

```
Worker                    Contract                     Poster
  |  register_skill(desc)    |                             |
  |------------------------->|                             |
  |                          |     find_best_match(task)    |
  |                          |<------------------------------|
  |                          |  (returns ranked candidates) |
  |                          |                             |
  |                          |     post_task(desc, worker)  |
  |                          |     (funds reward, 48h       |
  |                          |      deadline starts)        |
  |                          |<------------------------------|
  |  submit_deliverable(url) |                             |
  |------------------------->|                             |
  |                    [fetch URL, LLM judges]              |
  |                    [validator consensus on verdict]     |
  |                          |                             |
  |   SATISFIED -> worker paid full reward                 |
  |   UNSATISFIED -> poster refunded                        |
  |   unchallenged past deadline -> claim_timeout_refund()  |
  |     (anyone can trigger, poster refunded)               |
```

## Fund safety

- **`cancel_task()`** — poster can reclaim funds anytime before a deliverable is submitted.
- **`claim_timeout_refund()`** — if the worker never submits, anyone can trigger a refund to the poster once the 48-hour deadline passes, so funds and the task slot never get stuck indefinitely.
- **No silent defaults** — the judgment step only produces exactly `SATISFIED` or `UNSATISFIED`; the settlement logic explicitly branches on both, so there's no path where malformed output accidentally releases or withholds funds incorrectly.

## State model

| Field | Purpose |
|---|---|
| `skill_registry` | VecDB of worker skill embeddings + profiles |
| `total_workers` | Count of registered workers |
| `is_open` | Whether a task is currently active |
| `task_description` / `poster` / `assigned_worker` / `reward` | Current task details |
| `deliverable_url` | Submitted proof-of-work link |
| `deadline` | Timeout for the current task |
| `total_completed` / `last_result` | History of resolved tasks |

## Contract API

| Method | Type | Purpose |
|---|---|---|
| `register_skill(skill_description)` | write | Add a worker to the semantic skill registry |
| `find_best_match(task_desc, top_n)` | view | Get ranked candidate workers by semantic similarity |
| `post_task(task_description, worker_address)` | write, payable | Fund and assign a task to a specific worker |
| `cancel_task()` | write | Poster reclaims funds before submission |
| `submit_deliverable(url)` | write | Worker submits proof-of-work, triggers judgment |
| `claim_timeout_refund()` | write | Anyone can trigger a refund after the deadline if unsubmitted |
| `get_current_task()` | view | See the currently open task, if any |
| `get_last_result()` | view | See the most recent settlement outcome |
| `get_total_workers()` / `get_total_completed()` | view | Registry/task statistics |

## Local verification (tested live in GenLayer Studio, Normal/Full Consensus)

Both settlement outcomes were tested end-to-end against real deployed state, not simulated:

**Test 1 — UNSATISFIED path:** Task requirement "Write a short explanation of what the Python programming language is," deliverable pointed to a raw documentation page with extra navigation/site content mixed in. Equivalence Principle consensus: 4 of 5 validators (leader + `prd-glm`, `anthropic-sonnet-4.6`, `prd-gpt-5-4`, `prd-minimax`) independently agreed **UNSATISFIED** (1 dissent from `prd-qwen`). Consensus reached ACCEPTED. Contract correctly ran the refund path: `"UNSATISFIED - poster refunded 2000000000000000000 wei"`.

**Test 2 — SATISFIED path:** Same task requirement, deliverable pointed to a clean, self-contained explanation of Python with no extraneous content. Equivalence Principle consensus: **SATISFIED**. Contract correctly ran the payment path: `"SATISFIED - worker paid 2000000000000000000 wei"`.

Both the success and failure branches of the judged-settlement logic are confirmed working against live multi-validator consensus, not just unit-tested in isolation.

## License

MIT
