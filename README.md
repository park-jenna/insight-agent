# InsightAgent

A RAG agent that answers questions across uploaded documents and structured data, with a reasoning trace, source citations, and an evaluation pipeline that scores its own output.

A tool calling agent decides when to search a document library and when to query a dataset, runs those tools, and returns an answer grounded in the results. Document answers cite their source files; data answers show the computed values; questions outside the available data are declined rather than answered. The agent and retrieval are domain neutral. The first deployment serves a special education advocacy context (see [Applied context](#applied-context)).

Repository: https://github.com/park-jenna/insight-agent

## What it does

A question in plain language is routed to the right source. Policy and procedure questions go to a document library of PDFs through hybrid retrieval. Counts, percentages, trends, and comparisons go to tabular CSV data through analysis tools. A question that needs both, such as "how many students are in a program, and what is the process for filing a complaint", uses both paths in one turn.

Answers stream token by token. A run inspector shows which tools ran, in what order, what they returned, and how long each took. When the documents and data do not contain an answer, the agent says so instead of inventing one.

## Architecture

| Layer | Choice |
|---|---|
| Frontend | Next.js, TypeScript, recharts |
| Backend | Python, FastAPI |
| Database | Postgres with pgvector, hosted on Supabase |
| Embeddings | OpenAI text-embedding-3-small (1536 dim) |
| Generation | OpenAI gpt-4o-mini |
| Transport | Server Sent Events for streaming |

A question hits the FastAPI agent endpoint. The agent loop plans tool calls, executes them, feeds the results back, and repeats up to a step limit before producing the final answer. The loop is implemented directly rather than with an agent framework, which keeps the reasoning trace, the streaming, and the grounding rules under explicit control.

Retrieval is hybrid. Vector search (pgvector cosine distance) and Postgres full text search run on the same candidate pool and are combined with Reciprocal Rank Fusion. Vector search covers meaning; keyword search covers exact identifiers such as section numbers, which embeddings tend to miss.

The schema separates documents and their chunks from datasets and their rows. Each chunk stores a 1536 dimension embedding with an HNSW index for vector search and a tsvector with a GIN index for keyword search. Tabular data is stored as JSONB rows and analyzed with Pandas. Sessions and prior turns are persisted so the agent carries short conversational memory.

The six agent tools are domain neutral: search documents, analyze a dataset column, detect trends over time, find anomalies, calculate ratios, and compare two periods. Adapting to a different domain means loading different data and writing a different system prompt.

The interface is a two panel workspace: the conversation on the left, a run inspector on the right that shows the agent's tool steps and timings as they stream in over Server Sent Events.

## Evaluation

The evaluation runs offline against 27 labeled questions: document questions, data questions with exact answers computed from the source CSV, questions that need both, exact identifier questions, and out of scope questions with no answer in the data. A results dashboard renders the output live from a single API endpoint, so re running the evaluation refreshes the page.

### Retrieval

Hybrid search compared against vector only and keyword only, on the same queries and candidate pool, so the only variable is ranking and fusion.

| Method | Precision@5 | Recall@5 | MRR |
|---|---|---|---|
| keyword only | 0.124 | 0.073 | 0.150 |
| vector only | 0.213 | 0.378 | 0.541 |
| hybrid (RRF) | 0.253 | 0.425 | 0.589 |

Split by question style, vector leads on natural language questions and keyword leads on exact identifier questions. On the exact identifier questions, hybrid reaches an MRR of 1.0, ranking a correct chunk first in every case.

### Answers

Correctness is a substring check against known answers. Faithfulness is scored by a separate LLM acting as judge, which reads the retrieved context and decides whether each claim in the answer is supported. Out of scope honesty checks that the agent declined rather than fabricated.

Across runs, correctness sits in the high eighties to mid nineties percent (data questions at 100 percent, document questions around 91 percent), faithfulness scores around 0.90 with unsupported answers at zero or one out of fifteen, and out of scope honesty is 2 of 2. Scores move between runs because the model is not deterministic, so the pipeline is read as a trend across runs rather than a single number.

During development the evaluation surfaced a fabricated answer to an out of scope question, which led to a stronger grounding rule in the system prompt, and two cases where the evaluation labels themselves were wrong, which were corrected.

### Latency

Search time split into stages, over 27 queries, in milliseconds.

| Stage | Mean | p50 | p95 |
|---|---|---|---|
| embedding | 398 | 275 | 910 |
| retrieval | 129 | 88 | 100 |

Embedding is an external API round trip and is roughly three times slower than retrieval, a local database query, with a longer tail. Search is a small fraction of total response time; the answer generation call dominates.

## Running locally

Requires Python 3.12, Node, and a Postgres database with the pgvector extension (Supabase works without extra setup).

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
DATABASE_URL=your_postgres_connection_string
OPENAI_API_KEY=your_openai_key
```

Apply the schema and start the server:

```bash
python apply_schema.py
uvicorn app.main:app --reload
```

Every route except `/health` requires an API key, sent as an `X-API-Key`
header. Issue one for yourself (creates the user if the email doesn't
exist yet):

```bash
python create_api_key.py you@example.com
```

This prints the raw key once, it isn't stored anywhere retrievable, only
its hash is. Try it:

```bash
curl -X POST http://localhost:8000/agent/query \
  -H "X-API-Key: <the key from above>" \
  -H "Content-Type: application/json" \
  -d '{"query": "hello"}'
```

A missing or wrong key gets a 401.

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=<the key from create_api_key.py>
```

`NEXT_PUBLIC_*` values ship in the client bundle, so this key is visible
to anyone who can load the page. That's an acceptable tradeoff for an
internal tool on a trusted network, not for a publicly reachable one.

Start it:

```bash
npm run dev
```

The app runs at `http://localhost:3000`, the dashboard at `http://localhost:3000/dashboard`.

### Evaluation

Run from the `backend` directory with the virtual environment active:

```bash
python eval/label_eval_set.py        # label ground truth chunks
python -m eval.eval_retrieval        # hybrid vs vector vs keyword
python -m eval.eval_answers          # correctness, faithfulness, out of scope
python -m eval.eval_latency          # stage timings
```

Each writes a results file that the dashboard reads through the API.

## Applied context

The first deployment serves ChiEAC, an education advocacy cooperative. Advocates work across two kinds of information that usually live apart: special education policy documents (Illinois administrative code, consent form instructions) and program enrollment records. A question such as "what is the process for filing a state complaint, and how many of our students are active" crosses both. InsightAgent answers it in one place, showing the policy citation and the enrollment count together with the reasoning behind each.
