# FraudLens — API Architecture & Endpoint Design

## 1. Overview

This document defines the API architecture for FraudLens, an evidence-grounded AI financial fraud investigation system.

The API layer connects the FraudLens frontend with the backend application services, database, analytical services, document processing pipeline, investigation tools, and reporting components.

The API design is derived from:

* FraudLens research findings
* Identified research gaps
* Finalized system requirements
* System architecture
* Database and data model design

The API is designed around a **case-centered investigation model**.

All case-scoped operations must enforce authentication, authorization, and case isolation at the backend.

---

# 2. API Architecture Objectives

The API architecture should:

1. Provide a consistent interface between frontend and backend.
2. Support case-centered investigation workflows.
3. Enforce authentication and authorization.
4. Enforce case-level data isolation.
5. Support document and transaction ingestion.
6. Support financial analysis.
7. Support entity and relationship analysis.
8. Support evidence retrieval.
9. Support AI investigation tools.
10. Support investigator review of findings.
11. Support report generation.
12. Support audit logging.
13. Provide clear validation and error handling.
14. Preserve compatibility with existing working backend functionality.
15. Allow future integration with ML, RAG and graph services.

---

# 3. API Style

FraudLens will initially use a **REST API**.

Communication:

```text
Frontend
   │
   │ HTTP / HTTPS
   ▼
REST API
   │
   ▼
Node.js Backend
```

JSON will be the primary format for API request and response bodies.

Multipart form-data will be used for file uploads.

---

# 4. Base URL

The development API may use:

```text
/api
```

Example:

```text
/api/cases
/api/transactions
/api/documents
```

The exact development host and port remain environment-specific.

Production deployments should use HTTPS.

---

# 5. API Versioning

The API should support versioning.

Recommended structure:

```text
/api/v1
```

Example:

```text
/api/v1/cases
/api/v1/transactions
/api/v1/documents
```

Versioning allows future API changes without immediately breaking existing clients.

---

# 6. Authentication Model

Authenticated endpoints should require a valid access token.

Conceptual request:

```http
Authorization: Bearer <access-token>
```

Authentication flow:

```text
User
 │
 ▼
Login
 │
 ▼
Authentication
 │
 ▼
Access Token
 │
 ▼
Frontend
 │
 ▼
Protected API
 │
 ▼
Authentication Middleware
```

The exact authentication mechanism can be finalized during implementation.

---

# 7. Authorization Model

Authentication answers:

> Who is the user?

Authorization answers:

> What is this user allowed to access?

FraudLens should use:

* Role-Based Access Control
* Case-Level Authorization

Conceptually:

```text
Request
   │
   ▼
Authentication
   │
   ▼
User Identity
   │
   ▼
Role Check
   │
   ▼
Case Permission Check
   │
   ▼
Controller / Service
```

---

# 8. API Security Principle

The backend is the security boundary.

The frontend must not be trusted to enforce:

* user roles
* case permissions
* case isolation
* tool authorization

These checks must occur on the backend.

---

# 9. API Resource Structure

The main API resources are:

```text
Authentication
Cases
Documents
Transactions
Accounts
Entities
Relationships
Evidence
Investigations
Findings
Reports
Audit Logs
```

Conceptually:

```text
/api/v1
│
├── auth
├── cases
├── documents
├── transactions
├── accounts
├── entities
├── relationships
├── evidence
├── investigations
├── findings
├── reports
└── audit-logs
```

---

# 10. Authentication Endpoints

## 10.1 Register User

```http
POST /api/v1/auth/register
```

Purpose:

Creates a new application user.

Request:

```json
{
  "name": "Investigator Name",
  "email": "investigator@example.com",
  "password": "password"
}
```

Response:

```json
{
  "message": "User registered successfully"
}
```

User registration permissions should be controlled appropriately in production.

---

# 11. Login

```http
POST /api/v1/auth/login
```

