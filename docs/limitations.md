# Threat model, scope & known limitations

## What TraceVault's guarantees cover

Only operations the prototype can **observe, control, and test**, within the
declared, registered, controlled components (PostgreSQL registry, Qdrant
collection, Redis cache, application pathways it serves) and the tested
application pathways (document/chunk/summary/answer/cache retrieval, exports,
graph, audit).

## Explicitly OUT of scope (never claimed as deleted)

* unmanaged backups, storage snapshots, database WAL archives
* external provider telemetry, request logs, analytics
* replicas or stores without an integrated connector
* previously disclosed answers: screenshots, copies, human memory, unmanaged
  clients
* model weights / model unlearning — TraceVault controls stored RAG artifacts,
  NOT what a model has learned
* forensic byte erasure on physical media
* legal compliance (GDPR/DPDP "right to erasure" conformance), certified
  security, established patentability

## Outcome vocabulary (used everywhere: UI, API, reports)

1. **Application access blocked** — registry/tombstone blocking (logical)
2. **Stored records removed** — through supported connectors (physical, per-connector acknowledged)
3. **Supported-path verification passed** — evidence from specified checks at a recorded time
4. **Coverage incomplete / outside scope** — explicit, with reasons

These are distinct; a deletion is `COMPLETED` only when every required in-scope
removal and verification check passed. Verification is NOT proof that a fact can
never reappear — delayed reappearance checks exist precisely because of this.

## Security posture (prototype-appropriate)

* local session auth (PBKDF2 + HMAC-signed HttpOnly cookies, SameSite=Lax,
  CSRF custom-header requirement), viewer/operator roles
* parameterized SQL via SQLAlchemy; content-free error envelopes; no raw stack
  traces or document content in responses/logs
* uploads: size/type validation, UTF-8 decoding, PDFs parsed via PyMuPDF
  (scanned/image-only PDFs rejected with an explanation — OCR is NOT implemented)
* prompt-injection defense: document content is data, never instructions —
  red-team content in documents cannot alter deletion policy (deterministic
  protocol controls publication; LLM output is never the deletion authority)
* no secrets in the frontend bundle; remote inference is opt-in and off by
  default; infrastructure ports bind to loopback
* audit log is append-only through application permissions and metadata-only —
  it is NOT called tamper-proof

## Known limitations (prototype)

* single default workspace for the demo UI; evaluation runs in isolated
  workspaces (workspace-scoped authorization is enforced; a full multi-tenant
  surface is future work)
* transitive closure is a bounded BFS (depth 12) — sound for prototype scale
* semantic cache is experimental, flag-gated, and disabled by default
* OCR for scanned PDFs: not implemented
* bounded BFS + breadth limits on the provenance graph view (pagination by depth)
* `vector_only` baseline exists ONLY to demonstrate the weakness; it is not a
  safe operating mode and never runs in the demo workspace
*Redis expiry is never a substitute for deletion invalidation; cache TTLs are
an availability feature only
