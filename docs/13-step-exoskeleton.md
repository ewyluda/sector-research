# 13-step research framework (credit note)

Parts of this project's research workflow were informed by the 13-step
equity-research process taught in Fundamental Edge's paid training course:
a thesis-development arc (steps 1–8) followed by active position management
(steps 9–13).

The original notes transcribed course slides and have been removed to respect
the course's intellectual property. Older plans and specs in `docs/` still
cite this file and its slide numbers; read those references as pointers to
the course, not to content in this repository.

How the ideas map to the product:

- Thesis construction with variant perception, pre-mortem, catalysts and kill
  criteria — `backend/app/graph/prompts.py` (thesis prompt) and
  `backend/app/models/phase_schemas.py`.
- Post-thesis monitoring — the Status board, catalyst calendar and question log.
- The recurring refresh loop — the workspace loop (see `docs/adr/0001`).
