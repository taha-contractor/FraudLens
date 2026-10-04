# FraudLens — System Requirements

## 1. Purpose

This document defines the functional, analytical, AI, evidence-handling, security, and non-functional requirements of the **FraudLens** project.

FraudLens is a **B.Tech major project** developed as an AI-assisted financial fraud investigation system. The project aims to help investigators analyze financial transactions and investigation documents by combining transaction analysis, anomaly detection, temporal analysis, entity and relationship analysis, document processing, evidence retrieval, and AI-assisted investigation.

The system is designed to **assist human investigators rather than replace them**. The final interpretation and investigation decisions remain with the investigator.

The requirements are designed according to the scope of a two-semester B.Tech major project:

- **Semester 7:** Literature survey, system analysis and design, architecture, database design, prototype, and initial implementation.
- **Semester 8:** Complete implementation, AI/ML and RAG integration, testing, evaluation, investigation workflow, and final demonstration.

---

# 2. Project Scope

The main objective of FraudLens is to reduce the difficulty of manually analyzing large amounts of financial and documentary information during a fraud investigation.

The system will provide a common investigation environment where an investigator can:

- Create and manage investigation cases.
- Upload and process investigation documents.
- Import financial transaction data.
- Analyze transaction and behavioral patterns.
- Identify suspicious transactions or activities.
- Analyze relationships between entities.
- Trace financial flows between accounts.
- Search and retrieve relevant evidence.
- Ask investigation-related questions using natural language.
- Receive AI-assisted, evidence-grounded responses.
- Review and record investigation findings.
- Generate a structured investigation report.

FraudLens is intended as a **prototype and academic system**, not as a production banking or law-enforcement platform.

---

# 3. Requirement Categories

The requirements are divided into the following categories:

1. Functional Requirements
2. Analytical Requirements
3. Document and Evidence Requirements
4. AI Investigation Requirements
5. Security Requirements
6. Non-Functional Requirements
7. Human-in-the-Loop Requirements

---

# 4. Functional Requirements

## FR-01 — Case Management

The system shall allow an authorized investigator to create and manage an investigation case.

Each case shall have a unique case identifier and shall act as the main boundary for:

- Investigation documents
- Financial transactions
- Accounts
- Entities
- Relationships
- Analytical results
- Evidence
- Findings
- Investigator activities

The investigator should be able to view the overall information associated with a particular case.

---

## FR-02 — Document Upload

The system shall allow an authorized investigator to upload documents related to a case.

Documents may include:

- Bank statements
- Financial reports
- Audit reports
- Company records
- Correspondence
- Regulatory documents
- Investigation reports
- Scanned documents
- Other relevant case documents

Each uploaded document shall be associated with the appropriate case.

---

## FR-03 — Transaction Data Import

The system shall allow investigators to import financial transaction data for a particular case.

The system shall validate the imported data before storing it.

The system should identify common data problems such as:

- Missing required fields
- Invalid dates
- Invalid transaction amounts
- Incorrect data formats
- Duplicate records

---

## FR-04 — Transaction Analysis

The system shall provide basic analytical capabilities for examining financial transactions.

The analysis may include:

- Transaction amount
- Transaction frequency
- Transaction timing
- Sender and receiver accounts
- Account activity
- Transaction history
- Repeated transactions
- Unusual transaction behavior

---

## FR-05 — Suspicious Transaction and Risk Analysis

The system shall identify transactions or activities that show potentially suspicious characteristics using applicable:

- Rules
- Statistical methods
- Machine-learning models
- Behavioral analysis

The system shall present these results as **risk or anomaly signals**.

A risk score or model prediction shall not automatically be treated as proof of fraud.

---

## FR-06 — Temporal Analysis

The system shall support analysis of transaction activity over time.

The system should allow investigators to identify patterns such as:

- Unusual transaction frequency
- Sudden changes in transaction activity
- High transaction velocity
- Transactions occurring within short time periods
- Suspicious activity periods
- Changes from historical account behavior

---

## FR-07 — Entity Management

The system shall represent important entities involved in an investigation.

Entities may include:

- Persons
- Companies
- Banks
- Accounts
- Transactions
- Documents
- Locations