Purpose:

Authenticates a user.

Request:

```json
{
  "email": "investigator@example.com",
  "password": "password"
}
```

Response concept:

```json
{
  "accessToken": "<token>",
  "user": {
    "id": "<user-id>",
    "name": "Investigator Name",
    "role": "INVESTIGATOR"
  }
}
```

---

# 12. Current User

```http
GET /api/v1/auth/me
```

Purpose:

Returns information about the authenticated user.

Response:

```json
{
  "id": "<user-id>",
  "name": "Investigator Name",
  "email": "investigator@example.com",
  "role": "INVESTIGATOR"
}
```

---

# 13. Cases API

Cases are the central API resource.

```text
/api/v1/cases
```

---

# 14. Create Case

```http
POST /api/v1/cases
```

Purpose:

Creates a new investigation case.

Request:

```json
{
  "caseNumber": "CASE-2026-014",
  "title": "Suspicious Fund Transfer Investigation",
  "description": "Investigation into unusual financial activity"
}
```

Response:

```json
{
  "id": "<case-id>",
  "caseNumber": "CASE-2026-014",
  "title": "Suspicious Fund Transfer Investigation",
  "status": "OPEN"
}
```

The authenticated user should become the creator or investigator according to application rules.

---

# 15. List Cases

```http
GET /api/v1/cases
```

Purpose:

Returns cases accessible to the authenticated user.

The endpoint must not return cases belonging to unauthorized users.

---

# 16. Get Case

```http
GET /api/v1/cases/:caseId
```

Purpose:

Returns details of a specific case.

Authorization must verify that the user has access to the requested case.

---

# 17. Update Case

```http
PATCH /api/v1/cases/:caseId
```

Purpose:

Updates case information.

Example:

```json
{
  "title": "Updated Investigation Title",
  "status": "UNDER_INVESTIGATION"
}
```

---

# 18. Delete / Archive Case

```http
DELETE /api/v1/cases/:caseId
```

For investigation systems, hard deletion should be carefully controlled.

The preferred prototype behavior may be logical archiving rather than immediately destroying investigation data.

---

# 19. Case Dashboard

```http
GET /api/v1/cases/:caseId/summary
```

Purpose:

Returns a summary of the investigation.

Potential response information:

```text
Case status
Document count
Transaction count
Account count
Entity count
Relationship count
Open findings
Reviewed findings
Investigation activity
Risk indicators
```

Example:

```json
{
  "caseId": "<case-id>",
  "documents": 12,
  "transactions": 10452,
  "accounts": 43,
  "entities": 76,
  "relationships": 121,
  "openFindings": 8
}
```

---

# 20. Documents API

Base path:

```text
/api/v1/cases/:caseId/documents
```

Documents are always associated with a case.

---

# 21. Upload Document

```http
POST /api/v1/cases/:caseId/documents
```

Content type:

```text
multipart/form-data
```

Possible fields:

```text
file
documentType
description
```

Processing flow:

```text
Upload
  │
  ▼
Validation
  │
  ▼
Document Metadata
  │
  ▼
Storage
  │
  ▼
Processing
```

---

# 22. List Case Documents

```http
GET /api/v1/cases/:caseId/documents
```

Returns only documents belonging to the requested authorized case.

---

# 23. Get Document

```http
GET /api/v1/cases/:caseId/documents/:documentId
```

Returns document metadata.

---

# 24. Document Processing Status

```http
GET /api/v1/cases/:caseId/documents/:documentId/status
```

Example:

```json
{
  "documentId": "<document-id>",
  "status": "INDEXED",
  "pageCount": 18
}
```

---

# 25. Document Evidence

```http
GET /api/v1/cases/:caseId/documents/:documentId/evidence
```

Returns evidence extracted from the document.

---

# 26. Transactions API

Base path:

```text
/api/v1/cases/:caseId/transactions
```

Transactions are always scoped to the case.

