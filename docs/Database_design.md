# FraudLens — Database & Data Model Design

## 1. Overview

FraudLens uses a case-centered MongoDB data model to store and manage the information required for financial fraud investigation.

The database supports:

- Investigation cases
- Users and investigators
- Documents
- Transactions
- Financial accounts
- Investigation entities
- Entity relationships
- Evidence
- Investigation sessions
- Findings
- Audit logs

The database is designed for the B.Tech major project and focuses on simplicity, security, traceability, and practical implementation.

The main principle is:

> Every investigation-related record must remain associated with the correct case.

---

# 2. Database Objectives

The database must support:

1. User management
2. Case management
3. Case-level access control
4. Document management
5. Transaction management
6. Account management
7. Entity management
8. Relationship analysis
9. Evidence provenance
10. Investigation queries
11. AI-assisted investigations
12. Findings and investigator review
13. Fund-flow analysis
14. Temporal analysis
15. Audit logging
16. Future RAG integration

---

# 3. Database Technology

## Primary Database

MongoDB is used as the primary application database.

MongoDB is suitable because FraudLens contains different types of investigation data such as:

- Cases
- Documents
- Transactions
- Accounts
- Entities
- Relationships
- Evidence
- Findings
- Investigation sessions

The schema should remain flexible enough to support the evolving investigation requirements.

---

# 4. Collection Overview

FraudLens uses the following MongoDB collections:

    MongoDB
    |
    +-- users
    |
    +-- cases
    |
    +-- documents
    |
    +-- transactions
    |
    +-- accounts
    |
    +-- entities
    |
    +-- relationships
    |
    +-- evidence
    |
    +-- investigations
    |
    +-- findings
    |
    +-- auditLogs

## Collection Responsibilities

| Collection | Responsibility |
|---|---|
| users | User identity, authentication and role |
| cases | Investigation case information |
| documents | Uploaded document metadata and processing status |
| transactions | Financial transaction records |
| accounts | Financial account information |
| entities | People, companies and other investigation entities |
| relationships | Connections between entities and financial objects |
| evidence | Traceable investigation evidence |
| investigations | Investigator and AI investigation sessions |
| findings | Analytical findings and investigator review |
| auditLogs | Security and investigation activity |

---

# 5. Case-Centered Data Model

The Case is the central object in the FraudLens database.

    Case
     |
     +-- Users / Investigators
     |
     +-- Documents
     |      |
     |      +-- Evidence
     |
     +-- Transactions
     |      |
     |      +-- Accounts
     |
     +-- Entities
     |      |
     |      +-- Relationships
     |
     +-- Investigations
     |
     +-- Findings
     |
     +-- Audit Logs

All case-related collections must contain a `caseId` field.

This provides the foundation for case isolation.

---

# 6. Common Fields

Where applicable, collections should contain:

    _id
    caseId
    createdAt
    updatedAt

The exact fields depend on the collection.

The `caseId` field is especially important because it allows the backend to restrict queries to the authorized investigation case.

---

# 7. Users Collection

Collection:

    users

## Purpose

Stores FraudLens application users.

## Schema

    User
     |
     +-- _id
     +-- name
     +-- email
     +-- passwordHash
     +-- role
     +-- isActive
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Unique user identifier |
| `name` | String | User name |
| `email` | String | Login email |
| `passwordHash` | String | Hashed password |
| `role` | String | User role |
| `isActive` | Boolean | Account status |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

## Roles

For the B.Tech prototype:

    ADMIN
    INVESTIGATOR
    REVIEWER

The exact permissions are enforced by the backend authorization layer.

---

# 8. Cases Collection

Collection:

    cases

## Purpose

Stores investigation cases.

## Schema

    Case
     |
     +-- _id
     +-- caseNumber
     +-- title
     +-- description
     +-- status
     +-- createdBy
     +-- investigators
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Case identifier |
| `caseNumber` | String | Human-readable case number |
| `title` | String | Case title |
| `description` | String | Case description |
| `status` | String | Current case status |
| `createdBy` | ObjectId | User who created the case |
| `investigators` | ObjectId[] | Users assigned to the case |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

## Example

    {
      "caseNumber": "CASE-2026-001",
      "title": "Suspicious Fund Transfer Investigation",
      "description": "Investigation of unusual transactions.",
      "status": "OPEN",
      "createdBy": "USER_ID",
      "investigators": ["USER_ID"]
    }

