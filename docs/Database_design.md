# FraudLens — Database & Data Model Design

## 1. Overview

This document defines the database and data model for FraudLens, an evidence-grounded AI financial fraud investigation system.

The data model is derived from the finalized:

* Research findings
* Research gaps
* Technology selection
* System requirements
* System architecture

The database design is centered around the **investigation case**.

Documents, transactions, accounts, entities, relationships, evidence, investigations, findings, and audit activities must remain associated with the appropriate case.

The primary application database is **MongoDB**.

The architecture is designed so that graph-oriented data and retrieval-oriented data can later be implemented using specialized technologies without changing the logical investigation model.

---

# 2. Database Design Objectives

The database must support the following objectives:

1. Store investigation cases.
2. Store and manage case participants.
3. Store uploaded investigation documents.
4. Store financial transactions.
5. Store financial accounts.
6. Store investigation entities.
7. Store relationships between entities and financial objects.
8. Preserve evidence provenance.
9. Store investigator and AI investigation sessions.
10. Store analytical and AI-generated findings.
11. Support investigator review.
12. Maintain strict case-level isolation.
13. Support transaction and temporal analysis.
14. Support graph and fund-flow analysis.
15. Support document retrieval and RAG.
16. Support auditability.
17. Support future integration with specialized graph and vector databases.

---

# 3. Database Technology

## Primary Database

**MongoDB**

MongoDB is used as the primary application database because the investigation domain contains heterogeneous and evolving records such as:

* documents
* transactions
* entities
* evidence
* findings
* investigation sessions

The schema should therefore remain flexible enough to accommodate different investigation data structures.

---

# 4. Collection Overview

FraudLens uses the following logical collections:

```text
MongoDB
│
├── users
├── cases
├── documents
├── transactions
├── accounts
├── entities
├── relationships
├── evidence
├── investigations
├── findings
└── auditLogs
```

Each collection has a specific responsibility.

| Collection       | Responsibility                                                     |
| ---------------- | ------------------------------------------------------------------ |
| `users`          | User identity, role and authentication-related information         |
| `cases`          | Investigation case information                                     |
| `documents`      | Uploaded document metadata and processing status                   |
| `transactions`   | Financial transaction records                                      |
| `accounts`       | Financial account information                                      |
| `entities`       | People, companies, banks and other investigation entities          |
| `relationships`  | Connections between entities, accounts, transactions and documents |
| `evidence`       | Traceable evidence extracted from investigation sources            |
| `investigations` | Investigator questions, AI sessions and investigation activities   |
| `findings`       | Analytical and AI-generated findings requiring review              |
| `auditLogs`      | Security and investigation activity records                        |

---

# 5. Case-Centered Data Model

The case is the central object in the FraudLens data model.

```text
Case
│
├── Users / Investigators
│
├── Documents
│   └── Evidence
│
├── Transactions
│   └── Accounts
│
├── Entities
│   └── Relationships
│
├── Investigations
│
├── Findings
│
└── Audit Logs
```

Conceptually:

```text
User
 │
 │ participates in
 ▼
Case
 │
 ├── has ──> Document
 │             │
 │             └── produces ──> Evidence
 │
 ├── has ──> Transaction
 │             │
 │             └── involves ──> Account
 │
 ├── has ──> Entity
 │             │
 │             └── connected through ──> Relationship
 │
 ├── has ──> Investigation
 │
 ├── has ──> Finding
 │
 └── has ──> AuditLog
```

---

# 6. Common Data Fields

Case-related collections should use common metadata where applicable.

Typical fields include:

```text
_id
caseId
createdAt
updatedAt
```

The exact fields depend on the collection.

The `caseId` field is particularly important because it enables case-level authorization and data isolation.

---

# 7. Users Collection

Collection:

```text
users
```

Purpose:

Stores FraudLens application users and their roles.

### Logical schema

```text
User
├── _id
├── name
├── email
├── passwordHash
├── role
├── isActive
├── createdAt
└── updatedAt
```

### Fields

| Field          | Type     | Description                      |
| -------------- | -------- | -------------------------------- |
| `_id`          | ObjectId | Unique user identifier           |
| `name`         | String   | User name                        |
| `email`        | String   | Unique login email               |
| `passwordHash` | String   | Hashed authentication credential |
| `role`         | String   | User role                        |
| `isActive`     | Boolean  | Whether account is active        |
| `createdAt`    | Date     | Creation timestamp               |
| `updatedAt`    | Date     | Last update timestamp            |