---

# 27. Create Transaction

```http
POST /api/v1/cases/:caseId/transactions
```

Example:

```json
{
  "transactionId": "TXN-001",
  "accountId": "<account-id>",
  "destinationAccountId": "<destination-account-id>",
  "amount": 50000,
  "currency": "INR",
  "transactionType": "TRANSFER",
  "merchant": "Example Merchant",
  "timestamp": "2026-09-29T10:30:00Z"
}
```

---

# 28. List Transactions

```http
GET /api/v1/cases/:caseId/transactions
```

Potential query parameters:

```text
page
limit
accountId
riskLevel
transactionType
status
startDate
endDate
minAmount
maxAmount
```

Example:

```text
GET /api/v1/cases/:caseId/transactions?accountId=ACCOUNT-001
```

---

# 29. Get Transaction

```http
GET /api/v1/cases/:caseId/transactions/:transactionId
```

Returns transaction details.

---

# 30. Transaction Analysis

```http
POST /api/v1/cases/:caseId/transactions/analyze
```

Purpose:

Triggers or requests analytical processing for transactions.

Potential analysis:

* risk scoring
* anomaly detection
* behavioral analysis
* temporal analysis

The exact implementation may call the Python analytical service.

---

# 31. Transaction Risk

```http
GET /api/v1/cases/:caseId/transactions/:transactionId/risk
```

Returns analytical risk information.

Example:

```json
{
  "transactionId": "TXN-001",
  "riskLevel": "HIGH",
  "fraudProbability": 0.82,
  "signals": [
    "HIGH_VALUE",
    "BEHAVIORAL_DEVIATION"
  ]
}
```

The response must make clear that model output is an analytical signal and not an automatic fraud determination.

---

# 32. Transaction Timeline

```http
GET /api/v1/cases/:caseId/transactions/timeline
```

Potential parameters:

```text
accountId
startDate
endDate
```

Purpose:

Returns chronological transaction activity.

---

# 33. Accounts API

Base path:

```text
/api/v1/cases/:caseId/accounts
```

---

# 34. Create Account

```http
POST /api/v1/cases/:caseId/accounts
```

Example:

```json
{
  "accountNumberMasked": "XXXXXX1234",
  "accountType": "BANK_ACCOUNT",
  "bankEntityId": "<entity-id>",
  "currency": "INR"
}
```

---

# 35. List Accounts

```http
GET /api/v1/cases/:caseId/accounts
```

---

# 36. Get Account

```http
GET /api/v1/cases/:caseId/accounts/:accountId
```

---

# 37. Account Transaction History

```http
GET /api/v1/cases/:caseId/accounts/:accountId/transactions
```

Purpose:

Returns transaction history for an account.

Potential query parameters:

```text
startDate
endDate
transactionType
riskLevel
```

---

# 38. Account Activity Summary

```http
GET /api/v1/cases/:caseId/accounts/:accountId/activity
```

Potential output:

```text
Total transactions
Total inflow
Total outflow
Average transaction
Maximum transaction
Activity periods
Risk signals
```

---

# 39. Entities API

Base path:

```text
/api/v1/cases/:caseId/entities
```

---

# 40. Create Entity

```http
POST /api/v1/cases/:caseId/entities
```

Example:

```json
{
  "entityType": "COMPANY",
  "name": "ABC Private Limited",
  "aliases": [
    "ABC Pvt Ltd"
  ]
}
```

---

# 41. List Entities

```http
GET /api/v1/cases/:caseId/entities
```

Potential filters:

```text
entityType
name
resolutionStatus
```

---

# 42. Get Entity

```http
GET /api/v1/cases/:caseId/entities/:entityId
```

---

# 43. Entity Relationships

```http
GET /api/v1/cases/:caseId/entities/:entityId/relationships
```

Returns relationships connected to the entity.

---

# 44. Entity Transactions