---

# 9. Case Status

Possible case statuses:

    OPEN
    UNDER_INVESTIGATION
    UNDER_REVIEW
    CLOSED
    ARCHIVED

For the initial prototype, the main statuses can be:

    OPEN
    UNDER_INVESTIGATION
    CLOSED

Additional statuses can be introduced when required.

---

# 10. Documents Collection

Collection:

    documents

## Purpose

Stores metadata about uploaded investigation documents.

The actual file can be stored using local/private file storage or object storage.

MongoDB stores the document metadata and processing information.

## Schema

    Document
     |
     +-- _id
     +-- caseId
     +-- fileName
     +-- documentType
     +-- mimeType
     +-- fileSize
     +-- storageReference
     +-- processingStatus
     +-- pageCount
     +-- checksum
     +-- uploadedBy
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Document identifier |
| `caseId` | ObjectId | Associated case |
| `fileName` | String | Original file name |
| `documentType` | String | Document category |
| `mimeType` | String | MIME type |
| `fileSize` | Number | File size |
| `storageReference` | String | Private file location/reference |
| `processingStatus` | String | Current processing status |
| `pageCount` | Number | Number of pages |
| `checksum` | String | File integrity hash |
| `uploadedBy` | ObjectId | User who uploaded the file |
| `createdAt` | Date | Upload time |
| `updatedAt` | Date | Last update time |

---

# 11. Document Processing Status

Possible statuses:

    UPLOADED
    VALIDATING
    PROCESSING
    OCR_COMPLETED
    EXTRACTED
    INDEXED
    FAILED

Typical flow:

    UPLOADED
        |
        v
    VALIDATING
        |
        v
    PROCESSING
        |
        v
    EXTRACTED
        |
        v
    INDEXED

For scanned documents:

    PROCESSING
        |
        v
    OCR_COMPLETED
        |
        v
    EXTRACTED

---

# 12. Transactions Collection

Collection:

    transactions

## Purpose

Stores financial transactions used for:

- Transaction analysis
- Risk analysis
- Behavioral analysis
- Temporal analysis
- Fund-flow analysis
- ML processing

## Schema

    Transaction
     |
     +-- _id
     +-- caseId
     +-- transactionId
     +-- sourceAccountId
     +-- destinationAccountId
     +-- amount
     +-- currency
     +-- transactionType
     +-- description
     +-- merchant
     +-- location
     +-- timestamp
     +-- status
     +-- riskScore
     +-- riskLevel
     +-- modelPrediction
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | MongoDB identifier |
| `caseId` | ObjectId | Investigation case |
| `transactionId` | String | External transaction identifier |
| `sourceAccountId` | ObjectId | Sending account |
| `destinationAccountId` | ObjectId | Receiving account |
| `amount` | Number | Transaction amount |
| `currency` | String | Currency code |
| `transactionType` | String | Transaction type |
| `description` | String | Transaction description |
| `merchant` | String | Merchant/counterparty |
| `location` | String/Object | Transaction location |
| `timestamp` | Date | Transaction time |
| `status` | String | Transaction status |
| `riskScore` | Number | Model-generated risk score |
| `riskLevel` | String | LOW, MEDIUM or HIGH |
| `modelPrediction` | Boolean | Model prediction |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 13. Transaction Example

    {
      "caseId": "CASE_ID",
      "transactionId": "TXN-001",
      "sourceAccountId": "ACCOUNT_A",
      "destinationAccountId": "ACCOUNT_B",
      "amount": 500000,
      "currency": "INR",
      "transactionType": "TRANSFER",
      "description": "Business transfer",
      "timestamp": "2026-09-15T14:30:00Z",
      "status": "COMPLETED",
      "riskScore": 0.87,
      "riskLevel": "HIGH",
      "modelPrediction": true
    }

Model outputs are analytical signals.

A model prediction must not automatically become a confirmed fraud finding.

---

# 14. Transaction Status

Possible statuses:

    PENDING
    COMPLETED
    FAILED
    REVERSED
    CANCELLED

---

# 15. Transaction Risk Level

Possible risk levels:

    LOW
    MEDIUM
    HIGH

Risk level is generated by the analytical layer based on available rules, ML signals, or other investigation logic.

