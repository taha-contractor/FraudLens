# FraudLens — API Design

## 1. Overview

FraudLens uses a **RESTful API** to connect the React frontend with the Node.js backend.

The API provides access to:

* Case management
* Documents
* Transactions and accounts
* Entities and relationships
* Evidence
* Investigation and AI-assisted analysis
* Findings and reports
* Audit logs

The backend is responsible for authentication, authorization, validation, case isolation, business logic, and communication with MongoDB and analytical/AI components.

---

## 2. API Architecture

```text
React Frontend
      │
      ▼
REST API
Node.js + Express
      │
 ┌────┼──────────────┐
 ▼    ▼              ▼
MongoDB   Python ML   Document/RAG
          Analytics   Processing
                │
                ▼
          AI Investigation
```

The Node.js backend acts as the main application and API layer.

ML, document processing, retrieval, and AI components are treated as **modular components**, not mandatory independent microservices.

---

## 3. API Versioning

All APIs use the following base path:

```text
/api/v1
```

Example:

```text
GET /api/v1/cases
```

Versioning allows the API to evolve without breaking existing clients.

---

# 4. Authentication & Authorization

FraudLens uses authenticated users with role-based access.

### Roles

| Role         | Purpose                                   |
| ------------ | ----------------------------------------- |
| ADMIN        | Manage users and system-level operations  |
| INVESTIGATOR | Create and investigate cases              |
| REVIEWER     | Review findings and investigation results |

### Authentication APIs

| Method | Endpoint                | Purpose          |
| ------ | ----------------------- | ---------------- |
| POST   | `/api/v1/auth/register` | Register user    |
| POST   | `/api/v1/auth/login`    | Login            |
| GET    | `/api/v1/auth/me`       | Get current user |

Protected endpoints require authentication.

---

# 5. Case APIs

Cases are the central boundary of the system.

| Method | Endpoint                        | Purpose                   |
| ------ | ------------------------------- | ------------------------- |
| POST   | `/api/v1/cases`                 | Create case               |
| GET    | `/api/v1/cases`                 | List accessible cases     |
| GET    | `/api/v1/cases/:caseId`         | Get case                  |
| PATCH  | `/api/v1/cases/:caseId`         | Update case               |
| GET    | `/api/v1/cases/:caseId/summary` | Get investigation summary |

Example:

```http
GET /api/v1/cases/CASE_ID
```

All case-related resources must belong to the requested case.

---

# 6. Document APIs

Documents provide investigation evidence such as statements, reports, and other case files.

| Method | Endpoint                                               | Purpose               |
| ------ | ------------------------------------------------------ | --------------------- |
| POST   | `/api/v1/cases/:caseId/documents`                      | Upload document       |
| GET    | `/api/v1/cases/:caseId/documents`                      | List documents        |
| GET    | `/api/v1/cases/:caseId/documents/:documentId`          | Get document metadata |
| GET    | `/api/v1/cases/:caseId/documents/:documentId/status`   | Processing status     |
| GET    | `/api/v1/cases/:caseId/documents/:documentId/evidence` | Extracted evidence    |

Documents are processed through PDF/text extraction and OCR when required.

---

# 7. Transaction & Account APIs

### Transactions

| Method | Endpoint                                                 | Purpose                  |
| ------ | -------------------------------------------------------- | ------------------------ |
| POST   | `/api/v1/cases/:caseId/transactions`                     | Add transaction          |
| POST   | `/api/v1/cases/:caseId/transactions/import`              | Import transactions      |
| GET    | `/api/v1/cases/:caseId/transactions`                     | List/search transactions |
| GET    | `/api/v1/cases/:caseId/transactions/:transactionId`      | Get transaction          |
| POST   | `/api/v1/cases/:caseId/transactions/analyze`             | Analyze transactions     |
| GET    | `/api/v1/cases/:caseId/transactions/:transactionId/risk` | Get risk information     |
| GET    | `/api/v1/cases/:caseId/transactions/timeline`            | Transaction timeline     |

### Accounts