```http
GET /api/v1/cases/:caseId/entities/:entityId/transactions
```

Returns transactions associated with the entity through linked accounts or relationships.

---

# 45. Entity Resolution

```http
POST /api/v1/cases/:caseId/entities/resolve
```

Purpose:

Attempts to identify records that may represent the same real-world entity.

Example:

```json
{
  "entityIds": [
    "<entity-id-1>",
    "<entity-id-2>"
  ]
}
```

Response should include:

* matching score
* matching signals
* possible conflicts
* review status

Entity resolution should not automatically merge records without appropriate validation.

---

# 46. Relationships API

Base path:

```text
/api/v1/cases/:caseId/relationships
```

---

# 47. Create Relationship

```http
POST /api/v1/cases/:caseId/relationships
```

Example:

```json
{
  "sourceType": "ENTITY",
  "sourceId": "<entity-a>",
  "relationshipType": "OWNS",
  "targetType": "ACCOUNT",
  "targetId": "<account-a>"
}
```

---

# 48. List Relationships

```http
GET /api/v1/cases/:caseId/relationships
```

Potential filters:

```text
sourceId
targetId
relationshipType
```

---

# 49. Relationship Graph

```http
GET /api/v1/cases/:caseId/graph
```

Purpose:

Returns case-scoped nodes and relationships required for graph visualization or graph analysis.

The response should contain only authorized case data.

---

# 50. Fund-Flow API

```http
GET /api/v1/cases/:caseId/fund-flow
```

Potential parameters:

```text
accountId
transactionId
maxDepth
startDate
endDate
```

Example:

```text
GET /api/v1/cases/:caseId/fund-flow?accountId=ACCOUNT-001&maxDepth=4
```

---

# 51. Fund-Flow Response

Conceptually:

```json
{
  "sourceAccount": "ACCOUNT-001",
  "paths": [
    {
      "accounts": [
        "ACCOUNT-001",
        "ACCOUNT-002",
        "ACCOUNT-003"
      ],
      "transactions": [
        "TXN-001",
        "TXN-002"
      ]
    }
  ]
}
```

Each path must remain traceable to its underlying transactions.

---

# 52. Evidence API

Base path:

```text
/api/v1/cases/:caseId/evidence
```

---

# 53. List Evidence

```http
GET /api/v1/cases/:caseId/evidence
```

Potential filters:

```text
evidenceType
sourceType
documentId
transactionId
entityId
```

---

# 54. Get Evidence

```http
GET /api/v1/cases/:caseId/evidence/:evidenceId
```

Returns evidence metadata and provenance.

Example:

```json
{
  "id": "<evidence-id>",
  "documentId": "<document-id>",
  "pageNumber": 12,
  "section": "Transaction Details",
  "sourceText": "..."
}
```

---

# 55. Evidence Search

```http
GET /api/v1/cases/:caseId/evidence/search
```

Potential query:

```text
q
documentId
page
evidenceType
```

---

# 56. Investigation API

Base path:

```text
/api/v1/cases/:caseId/investigations
```

This API provides the interface for investigator queries and AI-assisted investigation.

---

# 57. Create Investigation Query

```http
POST /api/v1/cases/:caseId/investigations
```

Request:

```json
{
  "query": "Trace the movement of funds from Account A."
}
```

The backend should create an investigation record.

---

# 58. Investigation Processing

Conceptual flow:

```text
Investigator Query
       │
       ▼
POST /investigations
       │
       ▼
Investigation Service
       │
       ▼
AI Investigation Agent
       │
       ├── searchTransactions()
       ├── searchDocuments()
       ├── findEntity()
       ├── findRelationships()
       ├── traceFundFlow()
       └── buildTimeline()
       │
       ▼
Evidence / Analytical Results
       │
       ▼
Investigation Response
```

---

# 59. Investigation Result

Example:

```json
{
  "investigationId": "<investigation-id>",
  "query": "Trace the movement of funds from Account A.",
  "summary": "The investigation identified a multi-step transfer path.",
  "evidenceIds": [
    "<evidence-1>",
    "<evidence-2>"
  ],
  "transactionIds": [
    "TXN-001",
    "TXN-002"
  ],
  "uncertainties": [],
  "status": "COMPLETED"
}
```

The final response should distinguish retrieved evidence from AI-generated interpretation.

---

# 60. Investigation History

```http
GET /api/v1/cases/:caseId/investigations
```

Returns previous investigation sessions for the authorized case.

---

# 61. Get Investigation

```http
GET /api/v1/cases/:caseId/investigations/:investigationId
```

Returns:

* query
* tool calls
* evidence references
* analytical outputs
* AI response
* status
* timestamps

---

# 62. AI Investigation Tool Architecture

The API should expose controlled backend functions to the AI agent.

Conceptually:

```text
AI Agent
   │
   ├── searchDocuments()
   ├── getDocumentEvidence()
   ├── searchTransactions()
   ├── getAccountHistory()
   ├── findEntity()
   ├── findRelationships()
   ├── traceFundFlow()
   ├── buildTimeline()
   └── createFinding()
```

These are **internal authorized tools**, not unrestricted database functions.

---

# 63. Tool Authorization

Every AI tool request should pass through authorization.

```text
AI Agent
   │
   ▼
Tool Request
   │
   ▼
Validate Case ID
   │
   ▼
Verify User Permission
   │
   ▼
Validate Parameters
   │
   ▼
Execute Case-Scoped Query
   │
   ▼
Return Result
```

The LLM itself should not decide whether it is authorized to access a case.

---

# 64. Findings API

Base path:

```text
/api/v1/cases/:caseId/findings
```

---

# 65. Create Finding

```http
POST /api/v1/cases/:caseId/findings
```

Example:

```json
{
  "title": "Unusual Transaction Sequence",
  "claim": "The account shows a sequence of rapid transfers requiring investigation.",
  "transactionIds": [
    "TXN-001",
    "TXN-002"
  ],
  "evidenceIds": [
    "<evidence-1>"
  ],
  "analyticalSignals": [
    {
      "signalType": "HIGH_VELOCITY",
      "description": "Multiple transfers occurred within a short period."
    }
  ]
}
```

---

# 66. List Findings

```http
GET /api/v1/cases/:caseId/findings
```

Potential filters:

```text
status
createdBy
entityId
riskLevel
```

---

# 67. Get Finding

```http
GET /api/v1/cases/:caseId/findings/:findingId
```

---

# 68. Review Finding

```http
PATCH /api/v1/cases/:caseId/findings/:findingId/review
```

Example:

```json
{
  "status": "UNDER_REVIEW",
  "reviewNotes": "Additional account documentation required."
}
```

Possible review states:

```text
OPEN
UNDER_REVIEW
CONFIRMED
REJECTED
FOLLOW_UP_REQUIRED
```

The meaning of `CONFIRMED` must represent investigator review, not merely model prediction.

---

# 69. Finding Evidence

```http
GET /api/v1/cases/:caseId/findings/:findingId/evidence
```

Returns supporting evidence associated with the finding.

---

# 70. Reports API

Base path:

```text
/api/v1/cases/:caseId/reports
```

---

# 71. Generate Report

```http
POST /api/v1/cases/:caseId/reports
```

Purpose:

Generates an investigation report using case data and reviewed findings.

The report should use:

* verified investigation information
* evidence
* analytical signals
* investigator-reviewed findings

It should not simply reproduce raw AI output.

---

# 72. Get Report

```http
GET /api/v1/cases/:caseId/reports/:reportId
```

Returns report metadata or generated report content depending on implementation.

---

# 73. Download Report

```http
GET /api/v1/cases/:caseId/reports/:reportId/download
```

The exact output format may include:

