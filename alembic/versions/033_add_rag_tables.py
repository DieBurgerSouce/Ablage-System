"""Add RAG Intelligence Layer tables.

Erstellt die Datenbank-Infrastruktur fuer das RAG (Retrieval-Augmented Generation)
Intelligence Layer des Ablage-Systems:

- rag_document_chunks: Chunked documents mit Embeddings fuer semantische Suche
- rag_customer_cards: Pre-computed Kunden-Zusammenfassungen fuer Telefon-Support
- rag_chat_sessions: Chat Konversationen mit Dokumenten-Kontext
- rag_chat_messages: Einzelne Chat-Nachrichten mit Quellen-Referenzen
- rag_llm_models: LLM Model Registry und Konfiguration
- rag_batch_jobs: Batch Job Tracking fuer Customer Card Sync und Reports

Zusaetzlich werden zwei PostgreSQL-Funktionen erstellt:
- rag_semantic_search(): Vector Similarity Search mit Filterung
- rag_hybrid_search(): Kombinierte Semantic + Keyword Suche

Revision ID: 033_add_rag_tables
Revises: 032_structured_extraction
Create Date: 2025-01-15

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

# revision identifiers
revision = "033_add_rag_tables"
down_revision = "032_structured_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade: RAG Intelligence Layer Tabellen und Funktionen erstellen.
    """
    # =========================================================================
    # 1. RAG DOCUMENT CHUNKS TABLE
    # Speichert die chunked Dokumente mit Embeddings fuer RAG
    # =========================================================================
    op.create_table(
        "rag_document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),

        # Chunk-Metadaten
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_tokens", sa.Integer, nullable=False),

        # Positionierung im Dokument
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_type", sa.String(50), nullable=True),  # header, paragraph, table, list, footer
        sa.Column("bounding_box", JSONB, nullable=True),  # {"x": 0, "y": 0, "width": 100, "height": 50}

        # Embedding-Metadaten
        sa.Column("embedding_model", sa.String(100), nullable=False, server_default="intfloat/multilingual-e5-large"),
        sa.Column("embedding_created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        # Constraints
        sa.CheckConstraint("chunk_index >= 0", name="ck_rag_chunks_valid_index"),
        sa.CheckConstraint("chunk_tokens > 0 AND chunk_tokens <= 8192", name="ck_rag_chunks_valid_tokens"),
    )

    # Embedding Vector Column (pgvector 1024 dimensions)
    op.execute("""
        ALTER TABLE rag_document_chunks
        ADD COLUMN embedding vector(1024) NOT NULL
    """)

    # Unique constraint fuer Document + Chunk Index
    op.create_index(
        "ix_rag_chunks_document_index",
        "rag_document_chunks",
        ["document_id", "chunk_index"],
        unique=True
    )

    # Vector Index fuer Semantic Search (IVFFlat fuer grosse Datenmengen)
    op.execute("""
        CREATE INDEX ix_rag_chunks_embedding_ivfflat
        ON rag_document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # GIN Index fuer Section Type Filtering
    op.create_index("ix_rag_chunks_section_type", "rag_document_chunks", ["section_type"])

    # B-Tree Index fuer Page Number Range Queries
    op.create_index("ix_rag_chunks_page_number", "rag_document_chunks", ["page_number"])

    # Index fuer Document ID (Foreign Key Performance)
    op.create_index("ix_rag_chunks_document_id", "rag_document_chunks", ["document_id"])

    # =========================================================================
    # 2. RAG CUSTOMER CARDS TABLE
    # Pre-computed Kunden-Zusammenfassungen fuer Real-Time Zugriff
    # =========================================================================
    op.create_table(
        "rag_customer_cards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Kunden-Identifikation
        sa.Column("customer_id", sa.String(100), nullable=False, unique=True),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_type", sa.String(50), nullable=True),  # Stammkunde, Neukunde, Inaktiv

        # Pre-Computed Summaries (vom LLM generiert)
        sa.Column("summary_text", sa.Text, nullable=False),
        sa.Column("quick_facts", JSONB, nullable=False, server_default="[]"),

        # Strukturierte Daten
        sa.Column("open_invoices", JSONB, server_default="[]"),
        sa.Column("active_contracts", JSONB, server_default="[]"),
        sa.Column("recent_orders", JSONB, server_default="[]"),

        # Metriken
        sa.Column("total_revenue_ytd", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_revenue_last_year", sa.Numeric(15, 2), nullable=True),
        sa.Column("average_order_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("payment_behavior", sa.String(50), nullable=True),  # Puenktlich, Verzoegert, Problematisch

        # Flags und Alerts
        sa.Column("flags", JSONB, server_default="[]"),  # ["Zahlungsverzug", "Vertrag laeuft aus"]
        sa.Column("priority_level", sa.Integer, server_default="0"),  # 0-10, hoeher = wichtiger

        # Synchronisation
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_incremental_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(20), server_default="pending"),  # pending, syncing, completed, error
        sa.Column("sync_error_message", sa.Text, nullable=True),

        # Source Documents (fuer Nachvollziehbarkeit)
        sa.Column("source_document_ids", ARRAY(UUID(as_uuid=True)), server_default="{}"),
        sa.Column("source_document_count", sa.Integer, server_default="0"),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Embedding fuer Card-Search (optional, fuer semantische Kundensuche)
    op.execute("""
        ALTER TABLE rag_customer_cards
        ADD COLUMN card_embedding vector(1024)
    """)

    # Trigram Index fuer Fuzzy-Suche nach Kundenname (erfordert pg_trgm Extension)
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS pg_trgm
    """)
    op.execute("""
        CREATE INDEX ix_rag_customer_cards_name_trgm
        ON rag_customer_cards
        USING gin (customer_name gin_trgm_ops)
    """)

    op.create_index("ix_rag_customer_cards_type", "rag_customer_cards", ["customer_type"])
    op.create_index("ix_rag_customer_cards_priority", "rag_customer_cards", ["priority_level"], postgresql_using="btree")
    op.create_index("ix_rag_customer_cards_sync_status", "rag_customer_cards", ["sync_status"])

    # =========================================================================
    # 3. RAG CHAT SESSIONS TABLE
    # Speichert Chat-Konversationen fuer Context
    # =========================================================================
    op.create_table(
        "rag_chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # User/Session Identifikation
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_token", sa.String(255), nullable=False, unique=True),

        # Session Metadaten
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("context_type", sa.String(50), nullable=True),  # general, customer, document, report
        sa.Column("context_id", sa.String(255), nullable=True),   # z.B. customer_id oder document_id

        # Session Status
        sa.Column("status", sa.String(20), server_default="active"),  # active, archived, deleted
        sa.Column("message_count", sa.Integer, server_default="0"),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_rag_chat_sessions_user", "rag_chat_sessions", ["user_id"])
    op.create_index("ix_rag_chat_sessions_context", "rag_chat_sessions", ["context_type", "context_id"])
    op.create_index("ix_rag_chat_sessions_status", "rag_chat_sessions", ["status"])

    # =========================================================================
    # 4. RAG CHAT MESSAGES TABLE
    # Einzelne Nachrichten in einer Session
    # =========================================================================
    op.create_table(
        "rag_chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Referenz zur Session
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("rag_chat_sessions.id", ondelete="CASCADE"), nullable=False),

        # Message Content
        sa.Column("role", sa.String(20), nullable=False),  # user, assistant, system
        sa.Column("content", sa.Text, nullable=False),

        # Fuer Assistant Messages: Quellen
        sa.Column("source_chunks", ARRAY(UUID(as_uuid=True)), server_default="{}"),  # Referenzen zu rag_document_chunks
        sa.Column("source_documents", ARRAY(UUID(as_uuid=True)), server_default="{}"),
        sa.Column("confidence_score", sa.Float, nullable=True),

        # Thinking Content (fuer LLMs mit Thinking Mode)
        sa.Column("thinking_content", sa.Text, nullable=True),

        # Model Information
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("tokens_input", sa.Integer, nullable=True),
        sa.Column("tokens_output", sa.Integer, nullable=True),
        sa.Column("generation_time_ms", sa.Integer, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_rag_chat_messages_session", "rag_chat_messages", ["session_id"])
    op.create_index("ix_rag_chat_messages_created", "rag_chat_messages", ["created_at"])
    op.create_index("ix_rag_chat_messages_role", "rag_chat_messages", ["role"])

    # =========================================================================
    # 5. RAG LLM MODELS TABLE
    # Registrierte LLM Modelle und ihre Konfiguration
    # =========================================================================
    op.create_table(
        "rag_llm_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Model Identifikation
        sa.Column("model_name", sa.String(100), nullable=False, unique=True),
        sa.Column("model_type", sa.String(50), nullable=False),  # chat, embedding, reranker
        sa.Column("provider", sa.String(50), nullable=False),    # ollama, llama.cpp, huggingface-tei

        # Model Specs
        sa.Column("parameters_billions", sa.Float, nullable=True),
        sa.Column("context_window", sa.Integer, nullable=True),
        sa.Column("quantization", sa.String(20), nullable=True),  # Q4_K_M, Q8_0, FP16, etc.

        # Resource Requirements
        sa.Column("ram_required_gb", sa.Float, nullable=True),
        sa.Column("vram_required_gb", sa.Float, nullable=True),

        # Performance Metrics
        sa.Column("avg_tokens_per_second", sa.Float, nullable=True),
        sa.Column("avg_latency_ms", sa.Integer, nullable=True),

        # Routing Configuration
        sa.Column("use_case", sa.String(50), nullable=True),  # realtime, batch, embedding, reranking
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Endpoint Configuration
        sa.Column("endpoint_url", sa.String(255), nullable=True),
        sa.Column("api_key_env_var", sa.String(100), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_rag_llm_models_type", "rag_llm_models", ["model_type"])
    op.create_index("ix_rag_llm_models_use_case", "rag_llm_models", ["use_case"])
    op.create_index("ix_rag_llm_models_active", "rag_llm_models", ["is_active"])

    # =========================================================================
    # 6. RAG BATCH JOBS TABLE
    # Tracking fuer Batch-Processing (Reports, Customer Card Updates)
    # =========================================================================
    op.create_table(
        "rag_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Job Identifikation
        sa.Column("job_type", sa.String(50), nullable=False),  # customer_card_sync, report_generation, reembedding, chunk_documents
        sa.Column("job_name", sa.String(255), nullable=True),

        # User der den Job gestartet hat (optional fuer automatische Jobs)
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Job Parameters
        sa.Column("parameters", JSONB, server_default="{}"),

        # Status Tracking
        sa.Column("status", sa.String(20), server_default="pending"),  # pending, running, completed, failed, cancelled
        sa.Column("progress_percent", sa.Integer, server_default="0"),
        sa.Column("progress_message", sa.Text, nullable=True),
        sa.Column("items_total", sa.Integer, nullable=True),
        sa.Column("items_processed", sa.Integer, server_default="0"),
        sa.Column("items_failed", sa.Integer, server_default="0"),

        # Results
        sa.Column("result", JSONB, nullable=True),
        sa.Column("output_file_path", sa.String(500), nullable=True),

        # Error Handling
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_stack", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("max_retries", sa.Integer, server_default="3"),

        # Timing
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_rag_batch_jobs_status", "rag_batch_jobs", ["status"])
    op.create_index("ix_rag_batch_jobs_type", "rag_batch_jobs", ["job_type"])
    op.create_index("ix_rag_batch_jobs_scheduled", "rag_batch_jobs", ["scheduled_at"])
    op.create_index("ix_rag_batch_jobs_created_by", "rag_batch_jobs", ["created_by_id"])
    op.create_index("ix_rag_batch_jobs_type_status", "rag_batch_jobs", ["job_type", "status"])

    # =========================================================================
    # 7. RAG ANALYTICS TABLE
    # Tracking von Nutzung und Performance
    # =========================================================================
    op.create_table(
        "rag_analytics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Event Type
        sa.Column("event_type", sa.String(50), nullable=False),  # search, chat, report, customer_card_view

        # Context
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),

        # Query/Request Details
        sa.Column("query_text", sa.Text, nullable=True),

        # Results
        sa.Column("results_count", sa.Integer, nullable=True),
        sa.Column("top_result_score", sa.Float, nullable=True),

        # Performance
        sa.Column("total_latency_ms", sa.Integer, nullable=True),
        sa.Column("embedding_latency_ms", sa.Integer, nullable=True),
        sa.Column("search_latency_ms", sa.Integer, nullable=True),
        sa.Column("rerank_latency_ms", sa.Integer, nullable=True),
        sa.Column("llm_latency_ms", sa.Integer, nullable=True),

        # Model Info
        sa.Column("llm_model_used", sa.String(100), nullable=True),
        sa.Column("tokens_input", sa.Integer, nullable=True),
        sa.Column("tokens_output", sa.Integer, nullable=True),

        # User Feedback
        sa.Column("feedback_rating", sa.Integer, nullable=True),  # 1-5
        sa.Column("feedback_text", sa.Text, nullable=True),

        # Timestamp
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Query Embedding fuer Analytics (optional, fuer Trend-Analyse)
    op.execute("""
        ALTER TABLE rag_analytics
        ADD COLUMN query_embedding vector(1024)
    """)

    op.create_index("ix_rag_analytics_event_type", "rag_analytics", ["event_type"])
    op.create_index("ix_rag_analytics_created", "rag_analytics", ["created_at"])
    op.create_index("ix_rag_analytics_user", "rag_analytics", ["user_id"])
    op.create_index("ix_rag_analytics_event_created", "rag_analytics", ["event_type", "created_at"])

    # =========================================================================
    # 8. DATABASE FUNCTIONS
    # =========================================================================

    # Semantic Search Function
    op.execute("""
        CREATE OR REPLACE FUNCTION rag_semantic_search(
            query_embedding vector(1024),
            match_threshold FLOAT DEFAULT 0.7,
            match_count INTEGER DEFAULT 20,
            filter_document_ids UUID[] DEFAULT NULL,
            filter_section_types VARCHAR(50)[] DEFAULT NULL
        )
        RETURNS TABLE (
            chunk_id UUID,
            document_id UUID,
            chunk_text TEXT,
            chunk_index INTEGER,
            page_number INTEGER,
            section_type VARCHAR(50),
            similarity FLOAT
        )
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN QUERY
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.chunk_text,
                c.chunk_index,
                c.page_number,
                c.section_type,
                1 - (c.embedding <=> query_embedding) AS similarity
            FROM rag_document_chunks c
            WHERE
                -- Similarity Threshold
                1 - (c.embedding <=> query_embedding) > match_threshold
                -- Optional Document Filter
                AND (filter_document_ids IS NULL OR c.document_id = ANY(filter_document_ids))
                -- Optional Section Type Filter
                AND (filter_section_types IS NULL OR c.section_type = ANY(filter_section_types))
            ORDER BY c.embedding <=> query_embedding
            LIMIT match_count;
        END;
        $$;
    """)

    # Hybrid Search Function (Semantic + Keyword)
    op.execute("""
        CREATE OR REPLACE FUNCTION rag_hybrid_search(
            query_embedding vector(1024),
            query_text TEXT,
            semantic_weight FLOAT DEFAULT 0.7,
            keyword_weight FLOAT DEFAULT 0.3,
            match_count INTEGER DEFAULT 20
        )
        RETURNS TABLE (
            chunk_id UUID,
            document_id UUID,
            chunk_text TEXT,
            combined_score FLOAT,
            semantic_score FLOAT,
            keyword_score FLOAT
        )
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN QUERY
            WITH semantic_results AS (
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_text,
                    1 - (c.embedding <=> query_embedding) AS score
                FROM rag_document_chunks c
                ORDER BY c.embedding <=> query_embedding
                LIMIT match_count * 2
            ),
            keyword_results AS (
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_text,
                    similarity(c.chunk_text, query_text) AS score
                FROM rag_document_chunks c
                WHERE c.chunk_text % query_text
                ORDER BY similarity(c.chunk_text, query_text) DESC
                LIMIT match_count * 2
            ),
            combined AS (
                SELECT
                    COALESCE(s.id, k.id) AS id,
                    COALESCE(s.document_id, k.document_id) AS document_id,
                    COALESCE(s.chunk_text, k.chunk_text) AS chunk_text,
                    COALESCE(s.score, 0) AS sem_score,
                    COALESCE(k.score, 0) AS kw_score
                FROM semantic_results s
                FULL OUTER JOIN keyword_results k ON s.id = k.id
            )
            SELECT
                combined.id AS chunk_id,
                combined.document_id,
                combined.chunk_text,
                (combined.sem_score * semantic_weight + combined.kw_score * keyword_weight) AS combined_score,
                combined.sem_score AS semantic_score,
                combined.kw_score AS keyword_score
            FROM combined
            ORDER BY combined_score DESC
            LIMIT match_count;
        END;
        $$;
    """)

    # Updated_at Trigger Function (falls noch nicht existiert)
    op.execute("""
        CREATE OR REPLACE FUNCTION rag_update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Triggers fuer updated_at
    op.execute("""
        CREATE TRIGGER update_rag_document_chunks_updated_at
            BEFORE UPDATE ON rag_document_chunks
            FOR EACH ROW
            EXECUTE FUNCTION rag_update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_rag_customer_cards_updated_at
            BEFORE UPDATE ON rag_customer_cards
            FOR EACH ROW
            EXECUTE FUNCTION rag_update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_rag_chat_sessions_updated_at
            BEFORE UPDATE ON rag_chat_sessions
            FOR EACH ROW
            EXECUTE FUNCTION rag_update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_rag_llm_models_updated_at
            BEFORE UPDATE ON rag_llm_models
            FOR EACH ROW
            EXECUTE FUNCTION rag_update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_rag_batch_jobs_updated_at
            BEFORE UPDATE ON rag_batch_jobs
            FOR EACH ROW
            EXECUTE FUNCTION rag_update_updated_at_column();
    """)

    # =========================================================================
    # 9. SEED DATA: Default LLM Models
    # =========================================================================
    op.execute("""
        INSERT INTO rag_llm_models (
            model_name, model_type, provider,
            parameters_billions, context_window, quantization,
            ram_required_gb, vram_required_gb,
            avg_tokens_per_second,
            use_case, priority, is_active,
            endpoint_url
        ) VALUES
        -- Embedding Model
        (
            'intfloat/multilingual-e5-large', 'embedding', 'huggingface-tei',
            0.56, 512, NULL,
            2.5, NULL,
            50,
            'embedding', 1, true,
            'http://embedding-service:8080'
        ),
        -- Reranker Model
        (
            'BAAI/bge-reranker-v2-m3', 'reranker', 'huggingface-tei',
            0.56, 512, NULL,
            1.5, NULL,
            100,
            'reranking', 1, true,
            'http://reranker-service:8080'
        ),
        -- Real-Time LLM
        (
            'qwen3:8b-q4_K_M', 'chat', 'ollama',
            8, 128000, 'Q4_K_M',
            8, NULL,
            18,
            'realtime', 1, true,
            'http://ollama:11434'
        ),
        -- Deep Analysis LLM
        (
            'qwen3:14b-q4_K_M', 'chat', 'ollama',
            14, 128000, 'Q4_K_M',
            12, NULL,
            10,
            'batch', 2, true,
            'http://ollama:11434'
        )
        ON CONFLICT (model_name) DO NOTHING;
    """)


def downgrade() -> None:
    """
    Downgrade: RAG Intelligence Layer Tabellen und Funktionen entfernen.
    """
    # Triggers entfernen
    op.execute("DROP TRIGGER IF EXISTS update_rag_batch_jobs_updated_at ON rag_batch_jobs")
    op.execute("DROP TRIGGER IF EXISTS update_rag_llm_models_updated_at ON rag_llm_models")
    op.execute("DROP TRIGGER IF EXISTS update_rag_chat_sessions_updated_at ON rag_chat_sessions")
    op.execute("DROP TRIGGER IF EXISTS update_rag_customer_cards_updated_at ON rag_customer_cards")
    op.execute("DROP TRIGGER IF EXISTS update_rag_document_chunks_updated_at ON rag_document_chunks")

    # Functions entfernen
    op.execute("DROP FUNCTION IF EXISTS rag_update_updated_at_column()")
    op.execute("DROP FUNCTION IF EXISTS rag_hybrid_search(vector, TEXT, FLOAT, FLOAT, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS rag_semantic_search(vector, FLOAT, INTEGER, UUID[], VARCHAR[])")

    # Tabellen entfernen (in umgekehrter Reihenfolge wegen Foreign Keys)
    op.drop_table("rag_analytics")
    op.drop_table("rag_batch_jobs")
    op.drop_table("rag_llm_models")
    op.drop_table("rag_chat_messages")
    op.drop_table("rag_chat_sessions")
    op.drop_table("rag_customer_cards")
    op.drop_table("rag_document_chunks")