Where possible, entities shall be linked to their source information.

---

## FR-08 — Relationship Analysis

The system shall represent relationships between entities involved in a case.

Examples include:

- Person owns Account
- Company owns Account
- Account transfers to Account
- Person associated with Company
- Company associated with Company
- Entity mentioned in Document
- Account involved in Transaction

These relationships shall help investigators understand connections within a case.

---

## FR-09 — Fund-Flow Analysis

The system shall support tracing the movement of money between connected accounts.

The investigator should be able to follow a transaction path across multiple accounts where the available transaction data supports it.

Fund-flow results should provide information such as:

- Source account
- Destination account
- Transaction amount
- Transaction date/time
- Intermediate accounts
- Related entities

---

## FR-10 — Entity Resolution

The system should support identification of potentially matching entities appearing in different records.

For example, the system may identify that different records refer to the same:

- Person
- Company
- Account
- Bank
- Entity

Potential matches should retain their source information and, where applicable, a confidence value.

---

## FR-11 — Document Processing

The system shall process supported documents and convert their content into machine-readable information.

For digital documents, the system should extract text directly where possible.

For scanned or image-based documents, the system should support OCR processing.

Document processing should preserve information such as:

- Document name
- Page number
- Extracted text
- Case identifier
- Document identifier

---

## FR-12 — Evidence Retrieval

The system shall allow investigators to search for relevant information within uploaded case documents.

Retrieved evidence should provide enough source information for the investigator to identify where the information came from.

Where available, the system should provide:

- Document name
- Page number
- Section
- Relevant text

---

## FR-13 — Investigation Knowledge Representation

The system shall maintain structured information about the entities and relationships associated with an investigation.

This representation shall support investigation activities such as:

- Finding connected entities
- Exploring relationships
- Understanding account connections
- Tracing transaction paths
- Supporting investigation queries

---

## FR-14 — Investigation Queries

The system shall allow investigators to ask questions related to a case.

Questions may be entered using natural language.

Examples include:

- "Show the major entities connected to Company A."
- "Which transactions involving Account X appear unusual?"
- "Trace the flow of money from Account A."
- "What documents mention Company B?"
- "Show the activity of Account X during this period."
- "What evidence supports this finding?"

---

## FR-15 — Evidence-Grounded Findings

The system shall generate investigation findings using available transaction, document, entity, relationship, and analytical information.

Where applicable, findings should distinguish between:

- Source evidence
- Analytical/model results
- AI-generated interpretation
- Unresolved information
- Investigator decisions

Important findings should reference the relevant evidence or data used to generate them.

---

## FR-16 — Investigator Review

The system shall allow investigators to review analytical and AI-generated findings.

The investigator should be able to assign a status such as:

- Pending Review
- Under Review
- Supported
- Rejected
- Requires More Evidence

The system shall not automatically convert an analytical signal into a final fraud determination.

---

## FR-17 — Investigation Report

The system shall support generation of a structured investigation report.

The report may contain:

- Case information
- Investigation summary
- Important entities
- Suspicious transactions
- Transaction analysis
- Fund-flow analysis
- Timeline
- Evidence references
- Analytical results
- AI-assisted findings
- Unresolved questions
- Investigator review information

---

# 5. Analytical Requirements

## AR-01 — Transaction Risk Analysis

The system should support a machine-learning or analytical model for identifying transactions with potentially suspicious characteristics.

The model may use transaction and behavioral features such as:

- Transaction amount
- Transaction frequency
- Transaction timing
- Previous account activity
- Average transaction amount
- Transaction velocity
- Historical behavior

---

## AR-02 — Behavioral Analysis

The system should compare current transaction activity with available historical account behavior.

The purpose is to identify significant deviations from normal or previously observed behavior.

---

## AR-03 — Temporal Pattern Analysis

The system should identify potentially suspicious patterns based on transaction timing and ordering.

Examples include:

- Multiple transactions within a short period
- Sudden increase in transaction activity
- Unusual activity during specific time periods
- Rapid movement of funds between accounts

---

## AR-04 — Relationship-Based Analysis

The system should use relationships between entities and transactions to provide additional investigation context.