```text
PDF
DOCX
JSON
```

depending on implementation requirements.

---

# 74. Audit Logs API

Base path:

```text
/api/v1/cases/:caseId/audit-logs
```

Access should be restricted to authorized roles.

---

# 75. List Audit Logs

```http
GET /api/v1/cases/:caseId/audit-logs
```

Potential filters:

```text
userId
action
resourceType
startDate
endDate
```

---

# 76. API Error Structure

API errors should use a consistent structure.

Example:

```json
{
  "error": {
    "code": "CASE_ACCESS_DENIED",
    "message": "You do not have permission to access this case."
  }
}
```

---

# 77. Suggested HTTP Status Codes

| Status | Meaning                                          |
| ------ | ------------------------------------------------ |
| `200`  | Successful request                               |
| `201`  | Resource created                                 |
| `204`  | Successful request with no response body         |
| `400`  | Invalid request                                  |
| `401`  | Authentication required / invalid authentication |
| `403`  | Authorization denied                             |
| `404`  | Resource not found                               |
| `409`  | Conflict                                         |
| `413`  | Payload/file too large                           |
| `422`  | Validation failure                               |
| `429`  | Rate limit exceeded                              |
| `500`  | Internal server error                            |
| `503`  | Service temporarily unavailable                  |

---

# 78. Validation

All API inputs should be validated.

Validation should cover:

* required fields
* data types
* allowed enum values
* string lengths
* numeric ranges
* dates
* IDs
* file size
* file type
* pagination limits

Validation should occur before business logic execution.

---

# 79. Pagination

Large resources should support pagination.

Example:

```text
GET /api/v1/cases/:caseId/transactions?page=1&limit=50
```

Response:

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 1000,
    "totalPages": 20
  }
}
```

Maximum page size should be controlled by the backend.

---

# 80. Filtering and Sorting

List APIs should support controlled filtering and sorting where required.

Example:

```text
GET /api/v1/cases/:caseId/transactions
    ?riskLevel=HIGH
    &startDate=2026-01-01
    &endDate=2026-09-29
    &sortBy=timestamp
    &sortOrder=desc
```

Allowed fields should be explicitly controlled to prevent unsafe query construction.

---

# 81. Rate Limiting

Sensitive or expensive endpoints should have appropriate rate limits.

Potentially sensitive endpoints include:

* login
* document upload
* AI investigation
* evidence search
* report generation

---

# 82. File Upload API Security

Document upload endpoints should validate:

```text
File extension
MIME type
File size
File structure
Case permission
Uploader permission
```

Production deployments should consider malware scanning and quarantine.

---

# 83. API and Case Isolation

Every case-scoped API follows:

```text
Request
  │
  ▼
Authenticate User
  │
  ▼
Extract caseId
  │
  ▼
Verify Case Access
  │
  ▼
Validate Resource Belongs to caseId
  │
  ▼
Execute Operation
```

Example:

```text
GET /api/v1/cases/A/transactions/TXN-123
```

The backend must verify:

```text
TXN-123 belongs to Case A
```

It must not simply search for `TXN-123` globally.

---

# 84. API and AI Isolation

The same principle applies to AI tools.

Example:

```text
AI asks:
"Get transaction TXN-123"
       │
       ▼
Backend
       │
       ├── Is user authenticated?
       ├── Is user authorized for case?
       ├── Does transaction belong to case?
       └── Is tool allowed?
       │
       ▼
Return authorized result
```

---

# 85. Existing Transaction API Compatibility

FraudLens already contains working transaction functionality.

The existing implementation includes transaction operations such as:

```text
POST transaction
GET transactions
```

The new API architecture should therefore **extend and organize the existing implementation rather than unnecessarily rewrite working functionality**.

During implementation:

```text
Existing Working API
        │
        ▼
Compare with API Design
        │
        ├── Already compliant → Preserve
        ├── Partially compliant → Refactor
        └── Missing → Implement
