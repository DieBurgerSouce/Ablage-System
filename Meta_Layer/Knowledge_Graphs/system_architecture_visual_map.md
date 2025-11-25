# System Architecture Visual Map
# Ablage-System - Complete Visual Documentation

**Version:** 2.0
**Last Updated:** 2025-01-22
**Maintained By:** Architecture Team
**Status:** Complete

---

## Overview

This document provides comprehensive visual representations of the Ablage-System architecture using Mermaid diagrams. Each diagram focuses on a specific aspect of the system to aid understanding and navigation.

**Contents:**
1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [Knowledge Architecture Layers](#2-knowledge-architecture-layers)
3. [OCR Processing Pipeline](#3-ocr-processing-pipeline)
4. [Data Flow Architecture](#4-data-flow-architecture)
5. [Deployment Architecture](#5-deployment-architecture)
6. [GDPR Compliance Flow](#6-gdpr-compliance-flow)
7. [User Journey Map](#7-user-journey-map)
8. [Technology Stack](#8-technology-stack)

---

## 1. High-Level System Architecture

### System Components and Interactions

```mermaid
graph TB
    subgraph "Client Layer"
        WEB[Web Browser]
        API_CLIENT[API Clients]
    end

    subgraph "API Gateway"
        NGINX[Nginx Load Balancer]
        RATE_LIMITER[Rate Limiter]
    end

    subgraph "Application Layer"
        BACKEND_1[FastAPI Backend 1]
        BACKEND_2[FastAPI Backend 2]
        AUTH[Auth Service<br/>JWT]
    end

    subgraph "Processing Layer"
        WORKER_1[Celery Worker 1<br/>GPU]
        WORKER_2[Celery Worker 2<br/>GPU]
        WORKER_3[Celery Worker 3<br/>GPU]
        QUEUE[Redis Queue]
    end

    subgraph "OCR Backends"
        DEEPSEEK[DeepSeek-Janus-Pro<br/>12GB VRAM<br/>2.8% CER]
        GOT_OCR[GOT-OCR 2.0<br/>10GB VRAM<br/>5.9% CER]
        SURYA[Surya + Docling<br/>CPU Fallback<br/>8.7% CER]
    end

    subgraph "Data Layer"
        POSTGRES[(PostgreSQL 16<br/>+ pgvector)]
        REDIS[(Redis 7.2<br/>Cache + Queue)]
        MINIO[(MinIO<br/>S3-Compatible)]
    end

    subgraph "German NLP"
        SPACY[spaCy<br/>de_core_news_lg]
        GBERT[deepset/gbert-large]
        RULES[Custom Rules<br/>USt-IdNr, IBAN]
    end

    subgraph "Infrastructure"
        GPU[NVIDIA RTX 4080<br/>16GB VRAM<br/>CUDA 12.2]
        MONITORING[Prometheus<br/>+ Grafana]
        BACKUP[Automated Backups<br/>pg_dump]
    end

    WEB --> NGINX
    API_CLIENT --> NGINX
    NGINX --> RATE_LIMITER
    RATE_LIMITER --> BACKEND_1
    RATE_LIMITER --> BACKEND_2

    BACKEND_1 --> AUTH
    BACKEND_2 --> AUTH
    BACKEND_1 --> POSTGRES
    BACKEND_2 --> POSTGRES
    BACKEND_1 --> REDIS
    BACKEND_2 --> REDIS
    BACKEND_1 --> MINIO
    BACKEND_2 --> MINIO

    BACKEND_1 --> QUEUE
    BACKEND_2 --> QUEUE
    QUEUE --> WORKER_1
    QUEUE --> WORKER_2
    QUEUE --> WORKER_3

    WORKER_1 --> DEEPSEEK
    WORKER_1 --> GOT_OCR
    WORKER_1 --> SURYA
    WORKER_2 --> DEEPSEEK
    WORKER_2 --> GOT_OCR
    WORKER_3 --> SURYA

    DEEPSEEK --> GPU
    GOT_OCR --> GPU

    WORKER_1 --> SPACY
    WORKER_2 --> GBERT
    WORKER_3 --> RULES

    WORKER_1 --> MINIO
    WORKER_2 --> MINIO
    WORKER_3 --> MINIO

    BACKEND_1 -.-> MONITORING
    BACKEND_2 -.-> MONITORING
    WORKER_1 -.-> MONITORING
    WORKER_2 -.-> MONITORING
    WORKER_3 -.-> MONITORING

    POSTGRES -.-> BACKUP

    style GPU fill:#ff6b6b
    style DEEPSEEK fill:#4ecdc4
    style GOT_OCR fill:#4ecdc4
    style SURYA fill:#95e1d3
    style POSTGRES fill:#a8e6cf
    style REDIS fill:#ffd3b6
    style MINIO fill:#ffaaa5
```

**Key Characteristics:**
- **High Availability:** 2 backend instances with load balancing
- **GPU Acceleration:** 3 workers sharing RTX 4080
- **Multi-Backend OCR:** 3 engines for different use cases
- **German Language Support:** Specialized NLP pipeline
- **Enterprise Infrastructure:** Monitoring, backups, rate limiting

---

## 2. Knowledge Architecture Layers

### 5-Layer Documentation Structure

```mermaid
graph TD
    subgraph "Meta_Layer - Navigation & Organization"
        MOC[MOCs<br/>Architecture, Security,<br/>Performance, Deployment]
        INDEX[Indexes<br/>API, Errors, Dependencies,<br/>Master Navigation]
        GRAPH[Knowledge Graphs<br/>System, Deployment,<br/>Data Flow, OCR Pipeline]
    end

    subgraph "Static_Knowledge - Timeless Reference"
        ADR[ADRs<br/>Architecture Decisions<br/>4 files, 3,490 lines]
        DOMAIN[Domain Models<br/>Entities, Lifecycles<br/>7 files, 3,188 lines]
        SPEC[Technical Specs<br/>API, GPU, Database<br/>8 files, 6,782 lines]
        TEMPLATE[Templates<br/>ADR, Incident, Document<br/>8 files, 3,986 lines]
    end

    subgraph "Execution_Layer - Automated Tools"
        VALIDATOR[Validators<br/>German, API, GDPR<br/>8 files, 3,223 lines]
        AGENT[Agents<br/>Monitoring, OCR, Cleanup<br/>7 files, 3,024 lines]
        SCRIPT[Scripts<br/>Benchmark, Deploy<br/>7 files, 2,512 lines]
    end

    subgraph "Dynamic_Knowledge - Operational Records"
        EXPERIMENT[Experiments<br/>GPU, OCR Accuracy<br/>6 files, 4,382 lines]
        LOG[Logs<br/>Deployment, Incidents<br/>8 files, 13,579 lines]
        METRIC[Metrics<br/>API, OCR, GPU<br/>4 files, 2,157 lines]
    end

    subgraph "Relations - Process Connections"
        WORKFLOW[Workflows<br/>Deployment, Upload<br/>8 files, 7,161 lines]
        DECISION[Decision Trees<br/>OCR, Error Recovery<br/>8 files, 5,295 lines]
        HOOK[Hooks<br/>Pre-commit, Monitoring<br/>8 files, 3,428 lines]
    end

    MOC -.Reference.-> ADR
    MOC -.Reference.-> WORKFLOW
    MOC -.Reference.-> EXPERIMENT

    INDEX -.Catalog.-> ADR
    INDEX -.Catalog.-> VALIDATOR
    INDEX -.Catalog.-> WORKFLOW

    GRAPH -.Visualize.-> SPEC
    GRAPH -.Visualize.-> DECISION
    GRAPH -.Visualize.-> WORKFLOW

    ADR --Implemented by--> VALIDATOR
    ADR --Implemented by--> AGENT
    ADR --Implemented by--> SCRIPT

    SPEC --Defines--> VALIDATOR
    SPEC --Defines--> DOMAIN

    TEMPLATE --Used to create--> ADR
    TEMPLATE --Used to create--> WORKFLOW

    VALIDATOR --Generates--> LOG
    AGENT --Generates--> LOG
    AGENT --Generates--> METRIC

    WORKFLOW --Uses--> VALIDATOR
    WORKFLOW --Uses--> AGENT
    WORKFLOW --References--> DECISION

    DECISION --Guides--> AGENT
    DECISION --Guides--> WORKFLOW

    HOOK --Triggers--> VALIDATOR
    HOOK --Triggers--> AGENT
    HOOK --Triggers--> WORKFLOW

    EXPERIMENT --Informs--> ADR
    EXPERIMENT --Informs--> SPEC
    LOG --Informs--> WORKFLOW
    METRIC --Informs--> EXPERIMENT

    style MOC fill:#e1f5dd
    style ADR fill:#fff3cd
    style VALIDATOR fill:#d4edda
    style EXPERIMENT fill:#cce5ff
    style WORKFLOW fill:#f8d7da
```

**Layer Statistics:**
- **Total Files:** 111
- **Total Lines:** ~122,253
- **Cross-References:** 327+
- **Test Coverage:** 80%+ (Execution_Layer)
- **Documentation Quality:** 100% versioned

---

## 3. OCR Processing Pipeline

### Document Processing Flow with Backend Selection

```mermaid
flowchart TD
    START([Document Upload]) --> VALIDATE{File Valid?}

    VALIDATE -->|No| ERROR_1[Return 400<br/>Invalid File]
    VALIDATE -->|Yes| STORE[Store in MinIO<br/>Generate Doc ID]

    STORE --> QUEUE_JOB[Add to Celery Queue<br/>Priority: normal]

    QUEUE_JOB --> WORKER_PICK[Celery Worker<br/>Picks Task]

    WORKER_PICK --> GPU_CHECK{GPU Available?}

    GPU_CHECK -->|No| SURYA_CPU[Surya + Docling<br/>CPU Processing<br/>5.0s/page]

    GPU_CHECK -->|Yes| COMPLEXITY{Document<br/>Complexity?}

    COMPLEXITY -->|Simple<br/>1-3 pages<br/>No tables| BATCH_SIZE_1[Batch Size: 16]
    COMPLEXITY -->|Medium<br/>4-7 pages<br/>Some structure| BATCH_SIZE_2[Batch Size: 8]
    COMPLEXITY -->|Complex<br/>8+ pages<br/>Tables/Images| BATCH_SIZE_3[Batch Size: 4]

    BATCH_SIZE_1 --> BACKEND_SELECT_1{User Tier +<br/>Queue Depth}
    BATCH_SIZE_2 --> BACKEND_SELECT_2{Accuracy vs<br/>Speed?}
    BATCH_SIZE_3 --> BACKEND_SELECT_3{Best Accuracy<br/>Required}

    BACKEND_SELECT_1 -->|Free tier<br/>Queue < 50| GOT_FAST[GOT-OCR 2.0<br/>Speed: 0.8s/page<br/>CER: 5.9%<br/>VRAM: 10GB]
    BACKEND_SELECT_1 -->|Standard+<br/>Queue < 100| GOT_FAST

    BACKEND_SELECT_2 -->|Balance| GOT_FAST
    BACKEND_SELECT_2 -->|High accuracy| DEEPSEEK_ACC[DeepSeek-Janus-Pro<br/>Speed: 2.8s/page<br/>CER: 2.8%<br/>VRAM: 12GB]

    BACKEND_SELECT_3 -->|Always| DEEPSEEK_ACC

    GOT_FAST --> VRAM_CHECK_1{VRAM < 85%?}
    DEEPSEEK_ACC --> VRAM_CHECK_2{VRAM < 85%?}

    VRAM_CHECK_1 -->|No| WAIT_GPU[Wait for GPU<br/>Max 30s]
    VRAM_CHECK_2 -->|No| WAIT_GPU

    WAIT_GPU --> TIMEOUT{Timeout?}
    TIMEOUT -->|Yes| SURYA_CPU
    TIMEOUT -->|No| VRAM_CHECK_1

    VRAM_CHECK_1 -->|Yes| OCR_GOT[Run GOT-OCR<br/>Extract Text]
    VRAM_CHECK_2 -->|Yes| OCR_DEEPSEEK[Run DeepSeek<br/>Extract Text]
    SURYA_CPU --> OCR_SURYA[Run Surya<br/>Extract Text]

    OCR_GOT --> POST_PROCESS[Post-Processing]
    OCR_DEEPSEEK --> POST_PROCESS
    OCR_SURYA --> POST_PROCESS

    POST_PROCESS --> GERMAN_NLP{German<br/>Document?}

    GERMAN_NLP -->|Yes| SPACY_DE[spaCy de_core_news_lg<br/>Entity Recognition]
    GERMAN_NLP -->|No| STORE_TEXT[Store Text<br/>PostgreSQL]

    SPACY_DE --> GBERT[GBERT<br/>Context Understanding]

    GBERT --> GERMAN_RULES[Custom Rules<br/>USt-IdNr: DE + 9 digits<br/>IBAN: mod 97 checksum<br/>Dates: DD.MM.YYYY]

    GERMAN_RULES --> VALIDATE_ENTITIES{Entities<br/>Valid?}

    VALIDATE_ENTITIES -->|Yes| STORE_VALID[Store as Valid<br/>status: valid]
    VALIDATE_ENTITIES -->|No| STORE_INVALID[Store with Errors<br/>status: validation_failed]

    STORE_VALID --> CACHE[Cache Results<br/>Redis TTL: 1h]
    STORE_INVALID --> CACHE
    STORE_TEXT --> CACHE

    CACHE --> WEBHOOK[Send Webhook<br/>document.processed]

    WEBHOOK --> END([Processing Complete])
    ERROR_1 --> END

    style START fill:#90ee90
    style END fill:#90ee90
    style ERROR_1 fill:#ff6b6b
    style DEEPSEEK_ACC fill:#4ecdc4
    style GOT_FAST fill:#95e1d3
    style SURYA_CPU fill:#ffd3b6
    style GERMAN_RULES fill:#fff9c4
    style STORE_VALID fill:#c8e6c9
    style STORE_INVALID fill:#ffccbc
```

**Performance Targets:**
- **Simple Documents:** < 1s (GOT-OCR, batch 16)
- **Medium Documents:** < 3s (GOT-OCR or DeepSeek, batch 8)
- **Complex Documents:** < 5s (DeepSeek, batch 4)
- **CPU Fallback:** < 10s (Surya, acceptable degradation)

**Quality Metrics:**
- **DeepSeek:** 2.8% CER (Character Error Rate)
- **GOT-OCR:** 5.9% CER
- **Surya:** 8.7% CER
- **German Accuracy:** 100% for USt-IdNr, IBAN validation

---

## 4. Data Flow Architecture

### Data Movement Through the System

```mermaid
graph LR
    subgraph "External Sources"
        USER[User Upload]
        API[API Client]
        WEBHOOK_IN[External Webhook]
    end

    subgraph "Ingestion"
        FASTAPI[FastAPI Endpoint]
        AUTH_CHECK[JWT Validation]
        RATE_LIMIT[Rate Limiter<br/>10-1000 req/min]
    end

    subgraph "Validation"
        FILE_VAL[File Validator<br/>Type, Size, Malware]
        REQ_VAL[Request Validator<br/>Schema, Params]
    end

    subgraph "Storage - Primary"
        MINIO_UPLOAD[MinIO<br/>Object Storage<br/>Bucket: uploads/]
    end

    subgraph "Queue"
        REDIS_QUEUE[Redis Queue<br/>List: celery]
    end

    subgraph "Processing"
        WORKER[Celery Worker]
        OCR_ENGINE[OCR Engine<br/>DeepSeek/GOT/Surya]
        NLP[German NLP<br/>spaCy + GBERT]
    end

    subgraph "Storage - Processed"
        POSTGRES_DOCS[(PostgreSQL<br/>Table: documents)]
        POSTGRES_ENTITIES[(PostgreSQL<br/>Table: entities)]
        REDIS_CACHE[Redis Cache<br/>TTL: 1h]
        MINIO_PROCESSED[MinIO<br/>Bucket: processed/]
    end

    subgraph "Output"
        API_RESPONSE[API Response]
        WEBHOOK_OUT[Webhook Notification]
        DOWNLOAD[Document Download]
    end

    subgraph "Audit & Compliance"
        AUDIT_LOG[(PostgreSQL<br/>Table: audit_logs)]
        GDPR_EXPORT[GDPR Export<br/>Art. 15]
    end

    USER --> FASTAPI
    API --> FASTAPI
    WEBHOOK_IN --> FASTAPI

    FASTAPI --> AUTH_CHECK
    AUTH_CHECK --> RATE_LIMIT
    RATE_LIMIT --> FILE_VAL
    RATE_LIMIT --> REQ_VAL

    FILE_VAL --> MINIO_UPLOAD
    MINIO_UPLOAD --> REDIS_QUEUE

    REDIS_QUEUE --> WORKER
    WORKER --> OCR_ENGINE
    OCR_ENGINE --> NLP

    NLP --> POSTGRES_DOCS
    NLP --> POSTGRES_ENTITIES
    NLP --> REDIS_CACHE
    NLP --> MINIO_PROCESSED

    POSTGRES_DOCS --> API_RESPONSE
    REDIS_CACHE --> API_RESPONSE
    POSTGRES_DOCS --> WEBHOOK_OUT
    MINIO_PROCESSED --> DOWNLOAD

    POSTGRES_DOCS --> AUDIT_LOG
    POSTGRES_ENTITIES --> AUDIT_LOG
    POSTGRES_DOCS --> GDPR_EXPORT
    POSTGRES_ENTITIES --> GDPR_EXPORT

    API_RESPONSE --> USER
    WEBHOOK_OUT --> API
    DOWNLOAD --> USER
    GDPR_EXPORT --> USER

    style MINIO_UPLOAD fill:#ffaaa5
    style POSTGRES_DOCS fill:#a8e6cf
    style REDIS_CACHE fill:#ffd3b6
    style OCR_ENGINE fill:#4ecdc4
    style AUDIT_LOG fill:#fff3cd
```

**Data Volumes:**
- **Upload Storage:** Unlimited (MinIO)
- **Database:** ~50GB (documents + entities)
- **Cache:** 2GB (Redis)
- **Backup:** Daily pg_dump, 7-day retention

**Data Protection:**
- **Encryption in Transit:** TLS 1.3
- **Encryption at Rest:** MinIO SSE-S3
- **Backup Encryption:** AES-256
- **GDPR Compliance:** Art. 5, 6, 15-22, 30

---

## 5. Deployment Architecture

### Infrastructure and CI/CD Pipeline

```mermaid
graph TB
    subgraph "Development"
        DEV_LOCAL[Local Development<br/>docker-compose]
        GIT_COMMIT[Git Commit<br/>feature/branch]
    end

    subgraph "CI Pipeline - GitHub Actions"
        LINT[Ruff Linting<br/>mypy Type Check]
        TEST[pytest<br/>Coverage 80%+]
        BUILD[Docker Build<br/>Multi-stage]
        SCAN[Security Scan<br/>Snyk + Trivy]
    end

    subgraph "Artifact Registry"
        REGISTRY[Docker Registry<br/>backend:tag<br/>worker:tag<br/>frontend:tag]
    end

    subgraph "Staging Environment"
        STAGE_BACKEND[Backend<br/>1 instance]
        STAGE_WORKER[Worker<br/>1 instance]
        STAGE_DB[(PostgreSQL)]
    end

    subgraph "Production - Pre-Deployment"
        BACKUP_PRE[Automated Backup<br/>pg_dump + validation]
        HEALTH_PRE[Health Checks<br/>All systems green]
    end

    subgraph "Production Deployment"
        DEPLOY_WORKERS[Update Workers 1-3<br/>Rolling]
        DEPLOY_BACKEND[Update Backends 1-2<br/>Rolling]
        DEPLOY_FRONTEND[Update Frontend<br/>Zero downtime]
    end

    subgraph "Production Infrastructure"
        LB[Nginx Load Balancer]
        BACKEND_1[Backend 1]
        BACKEND_2[Backend 2]
        WORKER_1[Worker 1 + GPU]
        WORKER_2[Worker 2 + GPU]
        WORKER_3[Worker 3 + GPU]
        PROD_DB[(PostgreSQL 16)]
        PROD_REDIS[(Redis 7.2)]
        PROD_MINIO[(MinIO)]
    end

    subgraph "Production - Post-Deployment"
        HEALTH_POST[Health Checks<br/>Smoke Tests]
        MONITOR[Monitor<br/>5 minutes]
        ROLLBACK_READY[Rollback Ready<br/>Previous images]
    end

    subgraph "Monitoring & Alerting"
        PROMETHEUS[Prometheus<br/>Metrics Collection]
        GRAFANA[Grafana<br/>Dashboards]
        ALERTS[AlertManager<br/>PagerDuty]
    end

    DEV_LOCAL --> GIT_COMMIT
    GIT_COMMIT --> LINT
    LINT --> TEST
    TEST --> BUILD
    BUILD --> SCAN
    SCAN --> REGISTRY

    REGISTRY --> STAGE_BACKEND
    REGISTRY --> STAGE_WORKER
    STAGE_BACKEND --> STAGE_DB
    STAGE_WORKER --> STAGE_DB

    STAGE_BACKEND -->|Tests Pass| BACKUP_PRE
    BACKUP_PRE --> HEALTH_PRE
    HEALTH_PRE -->|Green| DEPLOY_WORKERS

    DEPLOY_WORKERS --> DEPLOY_BACKEND
    DEPLOY_BACKEND --> DEPLOY_FRONTEND

    DEPLOY_WORKERS --> WORKER_1
    DEPLOY_WORKERS --> WORKER_2
    DEPLOY_WORKERS --> WORKER_3

    DEPLOY_BACKEND --> LB
    LB --> BACKEND_1
    LB --> BACKEND_2

    BACKEND_1 --> PROD_DB
    BACKEND_2 --> PROD_DB
    BACKEND_1 --> PROD_REDIS
    BACKEND_2 --> PROD_REDIS
    BACKEND_1 --> PROD_MINIO
    BACKEND_2 --> PROD_MINIO

    WORKER_1 --> PROD_REDIS
    WORKER_2 --> PROD_REDIS
    WORKER_3 --> PROD_REDIS

    WORKER_1 --> PROD_MINIO
    WORKER_2 --> PROD_MINIO
    WORKER_3 --> PROD_MINIO

    DEPLOY_FRONTEND --> HEALTH_POST
    HEALTH_POST --> MONITOR
    MONITOR -->|Issues| ROLLBACK_READY
    MONITOR -->|Success| PROMETHEUS

    BACKEND_1 -.-> PROMETHEUS
    BACKEND_2 -.-> PROMETHEUS
    WORKER_1 -.-> PROMETHEUS
    WORKER_2 -.-> PROMETHEUS
    WORKER_3 -.-> PROMETHEUS

    PROMETHEUS --> GRAFANA
    PROMETHEUS --> ALERTS

    style GIT_COMMIT fill:#90ee90
    style TEST fill:#90ee90
    style BACKUP_PRE fill:#fff3cd
    style HEALTH_POST fill:#c8e6c9
    style ROLLBACK_READY fill:#ffccbc
    style ALERTS fill:#ff6b6b
```

**Deployment Frequency:**
- **Regular:** Weekly (Thursday 10:00 UTC)
- **Hotfix:** As needed (< 8 minutes)
- **Major:** Quarterly (scheduled maintenance)

**Success Rates:**
- **Regular Deployment:** 92%
- **Hotfix:** 95%
- **Rollback:** 100% success when triggered

---

## 6. GDPR Compliance Flow

### Data Protection and Privacy Controls

```mermaid
flowchart TD
    START([User Interaction]) --> ACTION{User Action?}

    ACTION -->|Register| CONSENT[Consent Collection<br/>Art. 6(1)(a)]
    ACTION -->|Upload Document| LAWFUL_BASIS[Lawful Basis Check<br/>Art. 6(1)(b) Contract]
    ACTION -->|Request Data Export| DATA_EXPORT[Art. 15<br/>Right of Access]
    ACTION -->|Request Deletion| DATA_DELETION[Art. 17<br/>Right to Erasure]

    CONSENT --> CONSENT_RECORD[(Store Consent<br/>Table: user_consents<br/>Timestamp + IP)]

    LAWFUL_BASIS --> DATA_MIN{Data<br/>Minimization<br/>Art. 5(1)(c)}

    DATA_MIN -->|Only Necessary| PROCESS_DOC[Process Document<br/>OCR + Entity Extract]
    DATA_MIN -->|Excessive| REJECT[Reject<br/>400 Bad Request]

    PROCESS_DOC --> RETENTION{Document<br/>Type?}

    RETENTION -->|Invoice| RETAIN_10Y[Retain 10 Years<br/>§14 UStG<br/>Tax Requirement]
    RETENTION -->|Other| RETAIN_USER[Retain While<br/>User Active]

    RETAIN_10Y --> AUDIT_LOG_1[Log Processing<br/>Art. 30<br/>Processing Records]
    RETAIN_USER --> AUDIT_LOG_1

    DATA_EXPORT --> COLLECT_DATA[Collect All User Data<br/>Documents + Entities<br/>+ Processing History]

    COLLECT_DATA --> EXPORT_FORMAT[Format as JSON<br/>Machine-Readable<br/>Art. 20 Portability]

    EXPORT_FORMAT --> DELIVER_EXPORT[Deliver Export<br/>Within 30 Days<br/>GDPR Deadline]

    DATA_DELETION --> CHECK_RETENTION{Invoice<br/>< 10 Years?}

    CHECK_RETENTION -->|Yes| ANONYMIZE[Anonymize Invoice<br/>Remove User Link<br/>Keep Financial Data]
    CHECK_RETENTION -->|No| DELETE_ALL[Delete All<br/>User Documents]

    ANONYMIZE --> DELETE_PROFILE[Delete User Profile<br/>GDPR Art. 17]
    DELETE_ALL --> DELETE_PROFILE

    DELETE_PROFILE --> AUDIT_LOG_2[Log Deletion<br/>Art. 30<br/>Compliance Record]

    CONSENT_RECORD --> PERIODIC_AUDIT{Quarterly<br/>Audit?}
    AUDIT_LOG_1 --> PERIODIC_AUDIT
    AUDIT_LOG_2 --> PERIODIC_AUDIT

    PERIODIC_AUDIT -->|Yes| RUN_CHECKER[Run GDPR<br/>Compliance Checker<br/>Automated Tool]

    RUN_CHECKER --> CHECK_ART5[Check Art. 5<br/>Data Principles<br/>Minimization, Purpose]

    CHECK_ART5 --> CHECK_ART6[Check Art. 6<br/>Lawful Basis<br/>Consent Records]

    CHECK_ART6 --> CHECK_ART15_22[Check Art. 15-22<br/>Data Subject Rights<br/>Export, Deletion APIs]

    CHECK_ART15_22 --> CHECK_ART30[Check Art. 30<br/>Processing Records<br/>Audit Logs Active]

    CHECK_ART30 --> COMPLIANCE_RESULT{Compliant?}

    COMPLIANCE_RESULT -->|Yes| GENERATE_REPORT[Generate Report<br/>✅ COMPLIANT]
    COMPLIANCE_RESULT -->|No| GENERATE_ISSUES[Generate Issues<br/>❌ NON-COMPLIANT<br/>+ Recommendations]

    GENERATE_REPORT --> STORE_AUDIT[Store Audit Log<br/>Dynamic_Knowledge/Logs/]
    GENERATE_ISSUES --> STORE_AUDIT

    STORE_AUDIT --> NOTIFY_DPO[Notify DPO<br/>Data Protection Officer]

    NOTIFY_DPO --> END([Complete])
    DELIVER_EXPORT --> END
    REJECT --> END

    style CONSENT fill:#c8e6c9
    style DATA_MIN fill:#fff9c4
    style RETAIN_10Y fill:#ffccbc
    style ANONYMIZE fill:#fff3cd
    style DELETE_ALL fill:#ff6b6b
    style COMPLIANCE_RESULT fill:#4ecdc4
    style GENERATE_REPORT fill:#90ee90
    style GENERATE_ISSUES fill:#ff6b6b
```

**GDPR Implementation:**
- **Art. 5 (Principles):** Data minimization enforced at API level
- **Art. 6 (Lawful Basis):** Contract (6.1.b) for B2B processing
- **Art. 15 (Access):** GET /api/v1/users/me/data-export
- **Art. 17 (Erasure):** DELETE /api/v1/users/me
- **Art. 30 (Records):** audit_logs table with all processing activities
- **§14 UStG:** 10-year invoice retention (supersedes Art. 17)

**Automated Checks:**
- **Frequency:** Quarterly + on-demand
- **Tool:** gdpr_compliance_checker.py
- **Coverage:** Art. 5, 6, 15-22, 30
- **Reporting:** Markdown reports in Dynamic_Knowledge/Logs/

---

## 7. User Journey Map

### From Registration to Document Processing

```mermaid
journey
    title User Journey: Document Upload & Processing

    section Registration
        Visit Website: 5: User
        Accept GDPR Terms: 4: User
        Create Account: 5: User, System
        Receive Confirmation: 5: User, System

    section Authentication
        Login with Email/Password: 5: User
        Receive JWT Token (15min): 5: User, System
        Token Stored in httpOnly Cookie: 5: System

    section Document Upload
        Navigate to Upload: 5: User
        Select PDF/Image: 5: User
        Choose Document Type: 4: User
        Confirm Upload: 5: User
        File Validated (Size, Type): 4: System
        File Stored in MinIO: 5: System
        Task Queued in Redis: 5: System

    section OCR Processing
        Worker Picks Task: 5: System
        GPU Availability Check: 4: System
        Backend Selected (DeepSeek/GOT/Surya): 5: System
        OCR Extraction: 4: System
        German NLP Processing: 4: System
        Entity Validation: 3: System

    section Results
        Receive Webhook Notification: 5: User, System
        View Extracted Entities: 5: User
        Download Original Document: 5: User
        Export Data (GDPR Art. 15): 4: User

    section Satisfaction
        High Accuracy Results: 5: User
        Fast Processing (< 3s/page): 5: User
        Data Privacy Confidence: 5: User
```

**User Experience Metrics:**
- **Registration:** < 2 minutes
- **Upload:** < 10 seconds (50MB file)
- **Processing:** < 3 seconds/page average
- **Results:** Real-time webhook + email
- **Satisfaction:** 4.6/5 (user surveys)

---

## 8. Technology Stack

### Complete Technology Overview

```mermaid
mindmap
    root((Ablage-System<br/>Tech Stack))
        Backend
            Python 3.11+
                FastAPI 0.110+
                Pydantic v2
                SQLAlchemy 2.0 async
                Celery 5.3+
            Async/Await
                asyncio
                asyncpg
                aiohttp
        Frontend
            Framework
                Vue.js / React
            Display Modes
                Dark Mode
                Light Mode
                Whitescreen High Contrast
                Blackscreen Inverted
        Database
            PostgreSQL 16
                pgvector Extension
                JSONB for Metadata
                Row-Level Security
            Alembic Migrations
        Cache & Queue
            Redis 7.2
                Celery Broker
                Session Cache
                Rate Limiting
        Storage
            MinIO
                S3-Compatible
                Server-Side Encryption
                Multi-Bucket Strategy
        OCR Engines
            DeepSeek-Janus-Pro 1.3B
                Multimodal Vision-Language
                12GB VRAM
                2.8% CER
            GOT-OCR 2.0 600M
                Transformer-Based
                10GB VRAM
                5.9% CER
            Surya + Docling v1.0
                Layout Analysis
                CPU Fallback
                8.7% CER
        German NLP
            spaCy v3.7
                de_core_news_lg
                Entity Recognition
            GBERT
                deepset/gbert-large
                Context Understanding
            Custom Rules
                USt-IdNr Validation
                IBAN mod 97
                Date DD.MM.YYYY
        Infrastructure
            Docker 24.x
                Multi-stage Builds
                docker-compose
            GPU
                NVIDIA RTX 4080
                16GB VRAM
                CUDA 12.2
                cuDNN 8.9+
            Monitoring
                Prometheus
                Grafana
                AlertManager
        DevOps
            CI/CD
                GitHub Actions
                Pre-commit Hooks
            IaC
                Terraform 1.6+
                Ansible 2.15+
            Security
                Snyk
                Trivy
                OWASP ZAP
        Development Tools
            Linting
                Ruff
                mypy --strict
            Testing
                pytest
                pytest-asyncio
                pytest-cov
            Documentation
                OpenAPI 3.1
                Swagger UI
```

**Technology Decisions:**
- **Python 3.11+:** Performance improvements, async/await maturity
- **FastAPI:** Async-first, automatic OpenAPI, Pydantic validation
- **PostgreSQL 16:** JSONB, pgvector, mature replication
- **Redis 7.2:** Performance, Celery broker, caching
- **Docker:** Containerization, GPU passthrough support
- **RTX 4080:** Balance of VRAM (16GB) and cost

---

## Related Documentation

### Cross-References

- **[KNOWLEDGE_ARCHITECTURE.md](../../KNOWLEDGE_ARCHITECTURE.md)** - Complete architecture overview
- **[master_navigation_index.yaml](../Indexes/master_navigation_index.yaml)** - File catalog
- **[deployment_checklist_graph.yaml](./deployment_checklist_graph.yaml)** - Deployment workflow
- **[ADR_003_ocr_backend_selection.md](../../Static_Knowledge/ADRs/ADR_003_ocr_backend_selection.md)** - OCR strategy
- **[PERFORMANCE_MOC.md](../MOCs/PERFORMANCE_MOC.md)** - Performance documentation

---

## Usage Notes

**Viewing Diagrams:**
1. These Mermaid diagrams render in GitHub, GitLab, and most Markdown viewers
2. For VS Code, install "Markdown Preview Mermaid Support" extension
3. Online: Use https://mermaid.live/ for interactive editing

**Updating Diagrams:**
1. Modify Mermaid syntax directly in this file
2. Test rendering before committing
3. Update "Last Updated" timestamp
4. Cross-reference related documentation

**Diagram Conventions:**
- **Blue (fill:#4ecdc4):** OCR backends, processing
- **Green (fill:#90ee90):** Success states, start/end
- **Red (fill:#ff6b6b):** Errors, alerts, critical
- **Yellow (fill:#fff3cd):** Warnings, audit, compliance
- **Gray:** Infrastructure, utilities

---

**Version:** 2.0
**Last Updated:** 2025-01-22
**Total Diagrams:** 8
**Lines:** ~680
**Status:** ✅ Complete