For example, an investigator should be able to examine how:

- Accounts are connected
- Companies are connected
- Transactions connect accounts
- Documents mention entities

---

## AR-05 — Multi-Step Fund-Flow Analysis

The system should support tracing financial flows through multiple accounts where sufficient transaction information is available.

This can help investigators identify patterns that may not be visible when examining individual transactions separately.

---

## AR-06 — Explainable Analytical Results

Where practical, analytical results should provide understandable reasons or supporting information.

For example, a suspicious transaction may be associated with:

- Unusual transaction amount
- High transaction frequency
- Deviation from previous behavior
- Unusual transaction timing
- Connection to other suspicious transactions

The purpose is to help investigators understand why an analytical signal was generated.

---

# 6. Document and Evidence Requirements

## ER-01 — Document Source Preservation

The system shall preserve the identity of the source document from which information was extracted or retrieved.

---

## ER-02 — Page-Level Traceability

Where technically possible, extracted information shall retain page or section information so that investigators can locate the original source.

---

## ER-03 — OCR Support

The system shall support OCR for appropriate scanned or image-based documents.

---

## ER-04 — Information Extraction

The system should support extraction of useful investigation information from documents, including:

- Names
- Companies
- Accounts
- Dates
- Amounts
- Transactions
- Relationships

---

## ER-05 — Evidence Provenance

The system shall maintain information about the origin of extracted or retrieved evidence.

This may include:

- Case ID
- Document ID
- Document name
- Page number
- Section
- Source text

---

## ER-06 — Evidence Verification

Investigators shall be able to inspect the source information associated with important analytical or AI-generated findings.

---

## ER-07 — Evidence-Aware Retrieval

The document retrieval component should prioritize relevant information and preserve the metadata required for investigators to verify the retrieved content.

---

# 7. AI Investigation Requirements

## AI-01 — Evidence-Grounded AI

The AI investigation component should use relevant case information and retrieved evidence when answering investigation-related questions.

The AI should avoid presenting unsupported information as established facts.

---

## AI-02 — Investigation Tools

The AI investigation component should use controlled backend tools to perform investigation tasks.

Possible tools include:

- Document search
- Evidence retrieval
- Transaction search
- Account history
- Entity search
- Relationship search
- Fund-flow tracing
- Timeline generation
- Finding creation

---

## AI-03 — Case-Scoped AI Access

AI investigation operations shall remain restricted to the case being investigated.

The AI shall not retrieve information belonging to another unauthorized case.

---

## AI-04 — Evidence Attribution

Where applicable, AI-generated responses should identify the supporting:

- Document
- Page
- Transaction
- Account
- Entity
- Relationship

---

## AI-05 — Uncertainty Handling

The AI should distinguish between:

- Confirmed information
- Model-generated signals
- Possible relationships
- AI-generated interpretation
- Insufficient evidence
- Unresolved questions

---

## AI-06 — Human Decision-Making

The AI system shall assist the investigator and shall not independently determine that a person, company, account, or transaction is guilty of fraud.

Final investigation decisions shall remain with the investigator.

---

## AI-07 — Prompt Injection Protection

Uploaded documents and retrieved document content shall be treated as untrusted information.

Instructions contained inside a document shall not automatically be treated as instructions for the AI system.

---

## AI-08 — Controlled AI Actions

Actions performed by the AI component shall pass through the application's normal backend authorization and validation mechanisms.

The AI shall not directly bypass application security controls.

---

# 8. Security Requirements

## SEC-01 — Authentication

The system shall require user authentication before allowing access to protected investigation functionality.

---

## SEC-02 — Role-Based Access

The system should support different user roles according to the requirements of the prototype.

Possible roles include:

- Administrator
- Investigator
- Reviewer

---

## SEC-03 — Case Isolation

Users shall only be able to access investigation cases for which they have permission.

---

## SEC-04 — Backend Authorization

Authorization shall be enforced at the backend.

Frontend restrictions alone shall not be considered sufficient for protecting investigation data.

---

## SEC-05 — Input Validation

The system shall validate user-provided:

- API inputs
- Transaction data
- Document metadata
- Search queries
- Other investigation data

---

## SEC-06 — Secure File Upload