```

Existing behavior should be preserved where it does not conflict with the finalized architecture or security requirements.

---

# 86. API Layer Structure

The Node.js backend should follow a modular structure.

Conceptually:

```text
backend/
├── routes/
├── controllers/
├── services/
├── models/
├── middleware/
├── validators/
├── utils/
└── config/
```

Possible modules:

```text
auth
cases
documents
transactions
accounts
entities
relationships
evidence
investigations
findings
reports
audit
```

The exact folder structure can be adapted to the existing backend.

---

# 87. Controller-Service Separation

Controllers should handle:

* HTTP request
* validation result
* authentication context
* HTTP response

Services should handle:

* business logic
* database operations
* analytical orchestration
* investigation logic

Conceptually:

```text
HTTP Request
     │
     ▼
Controller
     │
     ▼
Service
     │
     ├── Database
     ├── ML
     ├── RAG
     └── Graph
```

---

# 88. API to ML Service

The Node.js backend may communicate with the Python ML service.

Conceptually:

```text
Node.js Backend
      │
      │ authenticated internal request
      ▼
Python ML Service
      │
      ▼
Model
      │
      ▼
Analytical Result
      │
      ▼
Node.js Backend
```

The ML service should not independently bypass application-level case authorization.

---

# 89. API to Document Processing

```text
Node.js Backend
      │
      ▼
Document Processing
      │
      ├── PDF Processing
      ├── OCR
      ├── Text Extraction
      └── Structured Extraction
      │
      ▼
Evidence / Document Metadata
```

---

# 90. API to Retrieval System

```text
Investigation Query
       │
       ▼
Node.js Backend
       │
       ▼
Retrieval Service
       │
       ├── Case Filter
       ├── Keyword Retrieval
       ├── Semantic Retrieval
       └── Reranking
       │
       ▼
Evidence
```

---

# 91. API to Knowledge Graph

```text
Graph Request
      │
      ▼
Node.js Backend
      │
      ▼
Graph Service
      │
      ├── Entity Lookup
      ├── Relationship Search
      ├── Path Search
      └── Fund-Flow Analysis
      │
      ▼
Case-Scoped Graph Result
```

---

# 92. API Request Lifecycle

A typical protected request follows:

```text
Frontend
   │
   ▼
HTTP Request
   │
   ▼
Authentication Middleware
   │
   ▼
Authorization Middleware
   │
   ▼
Validation Middleware
   │
   ▼
Controller
   │
   ▼
Service
   │
   ▼
Database / External Service
   │
   ▼
Service Result
   │
   ▼
Controller
   │
   ▼
HTTP Response
```

---

# 93. API Audit Lifecycle

Important API actions should generate audit events.

```text
API Request
   │
   ▼
Authorized Action
   │
   ▼
Business Operation
   │
   ▼
Audit Event
   │
   ▼
