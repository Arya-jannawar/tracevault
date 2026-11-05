# TraceVault API contract (v1) — shared reference for frontend & tests

Base URL: `/api/v1` (dev: Vite proxies `http://127.0.0.1:8000`).
All mutations require header `X-TraceVault-Session: 1` (CSRF) when cookie-authenticated.
Error envelope: `{"code": "...", "message": "...", "request_id": "..."}`.

| code | status | meaning |
|---|---|---|
| content_blocked | 410 | tombstoned/invalidated content requested (content-free) |
| publication_blocked | 409 | deletion fence committed before publication |
| csrf_missing | 403 | mutation missing CSRF header |
| auth_failed | 401 | sign-in required / invalid session |
| forbidden | 403 | viewer attempted operator action |
| not_found | 404 | |
| validation_failed | 422 | |
| unsupported_content | 415 | file type/extraction rejected (safe message) |
| adapter_unavailable | 503 | AI adapter down; actionable message |
| connector_unavailable | 503 | storage connector down |
| idempotency_conflict | 409 | same key, different payload |

## Auth
- `POST /auth/login` `{username,password}` → `{username, role}` + HttpOnly cookie `tv_session`
- `POST /auth/logout` → `{ok:true}`
- `GET /auth/me` → `{username, role}`

## Documents
- `POST /documents` multipart `file` (txt/md/pdf) or form `content`+`title` → `201 DocumentOut`
- `GET /documents?q&state&page&page_size` → `DocumentOut[]`
- `GET /documents/{id}` → `DocumentDetail` (adds `versions[]`, `coverage_notes[]`)
- `GET /documents/{id}/content` → `{document_id,title,content}` | **410 content_blocked**
- `GET /documents/{id}/chunks` → `ChunkOut[] {artifact_id,index,start,end,text|null,lifecycle_state}`
- `GET /documents/{id}/versions` → `DocumentVersionOut[] {id,version,source_type,filename,checksum,content_state,created_at}`
- `GET /documents/{id}/deletion-impact` → `DeletionImpact {document_id,affected_count,affected_by_type,coverage_warnings[],scope_exclusions[]}`
- `DELETE /documents/{id}` → `202 DeletionRequestOut`

`DocumentOut`: `{id,title,state,created_at,updated_at,version_count,chunk_count,summary_count,answer_count,cache_count}`

## RAG
- `POST /rag/query` `{question,document_ids?,top_k}` → `RagQueryResponse`:
  `{answer, answer_note?, citations:[{label,chunk_artifact_id,document_id,score,snippet}], cache_hit, cache_type:"exact"|"semantic"|null, mode:"llm"|"extractive"|"deterministic", model, latency_ms, answer_artifact_id}`
- `POST /summaries` `{document_id}` → `201 SummaryOut` (existing or new registered summary)
- `GET /summaries/{artifact_id}` → `SummaryOut {artifact_id,document_id,summary_version,content|null,lifecycle_state,claims:[{id,idx,text|null,status}]}`
- `POST /summaries/{artifact_id}/repair` `{deletion_request_id?}` → `{job_id,status:"queued"}` (503/403 if flag disabled)
- `GET /repair-jobs/{job_id}` → `{job_id,status,attempts,last_error}`

## Provenance
- `GET /provenance?root=<artifact_id|document:uuid>&direction=dependants|dependencies&include_transitive&depth(1..12)` →
  `{nodes:[{id,type,document_id,document_version_id,version,lifecycle_state,provenance_status,meta}], edges:[{parent,child,relationship,source_version}]}`
- `GET /provenance/dependencies/{artifact_id}` → `{artifact:{id,type,state},dependencies:[…],dependants:[…]}` (table alternative)

## Deletion center
- `POST /deletion-requests` `{document_id,idempotency_key,repair_enabled}` → `202 DeletionRequestOut`
- `GET /deletion-requests?status&page&page_size` → `DeletionRequestOut[]`
- `GET /deletion-requests/{id}` → `DeletionRequestDetail` adds
  `steps:[{step,status,attempts,error_code,detail,started_at,finished_at}]`,
  `verification:[{check_type,target_label,result,error_code,scope,started_at,finished_at}]`
- `POST /deletion-requests/{id}/retry` → `DeletionRequestOut`
- `GET /deletion-requests/{id}/verification` → `VerificationCheckOut[]`
- `GET /deletion-requests/{id}/repair-candidates` → `RepairCandidateOut[] {summary_artifact_id,document_id,summary_version,total_claims,surviving_supports,surviving_source_docs,repairable}`
- `GET /deletion-requests/{id}/report/export?format=json|csv` → metadata-only download

States: `ACCEPTED → FENCED → DISCOVERING → INVALIDATING → REMOVING → VERIFYING → COMPLETED`
with `RETRY_PENDING | INCOMPLETE | FAILED` carrying `failure_reason`.
`INCOMPLETE` must be visually distinct from `COMPLETED` in the UI.

## Audit
- `GET /audit-events?operation&target_id&from_date&to_date&page` → `AuditEventOut[] {id,type,actor,deletion_request_id,payload,created_at}`

## Evaluation
- `GET /evaluation/scenarios` → `[{name,description}]`
- `POST /evaluation-runs` `{scenario,baseline,seed}` → `202 EvaluationRunOut`
- `GET /evaluation-runs` → list; `GET /evaluation-runs/{id}` → detail
- baselines: `vector_only | broad_conservative | provenance_conservative | provenance_repair`
- `EvaluationRunOut`: `{id,scenario,baseline,seed,status:"queued|running|completed|failed",metrics,counts,config,error,started_at,finished_at}`

## System
- `GET /health/live` → `{status:"ok",checks:{}}`
- `GET /health/ready` → `{status:"ok"|"degraded",checks:{postgres,qdrant,redis}}`
- `GET /system/capabilities` → `{system,academic_title,tagline,is_research_prototype:true,operating_modes,embedding,llm,flags:{selective_repair,semantic_cache,pending_jobs},connectors,boundary[]}`
