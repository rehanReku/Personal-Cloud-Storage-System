# Personal Multi-Cloud Storage Dashboard

**Implementation blueprint — no code**  
**Starting point:** Flask application on EC2 using one Amazon S3 bucket.  
**Purpose:** a one-time personal/college demonstration, not a commercial service.

## Product statement

Build a Flask dashboard that presents files in several manually configured, owner-controlled object-storage locations as one personal library. The owner can browse, upload, download, and delete files; see where every physical copy lives; and demonstrate explicit routing and verified fallback.

The provider remains the source of truth for object bytes and object metadata. A small application database stores the logical inventory, mapping from a dashboard file to one or more physical copies, configuration references, and audit history.

### Success scenario

1. The owner signs in and sees configured locations with health state.
2. They upload a test file through a visible routing rule.
3. They browse/download it from a provider-neutral file list.
4. They can see its provider/location and audit history.
5. With a pre-verified replica and a deliberately unavailable primary, the app downloads the replica and clearly says so.

## Scope, ethics, and assumptions

- No intended paid use; the owner may use only legitimately available free tiers/trials/credits and is responsible for current provider terms and eligibility.
- The app never creates accounts, obtains payment methods, claims trials, automates sign-up, bypasses eligibility, or tries to multiply promotional benefits.
- Buckets/containers and credentials are manually created by the owner before connection.
- First release is single-owner, low traffic, test data only, small files, and no sensitive/irreplaceable data.
- “Folders” are object-key prefixes, not filesystem directories. Cross-provider moves and transactions are not atomic.
- Provider free tiers, quota, egress, billing prerequisites, regions, endpoints, limits, and API details are not assumed stable or equivalent.

### Non-goals

- Public SaaS, multi-tenancy, billing, sharing, collaboration, or unlimited/permanent storage.
- Guaranteed availability/durability, disaster recovery, compliance certification, ransomware protection, or end-to-end encryption.
- Claiming all providers are S3-compatible or free.
- Silent failover to a file with the same name but no verified identity.
- Supporting all eight providers in the first release.

## Architecture evolution

```text
Today
Browser -> Flask on EC2 -> one S3 bucket

Target
Browser -> Flask UI/routes -> StorageService -> Adapter registry -> provider adapters
                                 |                 |-> S3
                                 |                 |-> Azure Blob
                                 |                 |-> Google Cloud Storage
                                 |                 `-> optional adapters
                                 `-> metadata DB + audit log
```

Routes must never call a cloud SDK directly. The service selects a configured location and invokes a provider adapter. The adapter translates provider-specific authentication, calls, metadata, pagination, and errors into a small normalized contract.

## Provider rollout matrix

| Priority | Service | Plan | Provider-specific work to verify manually |
|---|---|---|---|
| 1 | AWS S3 | Preserve/refactor current integration | IAM least privilege, bucket/region, endpoint, actual charges/allowance |
| 2 | Azure Blob Storage | First non-S3 adapter | Storage account/container, Entra/scoped credential method, region/cost |
| 3 | Google Cloud Storage | Second non-S3 adapter | project/bucket, identity credential choice, billing/trial state |
| Optional | Alibaba Cloud OSS | Add one at a time after core contract | endpoint/signature and account/region access |
| Optional | OCI Object Storage | Add one at a time | namespace, compartment, endpoint, auth model |
| Optional | IBM Cloud Object Storage | Add one at a time | IAM/HMAC and endpoint behavior |
| Optional | DigitalOcean Spaces | Add one at a time | endpoint/region, credentials, plan/cost |
| Optional | OVHcloud Object Storage | Add one at a time | current service/API/auth model, endpoint, plan/cost |