---

# 16. Accounts Collection

Collection:

    accounts

## Purpose

Represents financial accounts involved in an investigation.

## Schema

    Account
     |
     +-- _id
     +-- caseId
     +-- accountNumberMasked
     +-- accountType
     +-- bankEntityId
     +-- ownerEntityIds
     +-- currency
     +-- status
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Account identifier |
| `caseId` | ObjectId | Investigation case |
| `accountNumberMasked` | String | Masked account number |
| `accountType` | String | Account type |
| `bankEntityId` | ObjectId | Associated bank entity |
| `ownerEntityIds` | ObjectId[] | Account owner entities |
| `currency` | String | Account currency |
| `status` | String | Account status |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

Sensitive account information should not be unnecessarily exposed.

---

# 17. Account Status

Possible statuses:

    ACTIVE
    INACTIVE
    CLOSED
    UNKNOWN

---

# 18. Entities Collection

Collection:

    entities

## Purpose

Stores people, organizations, companies, banks, merchants, locations, and other entities involved in an investigation.

## Schema

    Entity
     |
     +-- _id
     +-- caseId
     +-- entityType
     +-- name
     +-- aliases
     +-- identifiers
     +-- attributes
     +-- resolutionStatus
     +-- confidence
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Entity identifier |
| `caseId` | ObjectId | Investigation case |
| `entityType` | String | Type of entity |
| `name` | String | Primary name |
| `aliases` | String[] | Alternative names |
| `identifiers` | Object | Available identifiers |
| `attributes` | Object | Additional attributes |
| `resolutionStatus` | String | Entity resolution state |
| `confidence` | Number | Matching confidence where applicable |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 19. Entity Types

Possible entity types:

    PERSON
    COMPANY
    BANK
    ACCOUNT
    MERCHANT
    LOCATION
    ORGANIZATION
    OTHER

---

# 20. Entity Resolution

Entity resolution identifies potentially matching records.

Example:

    ABC Traders Pvt Ltd
    ABC Traders
    ABC Traders Private Limited

may refer to the same organization.

Possible matching signals:

- Name similarity
- Address
- Phone number
- Email
- Account information
- Transaction relationships
- Document references

The system should store confidence rather than automatically treating a match as confirmed.

---

# 21. Entity Resolution Status

Possible statuses:

    UNREVIEWED
    MATCHED
    REVIEW_REQUIRED
    REJECTED

Example:

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

---

# 22. Relationships Collection

Collection:

    relationships

## Purpose

Stores connections between entities, accounts, transactions, and documents.

## Schema

    Relationship
     |
     +-- _id
     +-- caseId
     +-- sourceType
     +-- sourceId
     +-- relationshipType
     +-- targetType
     +-- targetId
     +-- attributes
     +-- confidence
     +-- evidenceIds
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Relationship identifier |
| `caseId` | ObjectId | Investigation case |
| `sourceType` | String | Source object type |
| `sourceId` | ObjectId | Source object |
| `relationshipType` | String | Type of relationship |
| `targetType` | String | Target object type |
| `targetId` | ObjectId | Target object |
| `attributes` | Object | Additional relationship information |
| `confidence` | Number | Relationship confidence |
| `evidenceIds` | ObjectId[] | Supporting evidence |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 23. Relationship Types

Initial controlled relationship types:

    OWNS
    CONTROLS
    TRANSFERS_TO
    ASSOCIATED_WITH
    MENTIONED_IN
    LINKED_TO
    DIRECTOR_OF
    EMPLOYEE_OF
    LOCATED_AT

The relationship vocabulary should remain controlled so that the investigation graph remains consistent.

---

# 24. Evidence Collection

Collection:

    evidence

## Purpose

Stores traceable evidence used to support investigation findings.

Evidence can originate from:

- Documents
- Transactions
- Accounts
- Entities
- Relationships
- ML analysis
- Fund-flow analysis
- Timeline analysis

## Schema

    Evidence
     |
     +-- _id
     +-- caseId
     +-- evidenceType
     +-- sourceType
     +-- sourceId
     +-- documentId
     +-- pageNumber
     +-- section
     +-- sourceText
     +-- extractedData
     +-- extractionMethod
     +-- confidence
     +-- createdAt
     +-- updatedAt

---