### Roles

Conceptual roles:

```text
ADMIN
INVESTIGATOR
REVIEWER
AUDITOR
```

Role permissions should be implemented at the backend authorization layer.

---

# 8. Cases Collection

Collection:

```text
cases
```

Purpose:

Stores investigation cases.

### Logical schema

```text
Case
├── _id
├── caseNumber
├── title
├── description
├── status
├── createdBy
├── investigators
├── createdAt
└── updatedAt
```

### Fields

| Field           | Type            | Description                    |
| --------------- | --------------- | ------------------------------ |
| `_id`           | ObjectId        | Internal MongoDB identifier    |
| `caseNumber`    | String          | Human-readable case identifier |
| `title`         | String          | Case title                     |
| `description`   | String          | Case description               |
| `status`        | String          | Case status                    |
| `createdBy`     | ObjectId        | User who created the case      |
| `investigators` | Array<ObjectId> | Users associated with the case |
| `createdAt`     | Date            | Creation timestamp             |
| `updatedAt`     | Date            | Last update timestamp          |

Example:

```json
{
  "caseNumber": "CASE-2026-014",
  "title": "Suspicious Fund Transfer Investigation",
  "status": "OPEN"
}
```

---

# 9. Case Status

Possible case states:

```text
OPEN
UNDER_INVESTIGATION
UNDER_REVIEW
CLOSED
ARCHIVED
```

The exact workflow can be refined during implementation.

---

# 10. Documents Collection

Collection:

```text
documents
```

Purpose:

Stores metadata about uploaded investigation documents.

The actual binary file may be stored separately depending on the final storage architecture.

### Logical schema

```text
Document
├── _id
├── caseId
├── fileName
├── documentType
├── mimeType
├── fileSize
├── storageReference
├── processingStatus
├── pageCount
├── checksum
├── uploadedBy
├── createdAt
└── updatedAt
```

### Fields

| Field              | Type     | Description               |
| ------------------ | -------- | ------------------------- |
| `_id`              | ObjectId | Document identifier       |
| `caseId`           | ObjectId | Associated case           |
| `fileName`         | String   | Original file name        |
| `documentType`     | String   | Document category         |
| `mimeType`         | String   | MIME type                 |
| `fileSize`         | Number   | File size                 |
| `storageReference` | String   | File storage reference    |
| `processingStatus` | String   | Processing state          |
| `pageCount`        | Number   | Number of pages           |
| `checksum`         | String   | File integrity identifier |
| `uploadedBy`       | ObjectId | Uploading user            |
| `createdAt`        | Date     | Upload timestamp          |
| `updatedAt`        | Date     | Last update               |

---

# 11. Document Processing Status

Possible states:

```text
UPLOADED
VALIDATING
PROCESSING
OCR_COMPLETED
EXTRACTED
INDEXED
FAILED
```

---

# 12. Transactions Collection

Collection:

```text
transactions
```

Purpose:

Stores financial transaction records used for transaction analysis, anomaly detection, temporal analysis and fund-flow analysis.

### Logical schema

```text
Transaction
├── _id
├── caseId
├── transactionId
├── accountId
├── destinationAccountId
├── amount
├── currency
├── transactionType
├── merchant
├── location
├── timestamp
├── status
├── fraudProbability
├── riskLevel
├── fraudPrediction
├── sourceDocumentId
├── createdAt
└── updatedAt
```

---

# 13. Transaction Fields

| Field                  | Type            | Description                                      |
| ---------------------- | --------------- | ------------------------------------------------ |
| `_id`                  | ObjectId        | Internal identifier                              |
| `caseId`               | ObjectId        | Investigation case                               |
| `transactionId`        | String          | External/business transaction identifier         |
| `accountId`            | ObjectId/String | Source account                                   |
| `destinationAccountId` | ObjectId/String | Destination account where applicable             |
| `amount`               | Number          | Transaction amount                               |
| `currency`             | String          | Currency code                                    |
| `transactionType`      | String          | Type of transaction                              |
| `merchant`             | String          | Merchant or counterparty information             |
| `location`             | String/Object   | Transaction location                             |
| `timestamp`            | Date            | Transaction timestamp                            |
| `status`               | String          | Transaction status                               |
| `fraudProbability`     | Number          | Model-generated risk probability where available |
| `riskLevel`            | String          | Analytical risk category                         |
| `fraudPrediction`      | Boolean         | Model prediction where applicable                |
| `sourceDocumentId`     | ObjectId        | Source document if applicable                    |
| `createdAt`            | Date            | Creation timestamp                               |
| `updatedAt`            | Date            | Last update                                      |