Record owner-verified `account_status` as `active`, `trial`, `unknown`, or `disabled`; it is merely informational. Do not code an entitlement checker. Official references for future adapter work: [S3](https://docs.aws.amazon.com/s3/), [Azure Blob](https://learn.microsoft.com/en-us/rest/api/storageservices/blob-service-rest-api), [Google Cloud Storage](https://cloud.google.com/storage/docs/json_api), and [Alibaba OSS](https://www.alibabacloud.com/help/en/oss/developer-reference/description). They establish object APIs, not identical behavior or current eligibility.

## Phased delivery

### Phase 0 — Baseline and safety inventory

**Goal:** reproduce the existing prototype before changing it.

- Document Flask routes, deployment, dependencies, current S3 behavior, bucket/region, authentication state, environment variable names, and IAM policy.
- Use version control, dependency locking, `.env.example` with names only, and a separate development/test prefix or bucket.
- Capture a smoke-test checklist for current upload/download/list behavior.

**Exit:** the original one-bucket application can be run and demonstrated locally and on the existing deployment without revealing credentials.

### Phase 1 — Single-provider hardening

**Goal:** turn the prototype into a safe S3-backed file manager with separable storage logic.

- Split Flask routes/templates from `StorageService` and `S3StorageAdapter`.
- Add owner login, password hashing or existing identity integration, secure sessions, CSRF protection, input validation, upload limits/type policy, safe file-name handling, and friendly errors.
- Add logical file IDs; UI must not depend on raw object paths.
- Implement list/upload/download/metadata/delete-with-confirmation/health-check and audit logging.

**Exit:** no web route imports an AWS SDK; all existing functionality passes through the adapter.

### Phase 2 — Metadata database and configurable locations

**Goal:** make locations editable without storing secrets in the app database.

- Add provider-account/location records, enabled state, priority, capabilities, and last health result.
- Build admin settings to view locations by friendly name; secret values stay in environment variables or approved secret storage.
- Show a unified logical file inventory and physical-copy records.
- Implement read-only reconciliation between one configured bucket/container prefix and the database. Report differences before any corrective action.

**Exit:** a second location can be registered, tested, and disabled without a source-code change or accidental destructive action.

### Phase 3 — Azure and Google adapters

**Goal:** prove the abstraction across materially different APIs.

- Implement Azure Blob Storage using the official Azure Python library, then Google Cloud Storage using its official Python library.
- Start with list, put, head, get, delete, and health checks. Test against fake adapters and manually configured real test locations.
- Normalize only common behavior. Model differences as capabilities rather than hiding them.

**Exit:** a common contract suite passes for S3, Azure Blob, and GCS, with any exceptions documented.

### Phase 4 — Routing, replicas, and controlled fallback

**Goal:** demonstrate multi-cloud routing safely.

- Add transparent policies: fixed destination, category/prefix rule, and ordered healthy-location priority.
- Use deterministic object keys and idempotency tokens for uploads.
- Optional replication copies a *verified* primary to one configured replica, then stores separate verification state.
- Downloads start with the primary. A replica is used only for read requests, only after a retryable primary failure, and only when its copy was verified.
- Deletes are never rerouted automatically. A partial delete is reported as partial failure/degraded state.

**Exit:** simulated primary unavailability produces a visible, auditable replica download—not a silent claim of success.

### Phase 5 — Optional provider adapters

**Goal:** add practical providers only when the owner has legitimate working access.

For OSS, OCI, IBM COS, DigitalOcean Spaces, or OVHcloud Object Storage: complete a provider onboarding worksheet, verify its current official SDK/API/authentication, implement one adapter, run contract and real-location tests, document capabilities/limits, and leave it `experimental` or disabled until it passes. A vendor’s claimed S3 compatibility is not proof that every API feature works; isolate the configuration/adapter and test it.

### Phase 6 — Deployment and presentation

**Goal:** make the project reproducible and assessable.

- Retain EC2 only if it is presently permitted/usable; otherwise demonstrate locally.
- Run Flask behind a production WSGI server and HTTPS-capable proxy with debug disabled.
- Add structured redacted logs, health endpoint, location status cards, CI, manual deployment approval, rollback notes, and a demo dataset/script.

**Exit:** a reviewer can run the fake-adapter demo, understand manual real-provider onboarding, and repeat the final flow.

## Adapter contract and capabilities

Conceptual operations—not fixed code signatures:

| Operation | Input | Normalized result |
|---|---|---|
| `health_check` | location | status, latency, diagnostic code; no mutation |
| `list_objects` | prefix, cursor | summaries and next cursor |
| `put_object` | stream, key, content metadata, idempotency context | object reference, ETag/version if available |
| `head_object` | reference/key | size, content type, checksum/version when available |
| `get_object` | reference/key, optional range | stream and metadata |
| `delete_object` | reference/key | explicit result |
| `copy_object` | source, destination | optional; cross-provider copy may be app-mediated |

Map native errors to `not_found`, `permission_denied`, `authentication_failed`, `rate_limited`, `temporary_unavailable`, `invalid_request`, `conflict`, or `unknown`. Display safe messages to the owner; retain sanitized native diagnostics only in restricted logs.

Each location declares capabilities such as `read`, `write`, `delete`, `list`, `multipart_upload`, `range_read`, `server_side_copy`, `versioning`, `presigned_download`, `checksum_algorithm`, and `object_tags`. The UI offers a feature only where supported.

## Data model

| Entity | Essential fields | Purpose |
|---|---|---|
| `user` | id, login/email, role, password/OIDC reference | Begin with one admin owner |
| `provider_account` | id, provider type, display name, status, credential reference | Non-secret account configuration |
| `storage_location` | account, bucket/container, region/endpoint, prefix, enabled, priority, capabilities | One physical target |
| `routing_policy` | name, match rule, ordered locations, replica count, enabled | Upload selection |
| `logical_file` | UUID, display name, content type, size, checksum, status, creator | User-facing file identity |
| `file_copy` | logical file, location, object key, ETag/version, checksum, state, verified time | One physical object |
| `operation` | type, actor, file, idempotency key, state, times, error category | Audit trail |
| `reconciliation_run` | location, start/end, counts, status/report | Inventory evidence |

Use SQLite for the small/local demo; migrate to PostgreSQL only when a genuine durable/multi-user need exists. Typical copy states: `pending`, `uploading`, `available`, `verification_failed`, `unavailable`, `deleted`. Logical file states: `available`, `degraded`, `unavailable`, `deleted`.

## Core user flows

### Upload

1. Owner selects a file and optional category/routing rule.
2. App validates size/type/name, creates pending logical-file and operation records, and streams while calculating checksum when feasible.
3. Routing selects an enabled eligible location and shows the intended destination.
4. Adapter writes a server-derived key such as `files/<UUID>/<sanitized-name>`.
5. App performs `head_object` verification (size at minimum; checksum/version where supported), creates an available physical copy, and marks the file available.
6. A safe retry may use another policy location only for retryable failures and the same idempotency context. Every attempt is logged.

### Browse/download

The file page shows logical files with current health; file detail shows all copies and audit history. Download resolves a verified available copy, streams it (or uses a short-lived provider URL only if that adapter/security design permits it), and states when a replica was used.

### Delete

The owner confirms all physical copies affected. The app records the operation, deletes each selected copy explicitly, and reports partial cleanup instead of false success. Reconciliation finds leftovers.

### Provider onboarding

The owner manually creates a target and least-privilege credential; supplies non-secret config plus a deployment secret reference; runs a read-only health check; then explicitly confirms a small write/read/delete test. The location stays disabled until successful.

## Routing and fallback rules

- **Fixed:** one selected target.
- **Category/prefix:** explicit demo routing, not cost optimization.
- **Priority healthy:** first enabled, recently healthy target in a defined ordered list.
- **Replica:** copy after primary verification and verify each copy separately.

Do not route by assumed free space, credit, or pricing. A health check is point-in-time only. A fallback requires an authorized read, a verified alternate copy, and a retryable unavailable/temporary primary error. Permission/authentication errors signal configuration trouble and must surface. Use bounded exponential-backoff retries; log every location attempted.

## UI and authentication

Use a single admin account, secure password storage and sessions, or an already available identity provider. Minimum pages: **Sign in**, **Files**, **File details**, **Locations** (health/capabilities but no secrets), **Routing**, and **Operations/Reconciliation**. Use precise labels such as “downloaded from verified S3 replica”; never advertise an “unlimited cloud drive.”

## Security baseline

- Scope cloud permissions to the necessary bucket/container and prefix; never use root/account-owner credentials.
- Keep secrets in deployment environment/secret store; never commit `.env`, keys, headers, or full presigned URLs. Redact logs.
- Use HTTPS, secure/HTTP-only cookies, CSRF controls, rate limits, input validation, conservative upload limits, and server-generated object keys.
- Reject path traversal-like names; do not trust browser MIME type.
- Treat presigned URLs as short-lived bearer credentials, scoped to one action/object.
- Audit actor/action/time/outcome without logging file contents or credentials.
- Scan dependencies and secrets before releases. Warn in docs that provider configuration can generate charges.

## DevOps and tests

Suggested repository areas: `app/` (Flask/UI/service), `storage/` (contract/adapters), `models/` (DB/migrations), `tests/`, `docs/`, and optional `infra/`.

CI sequence: formatting/lint → unit tests → fake-adapter contract tests → dependency/secret scan → opt-in real-provider integration tests with dedicated manually created test prefixes → build → manual deploy approval → smoke test. CI never creates accounts or unapproved resources. Use development/demo/production-like config separation and a tagged-release plus documented database/deploy rollback.

| Test layer | Evidence |
|---|---|
| Unit | routing, state transitions, validation, authorization, error mapping |
| Contract | all adapters conform using fakes/emulators where appropriate |
| Integration | manually configured test location supports list/put/head/get/delete |
| Failure | timeout, access denial, missing object, retry, checksum mismatch, unavailable replica, partial delete |
| Security | anonymous/CSRF denial, secret redaction, upload limit, unauthorized access |
| End-to-end | upload → verify → browse → primary outage simulation → replica download → audit |

## Documentation deliverables

- `README.md`: goal, limitations, local quick start, screenshots.
- `ARCHITECTURE.md`: diagram, flows, schema, adapter contract.
- `PROVIDER_ONBOARDING.md`: per-enabled-provider manual setup, links, permissions, endpoint/region, test/teardown steps.
- `SECURITY.md`, `DEPLOYMENT.md`, `DEMO.md`, and `KNOWN_LIMITATIONS.md`.
- Each provider worksheet records the date checked, source URLs, identity approach, required config **names** (not secrets), capabilities, observed limits, and unresolved questions.

## Handoff interfaces for other AI models

Always supply the repository tree, active phase, this blueprint, and these constraints: **Flask/Python; no account creation/provisioning; no secret values; no free-tier claims; no destructive cloud operation without explicit confirmation; preserve working behavior.**

**Refactor prompt**

> Work on Phase 1 only. Refactor the existing Flask+S3 prototype so routes use a provider-neutral StorageService and S3 adapter. Do not deploy, change cloud resources, create accounts, expose secrets, or add providers. First propose file changes, order, and tests; preserve upload/download behavior.

**Adapter prompt**

> Plan/implement the `<PROVIDER>` adapter for the existing contract: health_check, list_objects, put_object, head_object, get_object, delete_object, capabilities, and normalized errors. Use only current official documentation and SDKs. Do not infer S3 compatibility or free-tier details, create resources, or invent endpoints/authentication. First list configuration fields, open questions, capability gaps, and fake/contract tests.

**Security-review prompt**

> Review this single-owner Flask multi-cloud storage dashboard. Find concrete credential/IAM, session/CSRF, object-key, upload/download, logging, presigned URL, CI, and error-disclosure risks. Do not alter cloud accounts. Return prioritized findings with affected component and safe remediation.

**Test prompt**

> Design tests for Phase `<N>`. Prefer deterministic unit and fake-adapter contract tests. Real-cloud tests must be opt-in, use manually configured test prefixes, remove only test-created objects, and never provision accounts. Flag all human credential/provider verification requirements.

**Deployment/docs prompt**

> Prepare Phase 6 runbooks and demo assets. Preserve the non-commercial one-time-demo constraint; do not say a provider is free or permanent. Include local/demo deployment, secret variable names only, CI, rollback, and a visible verified-replica fallback demonstration. Do not deploy unless explicitly asked.

## Owner decisions needed before building

1. Which accounts/providers are actually active and lawful to use now (recommended initial set: S3, Azure Blob, GCS).
2. Single owner only, or real multi-user access.
3. Maximum file size/types and demo dataset; recommended: small, non-sensitive files only.
4. Placement-only versus verified replication; replication adds complexity and possible transfer/cost exposure.
5. Local demonstration versus EC2 deployment, based on current usable account status.
6. Allowed credential approach per provider and the human responsible for manual creation/revocation.

## Definition of done

Complete when the core flow works through S3 plus at least two materially different providers; targets were manually provisioned; unified inventory/health is visible; one verified fallback demo is reproducible; secrets are absent from the repo; tests/runbooks are complete; and documentation clearly says availability, retention, and cost are not guaranteed. Other providers are optional enhancements. If a trial or account ends, disable that location and document it—do not work around provider rules.



#npx kill-port 5000
