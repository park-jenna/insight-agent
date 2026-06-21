# InsightAgent

**AI Agent Platform for Document Intelligence and Data Analysis**

Architecture and Product Overview (completed system reference)

---

## 1. What It Is

InsightAgent is a full stack AI platform that lets any team upload documents and structured data, then ask questions across both in plain language. The system retrieves passages from documents using retrieval augmented generation, runs analysis on datasets using a tool calling agent, and combines both into one grounded answer with citations.

The platform is domain agnostic. The first deployment serves the Chicago Education Advocacy Cooperative (ChiEAC), where advocates query scholarship policies, financial aid rules, and program records. The same system reconfigures for sales analytics, HR knowledge bases, customer support, or any setting where teams search documents and analyze data at the same time.

The core thesis: most portfolio tools handle either documents or data. InsightAgent handles both behind a single agent, and proves the answer quality with an evaluation layer.

---

## 2. System Architecture

The system has three layers: a Next.js frontend, a FastAPI backend that holds the AI logic, and a Postgres data layer with pgvector.

### Frontend (Next.js + TypeScript)

* Chat interface for natural language questions
* File upload for CSV and PDF
* Token by token answer streaming over Server Sent Events
* A reasoning trace panel showing which tools the agent called and why
* Source citations linking answers back to the documents that informed them
* Charts and tables for data results
* Configurable branding (title, description, logo) driven by config, so the same build serves any deployment

### Backend (Python + FastAPI)

* Ingestion endpoints for CSV and PDF
* The RAG pipeline (extraction, chunking, embedding, hybrid retrieval)
* The agent loop (planning, tool execution, answer synthesis)
* A tool registry that exposes analysis and retrieval as callable functions
* An SSE endpoint that streams the agent response as it generates
* Domain configuration through environment variables (system prompt, labels)

### Data and Storage (Postgres + pgvector on Supabase)

* Relational tables for users, datasets, documents, sessions, and analysis history
* Dataset rows stored as JSONB so any CSV shape loads without a schema change
* Document chunks stored with both a vector embedding and a full text index, which is what makes hybrid search possible in one query
* pgvector keeps embeddings next to the relational data, so no separate vector database is needed

### Request Lifecycle

Ingestion:

Upload CSV or PDF → FastAPI ingestion endpoint → (CSV path: Pandas parse, column type inference, rows stored as JSONB) or (PDF path: text extraction, semantic chunking, embedding) → stored in Postgres and pgvector

Query:

User question → Agent planner (LLM decides which tools to use) → tool execution (document retrieval and dataset analysis) → LLM synthesizes a grounded answer with citations → streamed token by token to the frontend → reasoning trace and sources displayed

---

## 3. Core Features

### Dual Data Ingestion

* **Structured data:** any CSV is parsed, its column types inferred, and its rows stored. The system detects available columns automatically with no domain specific validation.
* **Unstructured data:** any PDF is extracted, chunked with overlap, embedded, and stored. Scanned image PDFs with no text layer are detected and reported rather than failing silently.

### RAG Pipeline

* PDF text extraction with page awareness
* Semantic chunking with configurable overlap, so a fact sitting on a chunk boundary still appears whole in at least one chunk
* Embedding with OpenAI text embedding 3 small (1536 dimensions)
* Hybrid retrieval combining full text keyword search and vector similarity
* Rank fusion to merge the two result lists into one ranking
* Source citation on every answer, naming the document each passage came from

### Autonomous Agent System

The agent runs a multistep reasoning loop using function calling:

1. Understand the question and decide which data sources are relevant
2. Plan which tools to call and in what order
3. Execute the tools and collect results
4. Synthesize the findings into a grounded answer with citations
5. Recover from tool errors by retrying with an alternative approach

The loop is built directly rather than with a framework, which keeps the control flow visible and debuggable.

### Tool Layer (generic by design)

All tools are named for the operation, not the domain, so the same agent works anywhere:

* **search_documents:** retrieve relevant passages through hybrid search
* **analyze_dataset:** summary statistics for a dataset or a single column
* **detect_trends:** identify movement in a metric over time
* **find_anomalies:** flag outliers or unusual values in a dataset
* **calculate_ratios:** compute ratios between two metrics, such as rates or percentages
* **compare_periods:** compare a metric across two time windows

New tools register in one place without touching the agent loop.

### Session Memory

* Conversation history stored per session
* The agent can reference earlier analysis results in follow up questions
* Context window managed to stay within token limits