Model outputs must be treated as analytical signals and not automatically as confirmed fraud findings.

---

# 14. Accounts Collection

Collection:

```text
accounts
```

Purpose:

Represents financial accounts involved in an investigation.

### Logical schema

```text
Account
├── _id
├── caseId
├── accountNumberMasked
├── accountType
├── bankEntityId
├── ownerEntityIds
├── currency
├── status
├── sourceDocumentIds
├── createdAt
└── updatedAt
```

Sensitive account identifiers should be handled according to the security requirements.

Where possible, sensitive values should not be unnecessarily exposed to the frontend or logs.

---

# 15. Entities Collection

Collection:

```text
entities
```

Purpose:

Stores investigation entities.

Possible entity types:

```text
PERSON
COMPANY
BANK
ACCOUNT
LOCATION
MERCHANT
OTHER
```

### Logical schema

```text
Entity
├── _id
├── caseId
├── entityType
├── name
├── aliases
├── identifiers
├── attributes
├── sourceDocumentIds
├── resolutionStatus
├── confidence
├── createdAt
└── updatedAt
```

---

# 16. Entity Resolution Fields

The entity model should support potential matching across different records.

Example:

```json
{
  "entityType": "COMPANY",
  "name": "ABC Private Limited",
  "aliases": [
    "ABC Pvt Ltd",
    "ABC PVT. LTD."
  ],
  "resolutionStatus": "REVIEW_REQUIRED",
  "confidence": 0.91
}
```

A high matching score does not automatically prove that two records represent the same real-world entity.

---

# 17. Relationships Collection

Collection:

```text
relationships
```

Purpose:

Represents relationships between entities and other investigation objects.

### Logical schema

```text
Relationship
├── _id
├── caseId
├── sourceType
├── sourceId
├── relationshipType
├── targetType
├── targetId
├── attributes
├── confidence
├── evidenceIds
├── createdAt
└── updatedAt
```

Example:

```json
{
  "caseId": "CASE_ID",
  "sourceType": "ENTITY",
  "sourceId": "ENTITY_A",
  "relationshipType": "OWNS",
  "targetType": "ACCOUNT",
  "targetId": "ACCOUNT_A"
}
```

---

# 18. Relationship Types

Potential relationships include:

```text
OWNS
CONTROLS
BELONGS_TO
TRANSFERS_TO
ASSOCIATED_WITH
MENTIONED_IN
LINKED_TO
DIRECTOR_OF
EMPLOYEE_OF
LOCATED_AT
```

The relationship vocabulary should remain controlled to avoid inconsistent graph construction.

---

# 19. Evidence Collection

Collection:

```text
evidence
```

Purpose:

Stores traceable evidence extracted from documents, transactions, relationships, or other investigation sources.

### Logical schema

```text
Evidence
├── _id
├── caseId
├── evidenceType
├── sourceType
├── sourceId
├── documentId
├── pageNumber
├── section
├── sourceText
├── extractedData
├── extractionMethod
├── confidence
├── hash
├── createdAt
└── updatedAt
```

---

# 20. Evidence Provenance

Evidence must preserve its origin.

Example:

```text
Finding
   │
   └── Evidence
         │
         ├── documentId
         ├── pageNumber
         ├── section
         └── sourceText
```

This enables an investigator to move from a finding back to the original source.

---

# 21. Evidence Types

Potential evidence types:

```text
DOCUMENT_TEXT
TRANSACTION
ACCOUNT_ACTIVITY
ENTITY_RECORD
RELATIONSHIP
MODEL_SIGNAL
TIMELINE_EVENT
FUND_FLOW
```

Evidence generated by analytical models should remain distinguishable from original source evidence.

---

# 22. Investigations Collection

Collection:

```text
investigations
```

Purpose:

Stores investigation sessions and investigator/AI queries.

### Logical schema

```text
Investigation
├── _id
├── caseId
├── userId
├── query
├── queryType
├── toolCalls
├── retrievedEvidenceIds
├── response
├── status
├── createdAt
└── updatedAt
```

---

# 23. Investigation Query Types

Possible query types:

```text
DOCUMENT_SEARCH
TRANSACTION_SEARCH
ENTITY_SEARCH
RELATIONSHIP_SEARCH
FUND_FLOW
TIMELINE
GENERAL_INVESTIGATION
```

The classification may later be performed automatically by the AI investigation layer.

---

# 24. Investigation Tool Calls

Tool calls should be recorded for auditability.

Example:

```json
{
  "tool": "traceFundFlow",
  "parameters": {
    "accountId": "ACCOUNT_A",
    "maxDepth": 4
  },
  "resultReference": "RESULT_ID"
}
```

The agent should not be allowed to bypass backend authorization when invoking a tool.

---

# 25. Findings Collection

Collection:

```text
findings
```

Purpose:

Stores analytical and AI-generated findings for investigator review.

### Logical schema

```text
Finding
├── _id
├── caseId
├── title
├── claim
├── entityIds
├── transactionIds
├── evidenceIds
├── analyticalSignals
├── modelRisk
├── confidence
├── contradictions
├── unresolvedQuestions
├── status
├── createdBy
├── reviewedBy
├── reviewNotes
├── reviewedAt
├── createdAt
└── updatedAt
```

---

# 26. Finding Status

Possible statuses:

```text
OPEN
UNDER_REVIEW
CONFIRMED
REJECTED
FOLLOW_UP_REQUIRED
```

The `CONFIRMED` status represents investigator review and must not simply mean that an ML model predicted fraud.

---

# 27. Analytical Signals

A finding may contain analytical signals such as:

```json
{
  "signalType": "BEHAVIORAL_DEVIATION",
  "description": "Transaction amount significantly differs from historical account behavior",
  "source": "ML_ANALYSIS"
}
```

Possible signal categories include:

```text
HIGH_VALUE
BEHAVIORAL_DEVIATION
HIGH_VELOCITY
UNUSUAL_TIME
UNUSUAL_COUNTERPARTY
NETWORK_PATTERN
TEMPORAL_PATTERN
MODEL_RISK
```

---

# 28. Contradictions and Unresolved Questions

Findings should support conflicting or incomplete information.

Example:

```json
{
  "contradictions": [
    "Transaction description differs between two source documents."
  ],
  "unresolvedQuestions": [
    "Ownership of destination account requires further verification."
  ]
}
```

This prevents the system from presenting uncertain information as established fact.

---

# 29. Audit Logs Collection

Collection:

```text
auditLogs
```

Purpose:

Stores important security and investigation activity.

### Logical schema

```text
AuditLog
├── _id
├── userId
├── caseId
├── action
├── resourceType
├── resourceId
├── result
├── metadata
├── timestamp
└── ipAddress
```

Sensitive information should not be unnecessarily stored in audit logs.

---

# 30. Audit Events

Examples:

```text
LOGIN
LOGOUT
CASE_CREATED
CASE_ACCESSED
DOCUMENT_UPLOADED
DOCUMENT_ACCESSED
TRANSACTION_IMPORTED
ENTITY_CREATED
FINDING_CREATED
FINDING_REVIEWED
AI_INVESTIGATION
EVIDENCE_ACCESSED
REPORT_GENERATED
```

---

# 31. Collection Relationships

The logical relationships are:

```text
users
  │
  └──────────────┐
                 ▼
               cases
                 │
       ┌─────────┼─────────┬─────────┬─────────┐
       ▼         ▼         ▼         ▼         ▼
   documents transactions accounts entities investigations
       │          │          │         │
       ▼          │          │         ▼
    evidence      │          └── relationships
       │          │
       └──────────┴───────────────┐
                                  ▼
                               findings
                                  │
                                  ▼
                              auditLogs
```

This is a logical relationship model rather than a relational database schema.

---

# 32. Case Isolation Model

Case isolation is one of the most important security requirements.

For case-scoped collections:

```text
documents
transactions
accounts
entities
relationships
evidence
investigations
findings
```

the system should associate records with a `caseId`.

A typical backend query should conceptually follow:

```text
User
 ↓
Verify authentication
 ↓
Verify case permission
 ↓
Query using caseId
 ↓
Return only authorized records
```

---

# 33. Case Isolation Example

Incorrect:

```javascript
Transaction.find({
  accountId: accountId
});
```

This may potentially return records belonging to different cases.

Preferred:

```javascript
Transaction.find({
  caseId: caseId,
  accountId: accountId
});
```

The exact implementation will depend on the final backend architecture.

---

# 34. Cross-Case Access Prevention