auditLogs
```

The audit mechanism should avoid logging sensitive credentials or unnecessary document contents.

---

# 94. API Traceability to Requirements

| Requirement                      | API Support                    |
| -------------------------------- | ------------------------------ |
| FR-01 Case Management            | `/cases`                       |
| FR-02 Document Ingestion         | `/cases/:caseId/documents`     |
| FR-03 Transaction Ingestion      | `/cases/:caseId/transactions`  |
| FR-04 Transaction Analysis       | `/transactions/analyze`        |
| FR-05 Anomaly and Risk Analysis  | `/transactions/:id/risk`       |
| FR-06 Temporal Analysis          | `/transactions/timeline`       |
| FR-07 Entity Management          | `/entities`                    |
| FR-08 Relationship Analysis      | `/relationships`, `/graph`     |
| FR-09 Fund-Flow Analysis         | `/fund-flow`                   |
| FR-10 Entity Resolution          | `/entities/resolve`            |
| FR-11 Document Processing        | `/documents`                   |
| FR-12 Evidence Retrieval         | `/evidence`, document evidence |
| FR-13 Knowledge Representation   | `/graph`, relationships        |
| FR-14 Investigation Queries      | `/investigations`              |
| FR-15 Evidence-Grounded Findings | `/findings` + `/evidence`      |
| FR-16 Investigator Review        | `/findings/:findingId/review`  |
| FR-17 Reporting                  | `/reports`                     |
| SEC-01 Authentication            | `/auth`                        |
| SEC-02 RBAC                      | Authorization middleware       |
| SEC-03 Case Isolation            | Case authorization             |
| SEC-04 Backend Authorization     | Middleware/service layer       |
| SEC-05 Input Validation          | Validation layer               |
| SEC-06 File Security             | Document upload validation     |
| SEC-09 Audit Logging             | `/audit-logs` + audit service  |

---

# 95. Initial API Priority

The APIs should be implemented in stages.

## Phase A — Core

```text
Authentication
Cases
Transactions
Accounts
```

## Phase B — Investigation Data

```text
Documents
Entities
Relationships
Evidence
```

## Phase C — Intelligence

```text
Transaction Analysis
Fund Flow
Investigation Queries
Findings
```

## Phase D — Reporting and Governance

```text
Reports
Audit Logs
Advanced Review
```

---

# 96. API Implementation Strategy

The implementation should follow:

```text
Design
  ↓
Compare with Existing Backend
  ↓
Preserve Working Functionality
  ↓
Add Missing Security
  ↓
Add Case Isolation
  ↓
Refactor Where Necessary
  ↓
Implement Missing APIs
  ↓
Test
  ↓
Commit
```

The existing working transaction APIs should be treated as an implementation baseline.

---

# 97. API Testing Strategy

Each endpoint should be tested for:

### Functional correctness

* valid request
* invalid request
* missing fields
* invalid IDs
* expected response

### Security

* unauthenticated request
* unauthorized user
* wrong case
* cross-case resource access
* invalid role
* malformed input

### Data integrity

* duplicate transaction
* invalid relationship
* missing source document
* invalid evidence reference

### AI-specific security

* unauthorized tool request
* cross-case retrieval
* prompt injection attempt
* invalid tool parameters

---

# 98. Example Security Test

Attempt:

```text
User authorized for Case A
        │
        ▼
GET /api/v1/cases/B/transactions
```

Expected:

```http
403 Forbidden
```

The system must not return Case B transaction data.

---

# 99. API Architecture Summary

FraudLens API architecture establishes:

1. REST as the initial API style.
2. `/api/v1` as the versioned API namespace.
3. Case-centered resource organization.
4. Authentication for protected resources.
5. RBAC combined with case-level authorization.
6. Backend-enforced case isolation.
7. Separate APIs for documents, transactions, accounts, entities, relationships, evidence, investigations, findings and reports.
8. Controlled internal AI investigation tools.
9. Integration points for ML, RAG and graph services.
10. Consistent validation and error handling.
11. Pagination and controlled filtering for large datasets.
12. Audit logging for important operations.
13. Compatibility with existing working transaction APIs.
14. Security testing for cross-case access and AI tool misuse.

---

# 100. Next Implementation Stage

After this API architecture is finalized, the next step is **Backend Architecture Mapping**.

The existing FraudLens backend will be inspected and mapped against this design:

```text
API Design
     │
     ▼
Existing Backend
     │
     ├── Already implemented
     ├── Needs modification
     ├── Needs security hardening
     └── Needs new implementation
```

Only after this mapping will implementation changes be made.

The next major implementation priorities will be:

1. Authentication and authorization foundation
2. Case management
3. Case-level isolation
4. Existing transaction API alignment
5. Document API
6. Entity and relationship APIs
7. Evidence APIs
8. Investigation/AI APIs
9. Findings and review
10. Reporting and audit logging
