# Perfume Selection Agent (MVP)

A chat-based perfume advisor: it asks a few questions (or reads plain English / Arabic), searches a
perfume catalogue, and recommends **3 perfumes plus 1 layering pair**, each with a one-line reason.
Built from the PRD "Perfume Selection Agent" as a disposable one-week prototype on Azure.

- **Widget**: one embeddable script (`/widget.js`), Shadow DOM, English + Arabic (RTL), guided quiz or free text,
  results card with match score, price, notes, imagery, refine chips, thumbs, wishlist (consent first).
- **Agent**: OpenAI Agents SDK on Azure OpenAI with five tools (`search_perfumes`, `get_perfume`, `find_similar`,
  `suggest_layering`, `save_wishlist`) and an output guardrail: any perfume id that no tool returned is dropped.
  Hard constraints the user states (dislikes, "not sweet", budget, strength) are enforced in code around the model.
- **Recommender**: deterministic hybrid score, 50% note/accord cosine match, 30% semantic match
  (Azure OpenAI embeddings when configured, IDF keyword match otherwise), 20% quality (ratings), diversity rule,
  rule-based layering pairs. Works with no model at all (guided quiz and rule-based chat fallback).
- **Data**: one taxonomy (8 families, 85 master notes with Arabic labels and synonyms), an importer for the Kaggle
  Fragrantica CSV or any brand CSV, and a 121-perfume seed catalogue so the app runs before any download.
  Prices in the seed/Kaggle data are **estimates** (flagged `est.` in the UI) until a brand feed with prices is imported.
- **Evals**: `evals/cases.json` (25 cases across the 8 PRD case types), `python -m evals.run`.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill AZURE_OPENAI_* or set LLM_PROVIDER=none for rule-based mode
scripts/dev.sh                  # seeds data/app.db from data/seed/seed_catalogue.csv and starts http://localhost:8000
```

Open http://localhost:8000 (demo store page with the widget) or embed on any page:

```html
<script src="https://<host>/widget.js" data-lang="en"></script>
```

## Catalogue

```bash
scripts/fetch_kaggle.sh                                   # downloads olgagmiufana1/fragrantica-com-fragrance-dataset to data/raw/
python -m app.pipeline.importer data/raw/fra_cleaned.csv --source kaggle-fragrantica --licence "scraped; prototype only"
python -m app.pipeline.importer my_brand.csv --source brand --licence "brand catalogue" --replace   # columns: name, brand, top, middle, base, accords, description, price_aed, image_url, product_url
```

Every row records `source` and `licence`; unknown notes go to the review queue (`/api/admin/summary`).
Set `BRAND_FILTER=<brand>` to restrict a deployment to one brand's range.

## Tests and evals

```bash
python -m pytest -q                                  # unit + API + agent loop (offline mock model)
LLM_PROVIDER=mock  python -m evals.run               # deterministic
LLM_PROVIDER=azure python -m evals.run               # real model, needs AZURE_OPENAI_* env
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/session` | start (or resume) a session; returns greeting + 5 quiz questions |
| `POST /api/chat` | free-text turn (EN/AR) → reply, picks, layering, chips |
| `POST /api/quiz` | submit the guided quiz → picks |
| `POST /api/refine` | chips: `less_sweet`, `fresher`, `cheaper`, `stronger`, `lighter`, `more_like:<id>` |
| `POST /api/wishlist`, `GET /api/wishlist` | wishlist (requires `consent: true`) |
| `POST /api/feedback`, `POST /api/events` | thumbs / clicks / analytics events |
| `GET /api/image/<id>` | bottle art (SVG), or a generated PNG when `AZURE_OPENAI_IMAGE_DEPLOYMENT` is set |
| `GET /api/admin/summary` | `Authorization: Bearer <ADMIN_TOKEN>`: events, low-rated picks, zero-result requests, unknown notes |
| `GET /api/health` | status |

## Deploy to Azure (disposable, one resource group, everything tagged)

See [infra/README.md](infra/README.md). Short version: add the GitHub secrets it lists and run the
**Deploy** workflow, or `infra/deploy.sh` from a machine with `az login`. Everything lives in
`rg-perfume-agent-mvp` tagged `project=perfume-agent-mvp environment=disposable expires=2026-10-05`;
`infra/teardown.sh` (or the scheduled **Teardown** workflow) deletes that group and nothing else.

## Layout

```
app/main.py              FastAPI service, orchestration, guardrails, fallback
app/agent/llm_agent.py   OpenAI Agents SDK agent, tools, grounding guardrail
app/agent/recommender.py hybrid scoring, similarity, layering
app/agent/extract.py     rule-based EN/AR profile extraction (quiz + fallback + hard constraints)
app/agent/cards.py       localized result cards
app/agent/images.py      SVG bottle art + optional Azure OpenAI image generation
app/data/taxonomy.json   families, notes (+Arabic), moods, seasons, layering rules
app/pipeline/importer.py CSV importer (Kaggle Fragrantica schema or brand CSV)
app/static/widget.js     embeddable widget; index.html demo page
evals/                   eval cases + runner
infra/                   Bicep, deploy/teardown scripts, GitHub workflows
```

## Known limits (MVP)

- Prices are estimated by brand tier unless the CSV has a price column.
- Free Kaggle data is scraped; prototype use only (see the PRD's data-rights risk).
- Wishlist is per browser session (no accounts); email of picks was dropped from scope.