| Method | Endpoint                                                 | Purpose              |
| ------ | -------------------------------------------------------- | -------------------- |
| POST   | `/api/v1/cases/:caseId/accounts`                         | Create account       |
| GET    | `/api/v1/cases/:caseId/accounts`                         | List accounts        |
| GET    | `/api/v1/cases/:caseId/accounts/:accountId`              | Get account          |
| GET    | `/api/v1/cases/:caseId/accounts/:accountId/transactions` | Account transactions |
| GET    | `/api/v1/cases/:caseId/accounts/:accountId/activity`     | Account activity     |

Transaction analysis may use the Python ML/analytics component.

---

# 8. Entity & Relationship APIs

Fraud investigations require identifying people, companies, accounts, banks, merchants and other entities.

### Entities

| Method | Endpoint                                                 | Purpose                         |
| ------ | -------------------------------------------------------- | ------------------------------- |
| POST   | `/api/v1/cases/:caseId/entities`                         | Create entity                   |
| GET    | `/api/v1/cases/:caseId/entities`                         | Search/list entities            |
| GET    | `/api/v1/cases/:caseId/entities/:entityId`               | Get entity                      |
| GET    | `/api/v1/cases/:caseId/entities/:entityId/relationships` | Entity relationships            |
| GET    | `/api/v1/cases/:caseId/entities/:entityId/transactions`  | Related transactions            |
| POST   | `/api/v1/cases/:caseId/entities/resolve`                 | Resolve possible entity matches |

### Relationships

| Method | Endpoint                                    | Purpose               |
| ------ | ------------------------------------------- | --------------------- |
| POST   | `/api/v1/cases/:caseId/relationships`       | Create relationship   |
| GET    | `/api/v1/cases/:caseId/relationships`       | List relationships    |
| GET    | `/api/v1/cases/:caseId/relationships/graph` | Get relationship view |

A dedicated graph database is **not required** for the initial implementation.

---

# 9. Fund-Flow API

Fund-flow analysis helps trace money between accounts and entities.

```http
GET /api/v1/cases/:caseId/fund-flow
```

Possible parameters include:

```text
sourceAccount
targetAccount
startDate
endDate
maxDepth
```

The API returns the relevant transaction paths and connected accounts/entities.

---

# 10. Evidence APIs

Evidence connects investigation conclusions to their underlying sources.

| Method | Endpoint                                     | Purpose         |
| ------ | -------------------------------------------- | --------------- |
| GET    | `/api/v1/cases/:caseId/evidence`             | List evidence   |
| GET    | `/api/v1/cases/:caseId/evidence/:evidenceId` | Get evidence    |
| GET    | `/api/v1/cases/:caseId/evidence/search`      | Search evidence |

Evidence may originate from:

* Documents
* Transactions
* Accounts
* Entities
* Relationships
* ML/model signals
* Timelines
* Fund-flow analysis

The system should preserve the source of evidence so that AI-generated results can be verified.

---

# 11. Investigation & AI APIs

The investigation API provides a controlled interface for AI-assisted investigation.

| Method | Endpoint                                                | Purpose             |
| ------ | ------------------------------------------------------- | ------------------- |
| POST   | `/api/v1/cases/:caseId/investigations`                  | Start investigation |
| GET    | `/api/v1/cases/:caseId/investigations`                  | List investigations |
| GET    | `/api/v1/cases/:caseId/investigations/:investigationId` | Get investigation   |

The AI can use controlled backend tools such as:

```text
searchDocuments()
getDocumentEvidence()
searchTransactions()
getAccountHistory()
findEntity()
findRelationships()
traceFundFlow()
buildTimeline()
createFinding()
```

The AI does **not** receive unrestricted database access.

AI responses should be grounded in evidence available within the selected case.

---

# 12. Findings APIs

Findings represent investigation conclusions that can be reviewed by an investigator.

| Method | Endpoint                                             | Purpose                 |
| ------ | ---------------------------------------------------- | ----------------------- |
| POST   | `/api/v1/cases/:caseId/findings`                     | Create finding          |
| GET    | `/api/v1/cases/:caseId/findings`                     | List findings           |
| GET    | `/api/v1/cases/:caseId/findings/:findingId`          | Get finding             |
| PATCH  | `/api/v1/cases/:caseId/findings/:findingId/review`   | Review finding          |
| GET    | `/api/v1/cases/:caseId/findings/:findingId/evidence` | Get supporting evidence |