# 25. Evidence Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Evidence identifier |
| `caseId` | ObjectId | Investigation case |
| `evidenceType` | String | Type of evidence |
| `sourceType` | String | Source category |
| `sourceId` | ObjectId/String | Original source |
| `documentId` | ObjectId | Related document |
| `pageNumber` | Number | Document page |
| `section` | String | Relevant section |
| `sourceText` | String | Extracted source text |
| `extractedData` | Object | Structured extracted information |
| `extractionMethod` | String | OCR, extraction, transaction, analysis etc. |
| `confidence` | Number | Extraction/analysis confidence |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 26. Evidence Types

Possible evidence types:

    DOCUMENT_TEXT
    TRANSACTION
    ACCOUNT_ACTIVITY
    ENTITY_RECORD
    RELATIONSHIP
    MODEL_SIGNAL
    TIMELINE_EVENT
    FUND_FLOW

Original source evidence and model-generated evidence should remain distinguishable.

---

# 27. Evidence Provenance

Evidence must preserve its source.

Example:

    Finding
       |
       +-- Evidence
              |
              +-- documentId
              +-- pageNumber
              +-- section
              +-- sourceText

This allows an investigator to trace a finding back to its source.

---

# 28. Investigations Collection

Collection:

    investigations

## Purpose

Stores investigation sessions and investigator/AI queries.

## Schema

    Investigation
     |
     +-- _id
     +-- caseId
     +-- userId
     +-- query
     +-- queryType
     +-- toolCalls
     +-- retrievedEvidenceIds
     +-- response
     +-- status
     +-- createdAt
     +-- updatedAt

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Investigation identifier |
| `caseId` | ObjectId | Investigation case |
| `userId` | ObjectId | User who initiated investigation |
| `query` | String | Investigation question |
| `queryType` | String | Query category |
| `toolCalls` | Array | Tools used by AI |
| `retrievedEvidenceIds` | ObjectId[] | Evidence retrieved |
| `response` | String | Investigation response |
| `status` | String | Investigation status |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 29. Investigation Query Types

Possible query types:

    DOCUMENT_SEARCH
    TRANSACTION_SEARCH
    ENTITY_SEARCH
    RELATIONSHIP_SEARCH
    FUND_FLOW
    TIMELINE
    GENERAL_INVESTIGATION

The AI investigation layer may classify queries automatically.

---

# 30. AI Tool Calls

AI tool calls should be recorded for traceability.

Example:

    {
      "tool": "traceFundFlow",
      "parameters": {
        "accountId": "ACCOUNT_A",
        "maxDepth": 4
      },
      "resultReference": "RESULT_ID"
    }

AI tools must never bypass backend authorization.

Every tool request must be restricted to the authorized case.

---

# 31. Findings Collection

Collection:

    findings

## Purpose

Stores analytical and AI-generated findings that require investigator review.

## Schema

    Finding
     |
     +-- _id
     +-- caseId
     +-- title
     +-- claim
     +-- entityIds
     +-- transactionIds
     +-- evidenceIds
     +-- analyticalSignals
     +-- riskScore
     +-- confidence
     +-- contradictions
     +-- unresolvedQuestions
     +-- status
     +-- createdBy
     +-- reviewedBy
     +-- reviewNotes
     +-- reviewedAt
     +-- createdAt
     +-- updatedAt

---

# 32. Finding Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Finding identifier |
| `caseId` | ObjectId | Investigation case |
| `title` | String | Finding title |
| `claim` | String | Finding statement |
| `entityIds` | ObjectId[] | Related entities |
| `transactionIds` | ObjectId[] | Related transactions |
| `evidenceIds` | ObjectId[] | Supporting evidence |
| `analyticalSignals` | Array | Supporting analytical signals |
| `riskScore` | Number | Overall analytical risk score |
| `confidence` | Number | Finding confidence |
| `contradictions` | String[] | Conflicting information |
| `unresolvedQuestions` | String[] | Information requiring further investigation |
| `status` | String | Review status |
| `createdBy` | ObjectId | User or system creating finding |
| `reviewedBy` | ObjectId | Investigator/reviewer |
| `reviewNotes` | String | Investigator comments |
| `reviewedAt` | Date | Review time |
| `createdAt` | Date | Creation time |
| `updatedAt` | Date | Last update time |

---

# 33. Finding Status