### Streaming Responses

* Answers stream token by token over Server Sent Events
* The interface shows live reasoning steps such as searching documents or analyzing data
* A collapsible trace shows which tools ran and with what arguments

### Evaluation Pipeline

This is what separates the platform from a demo. It measures whether the system actually works:

* **Retrieval quality:** precision and recall over a fixed evaluation set of queries with known relevant chunks
* **Answer faithfulness:** an LLM as judge pattern scores whether the answer is grounded in the retrieved context rather than invented
* **Latency tracking:** timing recorded per pipeline stage (embedding, retrieval, model call, total)
* **Dashboard:** evaluation results displayed over time in the frontend

---

## 4. User Flows and Use Cases

### ChiEAC Deployment (pilot)

* "What scholarships can an undocumented high school senior in Chicago apply for?" → document retrieval over policy guides
* "How many students are currently active in ELEVATE?" → dataset analysis over enrollment records
* "Which families have not had a check in within 30 days?" → dataset filtering over case records
* "What is the process for filing an IEP complaint?" → document retrieval over advocacy handbooks
* "Summarize ELEVATE outcomes this quarter and include relevant scholarship placement info." → both sources, multistep

### Business Deployment (alternate demo)

* "What is our refund policy for enterprise customers?" → document retrieval
* "Show me revenue trends for the past six months." → dataset analysis
* "Which accounts have had no activity in 30 days?" → dataset filtering
* "Compare customer acquisition cost across two quarters and find relevant strategy docs." → both sources, multistep

The query patterns are identical across deployments. Only the data and the system prompt differ.

### Worked Multistep Flow

Question: "How many students are in the ELEVATE program, and what is the process for filing an IEP complaint?"

1. The agent recognizes two distinct needs in one question
2. It calls analyze_dataset on the enrollment data to count ELEVATE students
3. It calls search_documents to retrieve the IEP complaint procedure
4. It synthesizes both results into one answer, citing the source document for the procedure
5. The reasoning trace shows both tool calls, which is the visible proof that the agent split the question and used two sources on its own

This single flow is the clearest demonstration of the platform's core claim.

---

## 5. Domain Agnostic Design

The platform stays reconfigurable through four choices:

* **Generic tool names** describe operations, not domains
* **System prompts live in config**, not in code, so switching from education advocacy to business analytics is a one line change
* **Ingestion accepts anything**, since any CSV becomes queryable and any PDF becomes searchable with no domain rules
* **Two demo datasets** are prepared (ChiEAC and a generic business scenario), swappable in under a minute

No domain specific logic is hardcoded anywhere in the backend.

---

## 6. Tech Stack and Key Decisions

* **FastAPI for the AI backend:** Python is the native language of the AI tooling ecosystem, and FastAPI provides async support and automatic API documentation
* **pgvector over a standalone vector database:** keeping vectors alongside relational data in one Postgres instance lets hybrid search and joins run in a single query, with no extra service to operate
* **Hybrid search over pure vector similarity:** vector search misses exact identifiers such as section numbers, keyword search catches them, and combining both beats either alone
* **Reciprocal Rank Fusion to combine searches:** cosine distance and text rank sit on different scales and cannot be added directly, so the two result lists are merged by rank instead of raw score
* **Agent loop built directly rather than with a framework:** keeps the control flow visible and demonstrates understanding of how function calling actually works, while a framework remains the right choice for faster prototyping or more complex multi agent flows
* **Streaming over Server Sent Events:** standard in shipped AI products and simpler than a full socket layer for one directional output

Full stack: Next.js, TypeScript, Tailwind, Python, FastAPI, Pandas, OpenAI API, PostgreSQL, pgvector, Supabase, Vercel, Render.

---

## 7. Deployment Topology

* **Frontend:** Vercel
* **Backend:** Render or Railway
* **Database:** Supabase (Postgres with pgvector)
* **Configuration:** environment variables select the domain, system prompt, and labels, so the ChiEAC version is live by default and the business version is ready to swap

---

## 8. Implementation Status

This document describes the completed system. Build progress to date:

* Done: FastAPI backend, Supabase with pgvector, full schema, CSV ingestion with type inference, PDF extraction and chunking, embedding pipeline, hybrid search with rank fusion, agent loop with two tools
* Remaining: the four additional analysis tools, session memory persistence, SSE streaming, the Next.js frontend, the evaluation pipeline and dashboard, and deployment