### Finding Status

```text
PENDING
UNDER_REVIEW
SUPPORTED
REJECTED
REQUIRES_MORE_EVIDENCE
```

The AI does not make the final investigation decision. The investigator/reviewer remains responsible for reviewing findings.

---

# 13. Report APIs

Reports summarize investigation results.

| Method | Endpoint                                           | Purpose         |
| ------ | -------------------------------------------------- | --------------- |
| POST   | `/api/v1/cases/:caseId/reports`                    | Generate report |
| GET    | `/api/v1/cases/:caseId/reports/:reportId`          | Get report      |
| GET    | `/api/v1/cases/:caseId/reports/:reportId/download` | Download report |

Reports may contain:

* Case summary
* Important entities
* Transaction analysis
* Fund-flow results
* Timeline
* Findings
* Supporting evidence
* Investigator review

---

# 14. API Security

Security is enforced by the backend.

### Main controls

* Authentication
* Role-based authorization
* Case-level access control
* Input validation
* File type and size validation
* Rate limiting
* Secure HTTP headers
* CORS configuration
* Protected database access
* Environment-based secrets
* Audit logging

### Case Isolation

Every case-scoped request follows:

```text
Request
   ↓
Authenticate
   ↓
Authorize
   ↓
Validate case access
   ↓
Validate resource belongs to case
   ↓
Execute operation
```

The frontend and AI system are **not trusted security boundaries**.

---

# 15. Error Handling

The API uses a consistent error structure.

Example:

```json
{
  "success": false,
  "message": "Transaction not found",
  "errorCode": "TRANSACTION_NOT_FOUND"
}
```

Common HTTP responses:

| Status | Meaning                 |
| ------ | ----------------------- |
| 200    | Successful request      |
| 201    | Resource created        |
| 400    | Invalid request         |
| 401    | Authentication required |
| 403    | Access denied           |
| 404    | Resource not found      |
| 409    | Conflict                |
| 422    | Validation error        |
| 500    | Internal server error   |

---

# 16. API ↔ Database Mapping

| API Resource   | MongoDB Collection |
| -------------- | ------------------ |
| Users          | `users`            |
| Cases          | `cases`            |
| Documents      | `documents`        |
| Transactions   | `transactions`     |
| Accounts       | `accounts`         |
| Entities       | `entities`         |
| Relationships  | `relationships`    |
| Evidence       | `evidence`         |
| Investigations | `investigations`   |
| Findings       | `findings`         |
| Audit Logs     | `auditLogs`        |

Most case-related collections contain:

```text
caseId
```

to maintain case isolation.

---

# 17. Implementation Priority

Implementation will be incremental rather than building the complete API at once.

### Phase 1 — Foundation

* Authentication
* Cases
* Authorization
* Case isolation

### Phase 2 — Core Data

* Transactions
* CSV import
* Accounts
* Documents

### Phase 3 — Investigation Data

* Entities
* Relationships
* Evidence

### Phase 4 — Intelligence

* Transaction analysis
* Fund-flow
* Investigations
* RAG
* AI tools
* Findings

### Phase 5 — Final Features

* Reports
* Audit logs
* Review workflow
* Security testing
* Final integration

---

# 18. API Design Principles

FraudLens follows these principles:

1. **Case-centered** — investigations are organized around cases.
2. **Secure by default** — authorization is enforced by the backend.
3. **Evidence-grounded** — important AI outputs should reference evidence.
4. **Human-in-the-loop** — AI assists investigators rather than replacing them.
5. **Modular** — ML, RAG and document processing can evolve independently.
6. **B.Tech appropriate** — avoid unnecessary enterprise-level complexity.
7. **Traceable** — important actions and investigation activities are auditable.

---

## Next Stage

The next step is to map this API design against the **actual FraudLens backend codebase**.

Before implementing new endpoints:

```text
API Design
    ↓
Inspect Existing Code
    ↓
Identify What Already Exists
    ↓
Modify / Add One Module
    ↓
Test
    ↓
Security Check
    ↓
Git Commit
    ↓
Next Module
```