The following situations must be prevented:

```text
Case A user
   ↓
Request Case B transaction
   ↓
Backend
   ↓
Permission check
   ↓
DENY
```

This must apply not only to normal APIs but also to:

* AI tools
* RAG retrieval
* graph queries
* document search
* fund-flow analysis
* investigation sessions

---

# 35. AI Data Access Boundary

The AI agent should never directly access MongoDB.

The architecture should be:

```text
AI Agent
   │
   ▼
Investigation Tool
   │
   ▼
Backend Authorization
   │
   ▼
Case-Scoped Database Query
   │
   ▼
Authorized Result
   │
   ▼
AI Agent
```

This ensures that AI access follows the same authorization rules as normal application requests.

---

# 36. RAG Data Boundary

RAG data should retain case association.

Conceptually:

```text
Document Chunk
├── caseId
├── documentId
├── pageNumber
├── section
├── text
└── embedding
```

Retrieval should always apply the appropriate case scope.

Example:

```text
Search Query
      │
      ▼
Case Filter
      │
      ▼
Vector / Keyword Retrieval
      │
      ▼
Relevant Case Evidence
```

A document from another investigation must not be retrieved into the current case context.

---

# 37. Knowledge Graph Data Boundary

Graph nodes and relationships should also retain case context.

Conceptually:

```text
Graph Node
├── nodeId
├── caseId
├── nodeType
└── properties
```

and:

```text
Graph Relationship
├── relationshipId
├── caseId
├── sourceNode
├── targetNode
└── relationshipType
```

This prevents cross-case graph contamination.

---

# 38. Transaction-to-Account Relationship

Transactions connect accounts.

```text
Source Account
      │
      │ transaction
      ▼
Transaction
      │
      ▼
Destination Account
```

The transaction should preserve both source and destination references where available.

This supports:

* transaction analysis
* fund-flow tracing
* graph construction
* temporal analysis

---

# 39. Entity-to-Account Relationship

Accounts may be associated with entities.

```text
Person / Company
       │
       │ owns / controls
       ▼
    Account
```

This relationship should be represented explicitly rather than relying only on text fields.

---

# 40. Document-to-Evidence Relationship

```text
Document
   │
   ├── page 1
   ├── page 2
   ├── page 3
   │
   ▼
Evidence
```

Evidence should reference the source document and location whenever possible.

---

# 41. Finding-to-Evidence Relationship

```text
Finding
   │
   ├── Evidence A
   ├── Evidence B
   ├── Transaction C
   └── Relationship D
```

This enables evidence-grounded findings.

---

# 42. Indexing Strategy

Indexes should be created based on actual query patterns.

Important candidate indexes include:

### Cases

```text
caseNumber
createdBy
```

### Documents

```text
caseId
caseId + documentType
caseId + processingStatus
```

### Transactions

```text
caseId
caseId + transactionId
caseId + accountId
caseId + timestamp
caseId + riskLevel
caseId + destinationAccountId
```

### Accounts

```text
caseId
caseId + accountNumberMasked
```

### Entities

```text
caseId
caseId + entityType
caseId + name
```

### Relationships

```text
caseId
caseId + sourceId
caseId + targetId
caseId + relationshipType
```

### Evidence

```text
caseId
caseId + documentId
caseId + evidenceType
```

### Investigations

```text
caseId
caseId + userId
caseId + createdAt
```

### Findings

```text
caseId
caseId + status
caseId + createdAt
```

Indexes should be validated against actual application queries before production deployment.

---

# 43. Data Integrity Rules

The following integrity rules should be enforced:

1. Every case-scoped record must belong to a valid case.
2. A transaction must belong to the correct case.
3. An account must belong to the correct case.
4. Entity relationships must not silently cross case boundaries.
5. Evidence must reference a valid source where applicable.
6. Findings must reference evidence or analytical signals where appropriate.
7. AI investigation sessions must belong to the correct case.
8. Unauthorized users must not retrieve case data.
9. Deleted or invalid source records should not silently invalidate evidence provenance.
10. Sensitive data must not be unnecessarily exposed.

---

# 44. Data Lifecycle

A typical investigation data lifecycle is:

```text
Upload
  ↓
Validation
  ↓
Storage
  ↓
Processing
  ↓
Extraction
  ↓
Analysis
  ↓
Evidence Creation
  ↓
Investigation
  ↓
Finding
  ↓
Review
  ↓
Report
  ↓
Archive
```