Use the following statuses:

    PENDING
    UNDER_REVIEW
    SUPPORTED
    REJECTED
    REQUIRES_MORE_EVIDENCE

Important:

A `SUPPORTED` finding means that the investigator has reviewed the available evidence and considers the finding sufficiently supported.

It does not simply mean that the ML model predicted fraud.

---

# 34. Analytical Signals

A finding may contain signals such as:

    HIGH_VALUE
    BEHAVIORAL_DEVIATION
    HIGH_VELOCITY
    UNUSUAL_TIME
    UNUSUAL_COUNTERPARTY
    NETWORK_PATTERN
    TEMPORAL_PATTERN
    MODEL_RISK

Example:

    {
      "signalType": "BEHAVIORAL_DEVIATION",
      "description": "Transaction amount differs significantly from historical account behavior.",
      "source": "ML_ANALYSIS"
    }

---

# 35. Contradictions and Unresolved Questions

The finding model should support uncertainty.

Example:

    {
      "contradictions": [
        "Transaction description differs between two documents."
      ],
      "unresolvedQuestions": [
        "Ownership of destination account requires verification."
      ]
    }

This prevents the system from presenting uncertain information as established fact.

---

# 36. Audit Logs Collection

Collection:

    auditLogs

## Purpose

Stores important security and investigation activities.

## Schema

    AuditLog
     |
     +-- _id
     +-- userId
     +-- caseId
     +-- action
     +-- resourceType
     +-- resourceId
     +-- result
     +-- metadata
     +-- timestamp

## Fields

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Audit record identifier |
| `userId` | ObjectId | User performing action |
| `caseId` | ObjectId | Related case |
| `action` | String | Action performed |
| `resourceType` | String | Resource affected |
| `resourceId` | ObjectId/String | Resource identifier |
| `result` | String | SUCCESS or DENIED |
| `metadata` | Object | Additional non-sensitive information |
| `timestamp` | Date | Action time |

IP address can be stored if required by the security implementation, but unnecessary personal or sensitive information should not be logged.

---

# 37. Audit Events

Examples:

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
    ACCESS_DENIED

---

# 38. Collection Relationships

The logical relationships are:

    users
       |
       v
    cases
       |
       +-- documents
       |      |
       |      +-- evidence
       |
       +-- transactions
       |      |
       |      +-- accounts
       |
       +-- entities
       |      |
       |      +-- relationships
       |
       +-- investigations
       |
       +-- findings
       |
       +-- auditLogs

This is a logical data model rather than a relational database schema.

---

# 39. Case Isolation Model

Case isolation is a core security requirement.

The following collections are case-scoped:

    documents
    transactions
    accounts
    entities
    relationships
    evidence
    investigations
    findings
    auditLogs

Each record must contain the appropriate `caseId`.

The backend must verify:

    User
      |
      v
    Authentication
      |
      v
    Case Permission
      |
      v
    caseId Filter
      |
      v
    Database Query
      |
      v
    Authorized Data

---

# 40. Case Isolation Example

Incorrect:

    Transaction.find({
      accountId: accountId
    })

This can potentially return records from multiple cases.

Preferred:

    Transaction.find({
      caseId: caseId,
      accountId: accountId
    })

The backend should verify that the user has access to the requested case before executing the query.

---

# 41. Cross-Case Access Prevention

The system must prevent:

    Case A User
          |
          v
    Request Case B Data
          |
          v
    Authorization Check
          |
          v
        DENY

This rule must apply to:

- Normal API requests
- AI tools
- RAG retrieval
- Document search
- Transaction search
- Entity search
- Relationship analysis
- Fund-flow analysis
- Investigation sessions

---

# 42. AI Data Access Boundary

The AI agent must not directly access MongoDB.

Correct architecture:

    AI Agent
        |
        v
    Investigation Tool
        |
        v
    Backend Authorization
        |
        v
    Case-Scoped Query
        |
        v
    Authorized Result
        |
        v
    AI Agent

This ensures that AI access follows the same security rules as normal application requests.

---

# 43. RAG Data Model

RAG data should maintain case association.

The logical document chunk structure is:

    DocumentChunk
     |
     +-- _id
     +-- caseId
     +-- documentId
     +-- pageNumber
     +-- section
     +-- text
     +-- embeddingReference

The actual embeddings may be stored in the selected retrieval/vector solution.