Uploaded files shall be checked for:

- Supported file type
- File size
- Valid file structure
- Other basic security requirements

Additional malware scanning may be considered for future production use.

---

## SEC-07 — Secure Data Handling

Investigation data shall be protected during transmission and storage using appropriate security mechanisms suitable for the project environment.

---

## SEC-08 — Secrets Management

Database credentials, API keys, model credentials, and other secrets shall not be hard-coded in the source code or committed to the project repository.

---

## SEC-09 — Audit Logging

Important system and investigation activities should be recorded in logs.

Examples include:

- User login
- Case creation
- Document upload
- Transaction import
- Finding creation
- Finding review

---

## SEC-10 — AI Security

The system shall consider AI-specific security risks such as:

- Prompt injection
- Untrusted document instructions
- Unauthorized tool access
- Cross-case information leakage

---

## SEC-11 — Database Security

The database shall be accessed through the application's backend services.

Direct unauthorized access to the database shall be prevented.

---

# 9. Non-Functional Requirements

## NFR-01 — Performance

The system should provide reasonable response times for common investigation operations within the expected B.Tech prototype workload.

---

## NFR-02 — Scalability

The system architecture should allow the number of:

- Transactions
- Documents
- Entities
- Relationships

to increase without requiring a complete redesign of the system.

---

## NFR-03 — Reliability

The system should handle invalid input and processing errors without corrupting existing investigation data.

---

## NFR-04 — Maintainability

The system should be divided into logical components so that different parts such as:

- Transaction analysis
- Machine learning
- Document processing
- Retrieval
- Knowledge representation
- AI investigation

can be modified independently where practical.

---

## NFR-05 — Traceability

Important findings should be traceable to the underlying transactions, entities, relationships, analytical results, or source documents wherever applicable.

---

## NFR-06 — Explainability

The system should provide enough information for an investigator to understand the basis of important analytical results.

---

## NFR-07 — Reproducibility

Machine-learning experiments should record relevant information such as:

- Dataset version
- Features used
- Model configuration
- Training configuration
- Evaluation metrics

This will allow the experimental results to be reproduced during project evaluation.

---

## NFR-08 — Extensibility

The system should allow additional analytical techniques, document types, models, and investigation tools to be added in the future.

---

## NFR-09 — Usability

The investigator interface should present complex information such as transactions, relationships, evidence, and analytical results in an understandable manner.

---

## NFR-10 — Data Integrity

The system shall maintain the consistency and integrity of:

- Case records
- Transaction records
- Entity records
- Document records
- Relationships
- Findings
- Evidence references

---

# 10. Human-in-the-Loop Requirements

## HIL-01 — Investigator as Final Decision-Maker

The investigator shall remain responsible for final interpretation and investigation decisions.

---

## HIL-02 — Reviewable AI Findings

AI-generated findings shall be presented in a form that allows investigators to review and verify them.

---

## HIL-03 — Evidence-Based Review

Investigators should be able to inspect the source evidence associated with important findings.

---

## HIL-04 — Finding Status

Investigation findings shall support review states such as:

- Pending
- Under Review
- Supported
- Rejected
- Requires More Evidence

---

## HIL-05 — Investigator Feedback

The system should allow investigators to add notes or feedback to findings where appropriate.

Such feedback shall become part of the investigation history.

---

## HIL-06 — Uncertainty and Contradictory Evidence

The system should allow uncertain relationships, contradictory evidence, and unresolved questions to be recorded instead of automatically treating them as confirmed facts.

---

# 11. Semester-Wise Implementation Scope

The requirements will be implemented progressively across the two semesters of the B.Tech major project.

## Semester 7 — Prototype

The Semester 7 prototype will focus on demonstrating the core investigation workflow.

The expected prototype will include:

- User authentication
- Case creation
- Case management
- Document upload
- Basic document processing
- OCR support where required
- CSV transaction import
- Transaction storage
- Basic transaction analysis
- Initial anomaly/risk analysis
- Basic temporal analysis
- Basic entity representation
- Basic relationship representation
- Evidence retrieval
- Initial RAG-based question answering
- Basic evidence references
- Initial investigator interface

