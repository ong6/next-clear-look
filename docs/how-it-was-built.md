# How this was built

Next Clear Look was built in one night by GPT-5.6 coding agents working in terminal sessions,
orchestrated by Claude Opus 5.5. The owner wrote one instruction: find a project that is visually
striking, deep on the backend and genuinely useful; research five domains, pick the best idea, then
use three agents to develop and implement it. Opus made every technical decision. Separate Claude
reviewers judged each round. This page records what happened, with the numbers.

- Agent work: 2026-10-03, 01:18 to 10:51 Singapore time (about 9.5 hours), then a final pass by
  Opus.
- Agent sessions started: 21 (5 research, then 3 long-lived roles restarted per round).
- Independent review passes: 7 (cross-spec, engine code, three design, two repository).

## Roles

| Role | Who | Owns |
|---|---|---|
| Orchestrator | Claude Opus 5.5 | Plan, goals, technical decisions, merges, acceptance |
| Workers | GPT-5.6 agents in terminal sessions | Research, specs, code, tests, fixtures, docs |
| Reviewers | Fresh Claude sub-agents | Scores and defect lists; never the authors' self-scores |

Workers signal completion by writing a `STATUS` file (done or blocked, a self-score, deliverables).
The orchestrator never accepted a self-score: every round was judged by a reviewer that had not
written the work.

## Timeline

| Phase | Workers | What came out |
|---|---|---|
| Research | 5 agents in parallel, one per domain | 25 scored ideas; every data source fetched live and sampled. Self-scores clustered at 46–52/60, so they could not rank across domains |
| Selection | Opus | Next Clear Look over a BGP route-replay tool, judged on a cross-domain table |
| Develop | 3 agents in parallel (engine, product, data) | Architecture, algorithms and an OpenAPI contract with spike code; product spec, design system and a Cesium prototype; data contracts, replay design and 17 quality gates. The orbit spike matched 5 of 5 real Sentinel-2 acquisitions with a 0.27 s median timing error |
| Cross-spec review | Claude reviewer | 28 conflicts between the three specs (7 blocking, 9 high, 12 medium), ruled in [`decisions.md`](decisions.md) before any code |
| Implement 1 | The same 3, each in its own clone and branch | Engine and contract, web app, record/replay platform. An early integration dry run found 18 seam problems (12 engine, 6 platform) before the first merge |
| Engine review | Claude reviewer | 12 defects, 11 reproduced (below) |
| Implement 2 | The same 3 | All 12 fixed with regression tests; datatake mosaics; five presets recorded |
| Design rounds | Product agent, two Claude design reviews | An art-direction brief, then a scored review (7.0/10), then fixes |
| Performance | Engine agent | Staged streaming; 4.2× (Tuas) and 4.1× (Sundarbans) faster on identical cached inputs, byte-identical results |
| Acceptance | Two Claude reviewers | Design 8.1/10. Repository 6/10 with critical issues: area drawing was a stub, some README claims were false, no licence, CI would fail on Linux |
| Polish | All 3 | Every listed item fixed |
| Final pass | Opus | Label and layout fixes, public decision log, full `make ci` |
| Final re-review | Claude reviewer | 7.5/10: every earlier item fixed or mostly fixed, but one README claim was false (identical requests did not produce identical event streams, because job IDs counted unrelated jobs). Opus fixed the code, with a test, rather than the wording |

## Self-scores against independent review

| Round | Worker self-score | Independent result |
|---|---:|---|
| Engine, first implementation | 9/10 | 12 defects; the likelihood could never be computed; acquisition rate 0.38 against an observed ~0.90 |
| Web, first hero pass | 9.3/10 | Art-direction review: a second satellite was drawn at an invented offset; the opening frame was a CSS placeholder; the pass was lit at the wrong hour |
| Web, visual round 1 | 9.7/10 | 7.0/10: the light sheet and swept swath were invisible; a "T0" clock showed before any pass existed |
| Platform, all gates green | 9.8/10 | Repository 6/10 with four critical issues |
| Web, area drawing | (reported complete) | Drawing invented its vertices from the preset's centroid |

## What the engine review found

1. A short opportunity window overwrote the stored likelihood with a false 0%.
2. Multi-tile areas were never mosaicked; partial tiles reported whole-area clear percentages.
3. The clear-look probability could never be computed (6 scenes against a 20-trial minimum).
4. The acquisition model assumed a 5-day repeat per satellite (truth: 10 days), giving 0.38
   instead of ~0.90.
5. The coarse pass scan missed passes for multipolygons and unevenly-vertexed polygons.
6. The event stream dropped the terminal event (20 of 20 streams).
7. Jobs survived restarts as zombies; replay reused cancelled jobs.
8. A drawn area in replay flipped from "not recorded" to "empty" after any job.
9. Opportunity IDs changed between runs, duplicating live results.
10. Trajectory swath edges used the previous sample's heading (up to 59 km off at high latitude).
11. `truncated` was never set for windows that start mid-pass.
12. Opportunity-day counts depended on the server's timezone.

Every fix landed with a regression test that failed before it.

## Mechanics that made parallel work safe

- **Contract first.** The engine agent published the OpenAPI contract and SSE schemas before
  writing the engine; the web agent built against generated examples.
- **One decision log.** Conflicts were ruled once, numbered, and cited by every later goal.
- **One writer per checkout.** Each agent worked in its own clone and branch with a list of paths
  it owned. A loop merged pushed branches into `main` every five minutes: 56 merges, no conflicts.
- **A watchdog.** It interrupted a model call stalled for 8 minutes and a command hung for
  101 minutes, nudged idle sessions twice, and made one session that had fallen to about 20% context commit
  its work and write a handoff before a fresh session took over.

## Where the orchestrator was wrong

- A replay-clock rule required the next Tuas pass to fall 2–4 hours after the recording instant,
  which blocked recording for most of the day; it was amended to search back up to 72 hours.
- A tight catalogue budget made the recorder shrink four presets to 2–8 km boxes; Rotterdam no
  longer contained Maasvlakte. The budget was raised and the presets re-recorded at 130–497 km².
- Opus's own visual direction for the globe was not enough: it only became striking after a
  dedicated art-direction review that specified camera poses, materials and lighting values.