---

# 45. Data Flow Example

Example investigation:

```text
Bank Statement PDF
        │
        ▼
Document
        │
        ▼
OCR / Extraction
        │
        ▼
Evidence
        │
        ├──────────────► Account
        │
        ├──────────────► Transaction
        │
        └──────────────► Entity
                              │
                              ▼
                         Relationship
                              │
                              ▼
                        Knowledge Graph
                              │
                              ▼
                        Investigation
                              │
                              ▼
                           Finding
                              │
                              ▼
                      Investigator Review
```

---

# 46. Example Investigation Data

A simplified case may look like:

```text
CASE-2026-014
│
├── Entity
│   └── ABC Private Limited
│
├── Account
│   └── Account-A
│
├── Transaction
│   ├── TXN-001
│   ├── TXN-002
│   └── TXN-003
│
├── Document
│   └── BankStatement.pdf
│
├── Evidence
│   └── Page 12 transaction record
│
├── Relationship
│   └── ABC Private Limited → OWNS → Account-A
│
└── Finding
    └── Unusual transaction sequence
```

---

# 47. Sensitive Data Handling

Financial investigation data may contain sensitive information.

The system should minimize unnecessary exposure of:

* full account numbers
* authentication credentials
* personal identifiers
* confidential documents
* internal investigation information

Where appropriate, account numbers should be masked.

Example:

```text
XXXXXX1234
```

rather than exposing the complete account number to every application component.

---

# 48. Database Security

MongoDB should:

* require authentication
* use controlled database users
* avoid public internet exposure
* use secure connection configuration
* restrict database network access
* store credentials in environment variables or a secure secret-management system
* use backups appropriate to the deployment environment

Database credentials must never be committed to Git.

---

# 49. Backup and Recovery

Production deployments should consider:

* regular backups
* backup verification
* recovery procedures
* retention policies
* protection of backup files
* encryption of sensitive backups

Backup requirements may be simplified for the academic prototype.

---

# 50. Graph Database Boundary

The logical relationship model is independent of the physical graph implementation.

Initially, relationships may be represented through MongoDB documents.

A future implementation may use a dedicated graph database if justified by:

* graph query complexity
* investigation scale
* performance requirements
* visualization requirements
* multi-hop relationship analysis

The logical model should remain:

```text
Entity / Account / Transaction
          │
          ▼
      Relationship
          │
          ▼
       Graph Path
```

---

# 51. Vector Database Boundary

RAG/vector storage should also remain logically separate from the main application database.

The logical document representation is:

```text
Document
   │
   ▼
Document Chunk
   │
   ├── caseId
   ├── documentId
   ├── page
   ├── section
   ├── text
   └── embedding
```

A dedicated vector database can be introduced if required by scale or retrieval performance.

---

# 52. MongoDB vs Specialized Stores

The architecture separates three logical data categories:

| Data Category           | Initial Approach                         | Possible Future Technology |
| ----------------------- | ---------------------------------------- | -------------------------- |
| Application / Case Data | MongoDB                                  | MongoDB                    |
| Graph Data              | MongoDB-based relationship model         | Dedicated Graph DB         |
| Vector / Retrieval Data | Application-integrated retrieval storage | Dedicated Vector DB        |
| Source Documents        | File/object storage                      | Object Storage             |
| ML Data                 | Files / Python data pipeline             | Data/ML platform           |

The initial prototype should avoid unnecessary infrastructure complexity.

---

# 53. Data Model and ML Layer

The ML layer should consume analytical features derived from transactions and historical behavior.

Conceptually:

```text
transactions
      │
      ▼
Feature Engineering
      │
      ├── transactionHour
      ├── isNightTransaction
      ├── isHighValue
      ├── transactionCount
      ├── previousTotalAmount
      ├── averageAmount
      ├── previousMaximumAmount
      ├── amountDeviation
      ├── transactionsLastHour
      ├── transactionsLast24Hours
      └── amountLastHour
      │
      ▼
ML Model
      │
      ▼
Analytical Signal
```

The final feature set may evolve as the ML research and evaluation progress.

---

# 54. Data Model and Temporal Analysis

Transaction timestamps must support chronological investigation.

The system should allow queries such as:

```text
Transactions for Account A
between T1 and T2
ordered by timestamp
```

This supports:

* activity timelines
* velocity analysis
* suspicious periods
* transaction sequences
* fund-flow timing

---