The purpose of the Semester 7 prototype is to demonstrate that the proposed FraudLens architecture and investigation workflow are technically feasible.

---

## Semester 8 — Final System

The Semester 8 implementation will extend the prototype with the remaining major capabilities.

These may include:

- Improved transaction risk analysis
- Behavioral analysis
- Fund-flow tracing
- Multi-hop relationship analysis
- Entity resolution
- Knowledge representation
- Advanced evidence retrieval
- Evidence-grounded AI investigation
- Controlled AI investigation tools
- Timeline generation
- Investigator findings
- Human review workflow
- Investigation report generation
- Security improvements
- System testing
- ML model evaluation
- Retrieval evaluation
- AI response evaluation
- Final performance evaluation

The final implementation will remain within the scope of a B.Tech major project and will focus on demonstrating the feasibility and usefulness of the proposed approach.

---

# 12. Requirement Prioritization

The requirements can be grouped according to their importance for the project implementation.

## Core Requirements

The following requirements form the main FraudLens system:

- Case management
- Document upload
- Transaction data import
- Transaction analysis
- Risk/anomaly analysis
- Temporal analysis
- Entity management
- Relationship analysis
- Document processing
- OCR
- Evidence retrieval
- Knowledge representation
- Investigation queries
- Evidence-grounded findings
- Investigator review
- Basic investigation reporting
- Authentication
- Case isolation

---

## Supporting Requirements

The following features enhance the investigation capabilities:

- Entity resolution
- Explainable analytical results
- Fund-flow analysis
- Multi-hop relationship analysis
- AI investigation tools
- Audit logging
- Advanced graph visualization
- Advanced document information extraction

---

## Future Extensions

The following features are outside the main B.Tech implementation scope and may be considered as future work:

- Real-time financial transaction streaming
- Large-scale production deployment
- Continuous model retraining
- Advanced deep-learning fraud models
- Automated learning from investigator feedback
- Large-scale distributed processing
- Multimodal investigation beyond the selected document types
- Integration with live banking or law-enforcement systems

---

# 13. Requirement Design Principles

The FraudLens requirements follow the following principles:

### 1. Evidence over unsupported inference

Important investigation findings should be supported by available evidence whenever possible.

### 2. Human-in-the-loop investigation

AI and machine-learning models should assist investigators rather than replace human judgment.

### 3. Case isolation

Investigation information should remain within the authorized case boundary.

### 4. Explainability and traceability

Important analytical results should provide information about the transactions, entities, relationships, or documents that contributed to the result.

### 5. Modular architecture

The transaction analysis, document processing, retrieval, knowledge representation, and AI components should remain logically separated.

### 6. Research-driven development

The selected technologies and analytical approaches should be supported by the findings of the literature survey and technology analysis.

### 7. Separation of evidence and inference

The system should clearly distinguish between:

- Source evidence
- Analytical/model-generated signals
- AI-generated interpretation
- Investigator decisions

### 8. Security by design

Authentication, authorization, case isolation, input validation, secure file handling, and AI-specific security considerations should be included during development.

### 9. Evaluation-oriented development

The system should support measurable evaluation of:

- Machine-learning performance
- Anomaly detection
- Retrieval quality
- Evidence grounding
- AI response quality
- System performance
- Overall investigation workflow

### 10. B.Tech Project Feasibility

The system should remain technically ambitious but achievable within the two-semester B.Tech major project timeline.

The project should demonstrate a working integration of AI, machine learning, document processing, financial transaction analysis, evidence retrieval, and investigator support without attempting to reproduce a full-scale production financial investigation platform.

---

# 14. Expected Outcome

The expected outcome of FraudLens is a working prototype and final system that demonstrates how multiple analytical capabilities can be combined into a single financial fraud investigation workflow.

The system should allow an investigator to move from:

**Case Creation → Data and Document Ingestion → Analysis → Evidence Retrieval → Relationship/Fund-Flow Investigation → AI-Assisted Querying → Finding Review → Investigation Report**

The final system will demonstrate the feasibility of using AI-assisted investigation techniques to reduce manual cross-referencing and help investigators understand complex financial information while keeping the human investigator responsible for final decisions.