The important requirement is that every retrievable chunk remains associated with its case.

---

# 44. RAG Case Isolation

RAG retrieval must follow:

    User Question
         |
         v
    Authorized Case
         |
         v
    Case Filter
         |
         v
    Document Retrieval
         |
         v
    Relevant Evidence
         |
         v
    LLM

Documents from another investigation must never enter the current case context.

---

# 45. Transaction-to-Account Relationship

Transactions connect source and destination accounts.

    Source Account
          |
          | Transaction
          v
      Transaction
          |
          v
    Destination Account

A transaction should store both source and destination account references where available.

This supports:

- Transaction analysis
- Fund-flow tracing
- Relationship analysis
- Graph construction
- Temporal analysis

---

# 46. Entity-to-Account Relationship

Accounts may be associated with one or more entities.

    Person / Company
          |
          | OWNS / CONTROLS
          v
        Account

This relationship should be explicitly represented using the `relationships` collection.

---

# 47. Document-to-Evidence Relationship

    Document
       |
       +-- Page
       |
       +-- Section
       |
       v
    Evidence

Evidence should reference the source document and location whenever possible.

---

# 48. Finding-to-Evidence Relationship

    Finding
       |
       +-- Evidence A
       +-- Evidence B
       +-- Transaction C
       +-- Relationship D

This provides the foundation for evidence-grounded findings.

---

# 49. Indexing Strategy

Indexes should be based on actual application query patterns.

## Users

    email

Email should be unique.

## Cases

    caseNumber
    createdBy
    investigators

## Documents

    caseId
    caseId + documentType
    caseId + processingStatus

## Transactions

    caseId
    caseId + transactionId
    caseId + sourceAccountId
    caseId + destinationAccountId
    caseId + timestamp
    caseId + riskLevel

## Accounts

    caseId
    caseId + accountNumberMasked

## Entities

    caseId
    caseId + entityType
    caseId + name

## Relationships

    caseId
    caseId + sourceId
    caseId + targetId
    caseId + relationshipType

## Evidence

    caseId
    caseId + documentId
    caseId + evidenceType

## Investigations

    caseId
    caseId + userId
    caseId + createdAt

## Findings

    caseId
    caseId + status
    caseId + createdAt

Indexes should be reviewed against the actual queries during implementation.

---

# 50. Data Integrity Rules

The following rules must be enforced:

1. Every case-scoped record must belong to a valid case.

2. Every transaction must belong to the correct case.

3. Every account must belong to the correct case.

4. Entity relationships must not cross case boundaries.

5. Evidence must reference a valid source where applicable.

6. Findings should reference supporting evidence or analytical signals.

7. Investigation sessions must belong to the correct case.

8. Unauthorized users must not retrieve case data.

9. AI tools must use case-scoped authorization.

10. RAG retrieval must remain case-scoped.

11. Sensitive information must not be unnecessarily exposed.

12. Model predictions must not automatically become confirmed findings.

---

# 51. Data Lifecycle

A typical investigation data lifecycle is:

    Upload
       |
       v
    Validation
       |
       v
    Storage
       |
       v
    Processing
       |
       v
    Extraction
       |
       v
    Analysis
       |
       v
    Evidence Creation
       |
       v
    Investigation
       |
       v
    Finding
       |
       v
    Investigator Review
       |
       v
    Report
       |
       v
    Archive

---

# 52. Data Flow Example

Example investigation flow:

    Bank Statement PDF
           |
           v
       Document
           |
           v
      OCR / Extraction
           |
           v
        Evidence
           |
       +---+---+
       |   |   |
       v   v   v
    Account Transaction Entity
       |       |       |
       +-------+-------+
               |
               v
         Relationships
               |
               v
        Investigation
               |
               v
             Finding
               |
               v
      Investigator Review
               |
               v
             Report

---

# 53. ML Data Flow

Transactions are used to generate analytical features.

    Transactions
         |
         v
    Feature Engineering
         |
         +-- transactionHour
         +-- isNightTransaction
         +-- isHighValue
         +-- transactionCount
         +-- previousTotalAmount
         +-- averageAmount
         +-- previousMaximumAmount
         +-- amountDeviation
         +-- transactionsLastHour
         +-- transactionsLast24Hours
         +-- amountLastHour
         |
         v
       ML Model
         |
         v
    Risk / Analytical Signal
         |
         v
       Finding