# 55. Data Model and Fund Flow

Fund-flow analysis should use transaction relationships.

```text
Account A
    │
    └── TXN-001 ──> Account B
                         │
                         └── TXN-002 ──> Account C
                                              │
                                              └── TXN-003 ──> Account D
```

The system should be able to reconstruct this path from stored transactions.

---

# 56. Data Model and Investigator Review

Findings should preserve both AI/analytical information and investigator decisions.

```text
Finding
│
├── AI / Analytical Information
│
├── Evidence
│
├── Uncertainty
│
├── Contradictions
│
└── Investigator Review
      ├── Status
      ├── Reviewer
      ├── Notes
      └── Timestamp
```

This supports the human-in-the-loop requirement.

---

# 57. Data Model and Reporting

Reports should be generated from verified investigation records rather than directly from raw AI output.

```text
Transactions
     │
Entities
     │
Documents
     │
Evidence
     │
Analytical Signals
     │
Findings
     │
Investigator Review
     │
     ▼
Investigation Report
```

This improves traceability and reduces the risk of unsupported AI-generated conclusions entering the final report.

---

# 58. Data Model Traceability to Requirements

| Requirement                      | Data Model Support                          |
| -------------------------------- | ------------------------------------------- |
| FR-01 Case Management            | `cases`, `users`                            |
| FR-02 Document Ingestion         | `documents`                                 |
| FR-03 Transaction Ingestion      | `transactions`                              |
| FR-04 Transaction Analysis       | `transactions`, analytical signals          |
| FR-05 Anomaly and Risk Analysis  | `transactions`, `findings`                  |
| FR-06 Temporal Analysis          | transaction timestamps                      |
| FR-07 Entity Management          | `entities`                                  |
| FR-08 Relationship Analysis      | `relationships`                             |
| FR-09 Fund-Flow Analysis         | `transactions`, `accounts`, `relationships` |
| FR-10 Entity Resolution          | `entities`                                  |
| FR-11 Document Processing        | `documents`, `evidence`                     |
| FR-12 Evidence Retrieval         | `evidence`, document metadata               |
| FR-13 Knowledge Representation   | `entities`, `relationships`                 |
| FR-14 Investigation Queries      | `investigations`                            |
| FR-15 Evidence-Grounded Findings | `findings`, `evidence`                      |
| FR-16 Investigator Review        | `findings`                                  |
| FR-17 Investigation Reporting    | findings + investigation data               |
| SEC-02 RBAC                      | `users`                                     |
| SEC-03 Case Isolation            | `caseId`                                    |
| SEC-09 Audit Logging             | `auditLogs`                                 |

---

# 59. Data Model Summary

The FraudLens data model is centered around the following relationship:

```text
                         CASE
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    DOCUMENTS         TRANSACTIONS          ENTITIES
        │                  │                  │
        ▼                  ▼                  ▼
     EVIDENCE           ACCOUNTS        RELATIONSHIPS
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                    INVESTIGATION
                           │
                           ▼
                        FINDING
                           │
                           ▼
                  INVESTIGATOR REVIEW
                           │
                           ▼
                        REPORT
```

---

# 60. Final Data Model Decisions

The current FraudLens database design establishes:

1. MongoDB as the primary application database.
2. A case-centered data model.
3. `caseId` as the primary logical isolation mechanism for case-scoped records.
4. Separate collections for users, cases, documents, transactions, accounts, entities, relationships, evidence, investigations, findings and audit logs.
5. Explicit relationships between transactions, accounts and entities.
6. Evidence provenance through document and source references.
7. Investigation sessions for investigator and AI activity.
8. Findings as reviewable analytical outputs.
9. Human investigator review as a separate stage from model prediction.
10. Audit logging for important security and investigation actions.
11. Logical separation between application data, graph data and vector/RAG data.
12. Flexibility for future dedicated graph and vector databases.
13. Backend-enforced authorization as the primary case-isolation mechanism.

---

# 61. Next Design Stage

After this database design is finalized, the next stage is:

**API Architecture & Endpoint Design**

The API design will define:

* authentication endpoints
* case endpoints
* document endpoints
* transaction endpoints
* account endpoints
* entity endpoints
* relationship endpoints
* evidence endpoints
* investigation endpoints
* finding/review endpoints
* report endpoints
* audit endpoints

The API design will then be mapped against the **existing FraudLens backend implementation** so that existing working functionality is preserved rather than unnecessarily rewritten.