The final feature set may change during ML experimentation and evaluation.

---

# 54. Temporal Analysis

Transaction timestamps must support chronological analysis.

The system should support queries such as:

    Get all transactions for Account A
    between T1 and T2
    ordered by timestamp

This supports:

- Transaction timelines
- Velocity analysis
- Suspicious periods
- Transaction sequences
- Fund-flow timing
- Behavioral analysis

---

# 55. Fund-Flow Data Model

Fund-flow analysis is reconstructed from transaction relationships.

Example:

    Account A
        |
        +-- TXN-001 --> Account B
                            |
                            +-- TXN-002 --> Account C
                                                  |
                                                  +-- TXN-003 --> Account D

The system should be able to reconstruct this path using:

- sourceAccountId
- destinationAccountId
- transactionId
- timestamp
- amount

---

# 56. Investigator Review Model

Findings must preserve both analytical information and investigator decisions.

    Finding
       |
       +-- AI / ML Information
       |
       +-- Evidence
       |
       +-- Uncertainty
       |
       +-- Contradictions
       |
       +-- Investigator Review
              |
              +-- Status
              +-- Reviewer
              +-- Notes
              +-- Timestamp

This separates automated analysis from human decision-making.

---

# 57. Reporting Data Flow

Reports should be generated from investigation records rather than directly from raw AI output.

    Transactions
         |
         v
      Entities
         |
         v
      Documents
         |
         v
      Evidence
         |
         v
   Analytical Signals
         |
         v
      Findings
         |
         v
 Investigator Review
         |
         v
 Investigation Report

This improves traceability and reduces unsupported AI-generated conclusions in the final report.

---

# 58. Sensitive Data Handling

Financial investigation data may contain sensitive information.

The system should minimize unnecessary exposure of:

- Full account numbers
- Passwords
- Authentication credentials
- Personal identifiers
- Confidential documents
- Internal investigation information

Where appropriate, account numbers should be masked.

Example:

    XXXXXXXX1234

rather than exposing the complete account number.

Passwords must only be stored as secure password hashes.

---

# 59. Database Security

MongoDB should:

- Require authentication
- Use controlled database users
- Avoid public internet exposure
- Use secure connection configuration
- Restrict database network access
- Store credentials in environment variables
- Use secure secret management where appropriate
- Use appropriate backups

Database credentials must never be committed to Git.

---

# 60. Backup and Recovery

For the B.Tech prototype, basic backup and recovery should be considered.

Possible measures:

- Database backups
- Backup verification
- Recovery procedure
- Protection of backup files
- Appropriate backup retention

Production-level disaster recovery is outside the core project scope.

---

# 61. Graph Data Boundary

FraudLens does not require a dedicated graph database for the initial implementation.

Relationships are initially stored in MongoDB.

The logical model is:

    Entity / Account / Transaction
                |
                v
           Relationship
                |
                v
            Graph Path

A dedicated graph database can be considered later if required for:

- Complex multi-hop queries
- Large investigation graphs
- Performance
- Advanced graph analysis
- Visualization

The logical data model should not depend on a specific graph database.

---

# 62. Vector / RAG Data Boundary

FraudLens does not require a dedicated vector database for the initial prototype.

The logical retrieval model is:

    Document
       |
       v
    Document Chunk
       |
       +-- caseId
       +-- documentId
       +-- pageNumber
       +-- section
       +-- text
       +-- embeddingReference

A dedicated vector database can be introduced later if retrieval performance or project requirements justify it.

---

# 63. MongoDB vs Specialized Storage

| Data | Initial Approach | Possible Future Approach |
|---|---|---|
| Application data | MongoDB | MongoDB |
| Case data | MongoDB | MongoDB |
| Transactions | MongoDB | MongoDB |
| Relationships | MongoDB | Graph DB |
| Retrieval data | Application-integrated retrieval | Vector DB |
| Source documents | Private file storage | Object storage |
| ML datasets | CSV / Python files | ML data platform |

The initial B.Tech implementation should avoid unnecessary infrastructure.

---

# 64. Database and Security Boundary

The database must never be directly exposed to the frontend.

Correct architecture:

    React Frontend
          |
          v
    Node.js API
          |
          +-- Authentication
          |
          +-- Authorization
          |
          +-- Case Isolation
          |
          v
       MongoDB

The frontend communicates with the backend API rather than directly with MongoDB.

---

# 65. Database and AI Boundary

The AI system must not directly query MongoDB.

Correct architecture:

    AI Agent
        |
        v
    Controlled Tool
        |
        v
    Node.js Backend
        |
        +-- Authorization
        +-- Case Validation
        +-- Input Validation
        |
        v
    MongoDB
        |
        v
    Authorized Result
        |
        v
    AI Agent

This ensures that AI cannot bypass the application's security controls.

---

# 66. Semester 7 Database Scope

The Semester 7 prototype should prioritize:

- users
- cases
- documents
- transactions
- accounts
- entities
- evidence
- basic investigations
- findings
- audit logs

Relationships can be implemented in the initial prototype where required by the investigation workflow.

The database should first support a complete working case lifecycle.

---

# 67. Semester 8 Database Extensions

Semester 8 can extend the database with:

- Advanced relationships
- Entity resolution information
- Advanced fund-flow analysis
- More detailed evidence provenance
- AI tool-call history
- Improved investigation sessions
- Advanced findings
- RAG metadata
- Model evaluation information

These should be added only when required by the implementation.

---

# 68. Requirement Mapping

| Requirement | Database Support |
|---|---|
| Case Management | `cases`, `users` |
| Document Ingestion | `documents` |
| Transaction Ingestion | `transactions` |
| Transaction Analysis | `transactions` |
| Risk / Anomaly Analysis | `transactions`, `findings` |
| Temporal Analysis | `transactions.timestamp` |
| Entity Management | `entities` |
| Relationship Analysis | `relationships` |
| Entity Resolution | `entities` |
| Fund-Flow Analysis | `transactions`, `accounts`, `relationships` |
| Document Processing | `documents`, `evidence` |
| Evidence Retrieval | `evidence` |
| Knowledge Representation | `entities`, `relationships` |
| Investigation Queries | `investigations` |
| AI Investigation | `investigations`, controlled tool records |
| Evidence-Grounded Findings | `findings`, `evidence` |
| Investigator Review | `findings` |
| Reporting | `findings`, `evidence`, investigation data |
| Authentication | `users` |
| Authorization | `users`, `cases` |
| Case Isolation | `caseId` |
| Audit Logging | `auditLogs` |

---

# 69. Final Database Architecture

The final logical database structure is:

    FraudLens MongoDB
    |
    +-- users
    |
    +-- cases
    |     |
    |     +-- investigators
    |
    +-- documents
    |     |
    |     +-- evidence
    |
    +-- transactions
    |     |
    |     +-- accounts
    |
    +-- entities
    |     |
    |     +-- relationships
    |
    +-- investigations
    |
    +-- findings
    |
    +-- auditLogs

The Case remains the central logical boundary.

---

# 70. Final Database Design Decisions

The current FraudLens database design establishes:

1. MongoDB as the primary application database.

2. A case-centered data model.

3. `caseId` as the primary logical mechanism for case isolation.

4. Separate collections for users, cases, documents, transactions, accounts, entities, relationships, evidence, investigations, findings, and audit logs.

5. Explicit source and destination account references for transactions.

6. Explicit relationships between entities, accounts, transactions, and documents.

7. Evidence provenance through source references.

8. Investigation sessions for investigator and AI activity.

9. Findings as reviewable analytical outputs.

10. Human investigator review as a separate stage from model prediction.

11. Audit logging for important security and investigation actions.

12. Case-scoped RAG data.

13. Backend-enforced authorization.

14. No direct database access from the frontend.

15. No direct database access from the AI agent.

16. No mandatory dedicated graph database for the initial implementation.

17. No mandatory dedicated vector database for the initial implementation.

18. A simple architecture suitable for the B.Tech project timeline.

19. The database can be extended during Semester 8 without redesigning the complete logical model.

---

# 71. Next Design Stage

After finalizing the database design, the next stage is:

## API Architecture and Endpoint Design

The API design should define:

- Authentication endpoints
- User endpoints
- Case endpoints
- Document endpoints
- Transaction endpoints
- Account endpoints
- Entity endpoints
- Relationship endpoints
- Evidence endpoints
- Investigation endpoints
- Finding and review endpoints
- Report endpoints
- Audit endpoints
