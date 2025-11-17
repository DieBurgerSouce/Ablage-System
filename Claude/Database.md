Database Schema - Enhanced Production System

🗂️ ALLE TABELLEN IM ÜBERBLICK
#TabelleKategorieZweckBeziehungenWichtigkeit1usersAuthBenutzer-Accounts→ documents, audit_logs, workflows⭐⭐⭐⭐⭐2rolesAuthRollen-Definition← user_roles⭐⭐⭐⭐⭐3user_rolesAuthUser-Rollen-Zuordnungusers ↔ roles⭐⭐⭐⭐⭐4permissionsAuthGranulare Berechtigungen← role_permissions⭐⭐⭐⭐5role_permissionsAuthRollen-Rechte-Mappingroles ↔ permissions⭐⭐⭐⭐6api_keysAuthAPI-Zugangsschlüssel→ users⭐⭐⭐⭐7sessionsAuthAktive User-Sessions→ users⭐⭐⭐8documentsCoreHauptdokumentenregister→ suppliers, jobs, tags⭐⭐⭐⭐⭐9processing_jobsCoreVerarbeitungs-Jobs→ documents, ocr_results⭐⭐⭐⭐⭐10job_eventsCoreJob-Event-Log→ processing_jobs⭐⭐⭐⭐11ocr_resultsCoreOCR-Ergebnisse→ documents, jobs⭐⭐⭐⭐⭐12document_versionsCoreDokumenten-Versionierung→ documents⭐⭐⭐⭐13document_pagesCoreMehrseitige Dokumente→ documents⭐⭐⭐⭐14document_relationsCoreDokument-Beziehungendocuments ↔ documents⭐⭐⭐⭐15suppliersMaster DataLieferanten-Stammdaten← documents⭐⭐⭐⭐⭐16supplier_contactsMaster DataLieferanten-Kontakte→ suppliers⭐⭐⭐17supplier_templatesMaster DataDokumenten-Templates→ suppliers⭐⭐⭐⭐18categoriesMaster DataDokumenten-Kategorien← documents⭐⭐⭐19tagsMaster DataFlexible Tags← document_tags⭐⭐⭐⭐20document_tagsMaster DataDokument-Tag-Zuordnungdocuments ↔ tags⭐⭐⭐⭐21workflowsAutomationWorkflow-Definitionen→ workflow_steps⭐⭐⭐⭐22workflow_stepsAutomationWorkflow-Schritte→ workflows⭐⭐⭐⭐23workflow_executionsAutomationWorkflow-Läufe→ workflows, documents⭐⭐⭐⭐24workflow_step_executionsAutomationStep-Execution-Log→ workflow_executions⭐⭐⭐25extraction_rulesML/AICustom Extraction Rules→ suppliers⭐⭐⭐⭐26extraction_rule_versionsML/AIRule-Versionierung→ extraction_rules⭐⭐⭐27training_dataML/AIML Training Samples→ documents⭐⭐⭐28model_performanceML/AIModel Performance Tracking-⭐⭐⭐29notificationsSystemUser-Benachrichtigungen→ users, documents⭐⭐⭐⭐30notification_preferencesSystemNotification Settings→ users⭐⭐⭐31email_queueSystemOutgoing Email Queue→ users⭐⭐⭐32email_templatesSystemEmail-Vorlagen-⭐⭐⭐33webhooksIntegrationWebhook-Endpunkte→ users⭐⭐⭐⭐34webhook_deliveriesIntegrationWebhook-Delivery-Log→ webhooks⭐⭐⭐35document_exportsIntegrationExport-Historie→ documents, users⭐⭐⭐36integrationsIntegrationExterne Integrationen-⭐⭐⭐37integration_logsIntegrationIntegration Event Log→ integrations⭐⭐⭐38backend_metricsMonitoringBackend Performance-⭐⭐⭐⭐⭐39system_metricsMonitoringSystem Health Metrics-⭐⭐⭐⭐40error_logsMonitoringFehler-Tracking→ users, documents⭐⭐⭐⭐41audit_logsMonitoringVollständiger Audit TrailALL⭐⭐⭐⭐⭐42system_settingsConfigGlobale Einstellungen-⭐⭐⭐⭐43feature_flagsConfigFeature Toggles-⭐⭐⭐44scheduled_tasksConfigCron-Jobs / Scheduled Tasks-⭐⭐⭐
Total: 44 Tabellen

🔧 ERWEITERTE SCHEMA-DEFINITIONEN
AUTH & USER MANAGEMENT
sql-- ============================================================================
-- AUTHENTICATION & AUTHORIZATION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- USERS
-- ----------------------------------------------------------------------------

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Authentication
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    username VARCHAR(100) UNIQUE,
    
    -- Profile
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    display_name VARCHAR(200),
    avatar_url TEXT,
    
    -- Contact
    phone VARCHAR(50),
    department VARCHAR(100),
    job_title VARCHAR(100),
    
    -- Settings
    language VARCHAR(10) DEFAULT 'de',
    timezone VARCHAR(50) DEFAULT 'Europe/Berlin',
    preferences JSONB DEFAULT '{}'::jsonb,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP WITH TIME ZONE,
    
    -- Security
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    two_factor_secret VARCHAR(100),
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_login_ip INET,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_active ON users(is_active) WHERE is_active = TRUE AND deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- ROLES
-- ----------------------------------------------------------------------------

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Hierarchy
    level INTEGER NOT NULL DEFAULT 0, -- 0=lowest, higher=more power
    
    -- System roles (can't be deleted)
    is_system BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_roles_level ON roles(level DESC);

-- Default roles
INSERT INTO roles (name, display_name, description, level, is_system) VALUES
    ('super_admin', 'Super Administrator', 'Full system access', 100, true),
    ('admin', 'Administrator', 'Administrative access', 90, true),
    ('manager', 'Manager', 'Manage documents and users', 50, true),
    ('editor', 'Editor', 'Edit and process documents', 30, true),
    ('viewer', 'Viewer', 'Read-only access', 10, true),
    ('api_user', 'API User', 'Programmatic access only', 20, true);

-- ----------------------------------------------------------------------------
-- USER_ROLES (Many-to-Many)
-- ----------------------------------------------------------------------------

CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    
    -- Metadata
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_by UUID REFERENCES users(id),
    expires_at TIMESTAMP WITH TIME ZONE,
    
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);

-- ----------------------------------------------------------------------------
-- PERMISSIONS
-- ----------------------------------------------------------------------------

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Permission identity
    name VARCHAR(100) NOT NULL UNIQUE, -- e.g., 'documents.read', 'documents.delete'
    resource VARCHAR(50) NOT NULL, -- e.g., 'documents', 'suppliers', 'users'
    action VARCHAR(50) NOT NULL, -- e.g., 'read', 'create', 'update', 'delete'
    
    description TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_permissions_resource ON permissions(resource);

-- Default permissions
INSERT INTO permissions (name, resource, action, description) VALUES
    -- Documents
    ('documents.read', 'documents', 'read', 'View documents'),
    ('documents.create', 'documents', 'create', 'Upload new documents'),
    ('documents.update', 'documents', 'update', 'Edit document metadata'),
    ('documents.delete', 'documents', 'delete', 'Delete documents'),
    ('documents.process', 'documents', 'process', 'Trigger document processing'),
    ('documents.export', 'documents', 'export', 'Export documents'),
    
    -- Suppliers
    ('suppliers.read', 'suppliers', 'read', 'View suppliers'),
    ('suppliers.create', 'suppliers', 'create', 'Create suppliers'),
    ('suppliers.update', 'suppliers', 'update', 'Edit suppliers'),
    ('suppliers.delete', 'suppliers', 'delete', 'Delete suppliers'),
    
    -- Users
    ('users.read', 'users', 'read', 'View users'),
    ('users.create', 'users', 'create', 'Create users'),
    ('users.update', 'users', 'update', 'Edit users'),
    ('users.delete', 'users', 'delete', 'Delete users'),
    
    -- System
    ('system.settings', 'system', 'manage', 'Manage system settings'),
    ('system.metrics', 'system', 'view', 'View system metrics'),
    ('system.logs', 'system', 'view', 'View system logs');

-- ----------------------------------------------------------------------------
-- ROLE_PERMISSIONS (Many-to-Many)
-- ----------------------------------------------------------------------------

CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (role_id, permission_id)
);

-- Assign default permissions
-- Super Admin: all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT 
    (SELECT id FROM roles WHERE name = 'super_admin'),
    id
FROM permissions;

-- Admin: all except system settings
INSERT INTO role_permissions (role_id, permission_id)
SELECT 
    (SELECT id FROM roles WHERE name = 'admin'),
    id
FROM permissions
WHERE name NOT LIKE 'system.%';

-- Viewer: only read permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT 
    (SELECT id FROM roles WHERE name = 'viewer'),
    id
FROM permissions
WHERE action = 'read';

-- ----------------------------------------------------------------------------
-- API_KEYS
-- ----------------------------------------------------------------------------

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Key
    key_hash VARCHAR(255) NOT NULL UNIQUE, -- SHA-256 of the key
    key_prefix VARCHAR(10) NOT NULL, -- First 8 chars for identification
    
    -- Metadata
    name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Permissions
    allowed_ips INET[], -- IP whitelist
    rate_limit INTEGER DEFAULT 1000, -- Requests per hour
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,
    
    -- Usage tracking
    last_used_at TIMESTAMP WITH TIME ZONE,
    total_requests BIGINT DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- SESSIONS
-- ----------------------------------------------------------------------------

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session data
    session_token VARCHAR(255) NOT NULL UNIQUE,
    refresh_token VARCHAR(255) UNIQUE,
    
    -- Client info
    ip_address INET,
    user_agent TEXT,
    device_info JSONB,
    
    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Security
    is_valid BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_token ON sessions(session_token) WHERE is_valid = TRUE;
CREATE INDEX idx_sessions_expires ON sessions(expires_at) WHERE is_valid = TRUE;

DOCUMENT ENHANCEMENTS
sql-- ============================================================================
-- ENHANCED DOCUMENT MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- DOCUMENT_PAGES - For multi-page documents
-- ----------------------------------------------------------------------------

CREATE TABLE document_pages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Page info
    page_number INTEGER NOT NULL,
    
    -- Storage
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    
    -- OCR per page
    ocr_text TEXT,
    ocr_confidence DECIMAL(5,2),
    ocr_data JSONB,
    
    -- Dimensions
    width_px INTEGER,
    height_px INTEGER,
    dpi INTEGER,
    
    -- Processing
    processed_at TIMESTAMP WITH TIME ZONE,
    processing_time_ms INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_page UNIQUE(document_id, page_number),
    CONSTRAINT valid_page_number CHECK (page_number > 0)
);

CREATE INDEX idx_document_pages_document ON document_pages(document_id, page_number);

-- ----------------------------------------------------------------------------
-- DOCUMENT_RELATIONS - Links between documents
-- ----------------------------------------------------------------------------

CREATE TYPE relation_type AS ENUM (
    'corrects',        -- Korrektur zu
    'replaces',        -- Ersetzt
    'references',      -- Referenziert
    'attachment_to',   -- Anhang zu
    'delivery_for',    -- Lieferschein zu Rechnung
    'order_for',       -- Bestellung zu Rechnung
    'credit_note_for', -- Gutschrift zu Rechnung
    'reminder_for',    -- Mahnung zu Rechnung
    'duplicate_of'     -- Duplikat von
);

CREATE TABLE document_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    source_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    relation_type relation_type NOT NULL,
    
    -- Metadata
    confidence DECIMAL(5,2), -- How confident are we about this relation
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    CONSTRAINT no_self_relation CHECK (source_document_id != target_document_id),
    CONSTRAINT unique_relation UNIQUE(source_document_id, target_document_id, relation_type)
);

CREATE INDEX idx_document_relations_source ON document_relations(source_document_id);
CREATE INDEX idx_document_relations_target ON document_relations(target_document_id);
CREATE INDEX idx_document_relations_type ON document_relations(relation_type);

-- ----------------------------------------------------------------------------
-- CATEGORIES - Hierarchical document categories
-- ----------------------------------------------------------------------------

CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    parent_id UUID REFERENCES categories(id) ON DELETE CASCADE,
    
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Path for hierarchical queries
    path TEXT NOT NULL, -- e.g., 'finance/invoices/incoming'
    
    -- Icon/Color for UI
    icon VARCHAR(50),
    color VARCHAR(7),
    
    -- Ordering
    sort_order INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_slug UNIQUE(slug),
    CONSTRAINT unique_path UNIQUE(path)
);

CREATE INDEX idx_categories_parent ON categories(parent_id);
CREATE INDEX idx_categories_path ON categories USING gin(string_to_array(path, '/'));

-- Default categories
INSERT INTO categories (name, slug, path) VALUES
    ('Finanzen', 'finance', 'finance'),
    ('Eingangsrechnungen', 'invoices-incoming', 'finance/invoices-incoming'),
    ('Ausgangsrechnungen', 'invoices-outgoing', 'finance/invoices-outgoing'),
    ('Verträge', 'contracts', 'contracts'),
    ('Personal', 'hr', 'hr'),
    ('Lieferscheine', 'delivery-notes', 'logistics/delivery-notes');

-- Add category to documents
ALTER TABLE documents ADD COLUMN category_id UUID REFERENCES categories(id);
CREATE INDEX idx_documents_category ON documents(category_id);

WORKFLOW AUTOMATION
sql-- ============================================================================
-- WORKFLOW AUTOMATION
-- ============================================================================

CREATE TYPE workflow_trigger AS ENUM (
    'manual',
    'document_uploaded',
    'document_processed',
    'confidence_below_threshold',
    'supplier_detected',
    'schedule',
    'webhook'
);

CREATE TYPE step_type AS ENUM (
    'classify_document',
    'extract_data',
    'validate_data',
    'send_notification',
    'send_email',
    'call_webhook',
    'update_field',
    'assign_user',
    'create_relation',
    'export_document',
    'conditional',
    'wait'
);

CREATE TYPE execution_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'skipped',
    'cancelled'
);

-- ----------------------------------------------------------------------------
-- WORKFLOWS
-- ----------------------------------------------------------------------------

CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Trigger
    trigger_type workflow_trigger NOT NULL,
    trigger_config JSONB, -- Configuration for trigger
    
    -- Conditions (when to run)
    conditions JSONB, -- JSON Logic rules
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_system BOOLEAN DEFAULT FALSE, -- System workflows can't be deleted
    
    -- Statistics
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    last_executed_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_workflows_active ON workflows(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_workflows_trigger ON workflows(trigger_type);

-- ----------------------------------------------------------------------------
-- WORKFLOW_STEPS
-- ----------------------------------------------------------------------------

CREATE TABLE workflow_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Step definition
    name VARCHAR(255) NOT NULL,
    step_type step_type NOT NULL,
    step_config JSONB NOT NULL, -- Step-specific configuration
    
    -- Execution order
    step_order INTEGER NOT NULL,
    
    -- Conditions
    conditions JSONB, -- Run step only if conditions met
    
    -- Error handling
    on_error VARCHAR(50) DEFAULT 'fail', -- 'fail', 'continue', 'retry'
    max_retries INTEGER DEFAULT 0,
    retry_delay_seconds INTEGER DEFAULT 60,
    
    -- Timeout
    timeout_seconds INTEGER DEFAULT 300,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_step_order UNIQUE(workflow_id, step_order)
);

CREATE INDEX idx_workflow_steps_workflow ON workflow_steps(workflow_id, step_order);

-- ----------------------------------------------------------------------------
-- WORKFLOW_EXECUTIONS
-- ----------------------------------------------------------------------------

CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    
    -- Execution context
    trigger_event VARCHAR(100),
    trigger_data JSONB,
    
    -- Status
    status execution_status DEFAULT 'pending',
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    
    -- Results
    success BOOLEAN,
    error_message TEXT,
    
    -- Output
    execution_log JSONB, -- Detailed step-by-step log
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_executions_workflow ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_document ON workflow_executions(document_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);
CREATE INDEX idx_workflow_executions_started ON workflow_executions(started_at DESC);

-- ----------------------------------------------------------------------------
-- WORKFLOW_STEP_EXECUTIONS
-- ----------------------------------------------------------------------------

CREATE TABLE workflow_step_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    step_id UUID NOT NULL REFERENCES workflow_steps(id) ON DELETE CASCADE,
    
    -- Status
    status execution_status DEFAULT 'pending',
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    
    -- Results
    success BOOLEAN,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Input/Output
    input_data JSONB,
    output_data JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_step_executions_execution ON workflow_step_executions(execution_id);
CREATE INDEX idx_workflow_step_executions_step ON workflow_step_executions(step_id);

-- Example workflow: Auto-assign invoices to accountant
INSERT INTO workflows (name, description, trigger_type, trigger_config, is_system) VALUES
    ('Auto-assign Invoices', 
     'Automatically assign invoices above 1000€ to accountant for review',
     'document_processed',
     '{"document_types": ["invoice"]}'::jsonb,
     false);

ML/AI & EXTRACTION RULES
sql-- ============================================================================
-- MACHINE LEARNING & EXTRACTION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- EXTRACTION_RULES - Custom field extraction rules
-- ----------------------------------------------------------------------------

CREATE TYPE rule_type AS ENUM (
    'regex',
    'position',
    'template',
    'ml_model'
);

CREATE TABLE extraction_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Association
    supplier_id UUID REFERENCES suppliers(id) ON DELETE CASCADE,
    document_type document_type,
    
    -- Rule identity
    rule_name VARCHAR(255) NOT NULL,
    field_name VARCHAR(100) NOT NULL, -- e.g., 'invoice_number', 'total_amount'
    
    -- Rule definition
    rule_type rule_type NOT NULL,
    rule_config JSONB NOT NULL,
    /*
    Examples:
    
    regex: {
        "pattern": "Rechnungsnr\\.?:\\s*([A-Z0-9-]+)",
        "flags": "i"
    }
    
    position: {
        "x": 450,
        "y": 100,
        "width": 200,
        "height": 30,
        "tolerance": 10
    }
    
    template: {
        "template_id": "uuid",
        "anchor_text": "Rechnungsdatum",
        "relative_position": {"x": 100, "y": 0}
    }
    
    ml_model: {
        "model_name": "invoice_number_extractor",
        "model_version": "1.2.0"
    }
    */
    
    -- Validation
    validation_regex VARCHAR(500),
    required BOOLEAN DEFAULT FALSE,
    
    -- Quality
    success_rate DECIMAL(5,2),
    avg_confidence DECIMAL(5,2),
    usage_count INTEGER DEFAULT 0,
    
    -- Priority (higher = try first)
    priority INTEGER DEFAULT 0,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_extraction_rules_supplier ON extraction_rules(supplier_id);
CREATE INDEX idx_extraction_rules_type ON extraction_rules(document_type);
CREATE INDEX idx_extraction_rules_field ON extraction_rules(field_name);
CREATE INDEX idx_extraction_rules_active ON extraction_rules(is_active) WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- EXTRACTION_RULE_VERSIONS - Rule version history
-- ----------------------------------------------------------------------------

CREATE TABLE extraction_rule_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    rule_id UUID NOT NULL REFERENCES extraction_rules(id) ON DELETE CASCADE,
    
    version INTEGER NOT NULL,
    rule_config JSONB NOT NULL,
    
    -- Performance before/after
    performance_delta JSONB, -- Improvement metrics
    
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    CONSTRAINT unique_rule_version UNIQUE(rule_id, version)
);

-- ----------------------------------------------------------------------------
-- TRAINING_DATA - For ML model improvement
-- ----------------------------------------------------------------------------

CREATE TABLE training_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Ground truth
    field_name VARCHAR(100) NOT NULL,
    expected_value TEXT NOT NULL,
    extracted_value TEXT,
    
    -- Context
    extraction_method VARCHAR(100), -- Which rule/model was used
    was_correct BOOLEAN,
    
    -- Image region (for position-based training)
    bounding_box JSONB,
    
    -- Validation
    validated_by UUID REFERENCES users(id),
    validated_at TIMESTAMP WITH TIME ZONE,
    
    -- Training status
    used_for_training BOOLEAN DEFAULT FALSE,
    training_batch_id VARCHAR(100),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_training_data_document ON training_data(document_id);
CREATE INDEX idx_training_data_field ON training_data(field_name);
CREATE INDEX idx_training_data_untrained ON training_data(used_for_training) WHERE used_for_training = FALSE;

-- ----------------------------------------------------------------------------
-- MODEL_PERFORMANCE - Track ML model metrics over time
-- ----------------------------------------------------------------------------

CREATE TABLE model_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    
    -- Metrics
    metric_date DATE NOT NULL,
    
    accuracy DECIMAL(5,2),
    precision_score DECIMAL(5,2),
    recall DECIMAL(5,2),
    f1_score DECIMAL(5,2),
    
    -- Per-field metrics
    field_metrics JSONB,
    
    -- Volume
    total_predictions INTEGER,
    correct_predictions INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_model_date UNIQUE(model_name, model_version, metric_date)
);

CREATE INDEX idx_model_performance_model ON model_performance(model_name, model_version);
CREATE INDEX idx_model_performance_date ON model_performance(metric_date DESC);

NOTIFICATIONS & INTEGRATIONS
sql-- ============================================================================
-- NOTIFICATIONS & COMMUNICATION
-- ============================================================================

CREATE TYPE notification_type AS ENUM (
    'info',
    'success',
    'warning',
    'error',
    'document_processed',
    'review_needed',
    'workflow_completed',
    'system_alert'
);

CREATE TYPE notification_channel AS ENUM (
    'in_app',
    'email',
    'webhook',
    'sms'
);

-- ----------------------------------------------------------------------------
-- NOTIFICATIONS
-- ----------------------------------------------------------------------------

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Notification content
    type notification_type NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    
    -- Context
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    link_url TEXT,
    action_button_text VARCHAR(100),
    action_button_url TEXT,
    
    -- Metadata
    metadata JSONB,
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    
    -- Delivery
    delivered_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE INDEX idx_notifications_unread ON notifications(user_id) WHERE is_read = FALSE;
CREATE INDEX idx_notifications_document ON notifications(document_id);

-- ----------------------------------------------------------------------------
-- NOTIFICATION_PREFERENCES
-- ----------------------------------------------------------------------------

CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    
    -- Channel preferences
    email_enabled BOOLEAN DEFAULT TRUE,
    in_app_enabled BOOLEAN DEFAULT TRUE,
    
    -- Type preferences (JSONB for flexibility)
    preferences JSONB DEFAULT '{
        "document_processed": {"email": true, "in_app": true},
        "review_needed": {"email": true, "in_app": true},
        "workflow_completed": {"email": false, "in_app": true},
        "system_alert": {"email": true, "in_app": true}
    }'::jsonb,
    
    -- Quiet hours
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    quiet_hours_timezone VARCHAR(50) DEFAULT 'Europe/Berlin',
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- EMAIL_QUEUE
-- ----------------------------------------------------------------------------

CREATE TYPE email_status AS ENUM (
    'queued',
    'sending',
    'sent',
    'failed',
    'bounced'
);

CREATE TABLE email_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Recipient
    to_address VARCHAR(255) NOT NULL,
    to_name VARCHAR(255),
    cc_addresses TEXT[],
    bcc_addresses TEXT[],
    
    -- Content
    subject VARCHAR(500) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,
    
    -- Template
    template_id UUID,
    template_data JSONB,
    
    -- Attachments
    attachments JSONB,
    
    -- Status
    status email_status DEFAULT 'queued',
    
    -- Delivery
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Metadata
    user_id UUID REFERENCES users(id),
    document_id UUID REFERENCES documents(id),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_email_queue_status ON email_queue(status, next_attempt_at);
CREATE INDEX idx_email_queue_user ON email_queue(user_id);

-- ----------------------------------------------------------------------------
-- EMAIL_TEMPLATES
-- ----------------------------------------------------------------------------

CREATE TABLE email_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    
    subject VARCHAR(500) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,
    
    -- Variables used in template
    variables TEXT[], -- e.g., ['user_name', 'document_title']
    
    -- Categorization
    category VARCHAR(100),
    
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Default templates
INSERT INTO email_templates (name, category, subject, body_html, body_text, variables) VALUES
    ('document_processed', 'documents', 
     'Document {{document_title}} processed', 
     '<p>Hi {{user_name}},</p><p>Your document <strong>{{document_title}}</strong> has been processed successfully.</p>',
     'Hi {{user_name}}, Your document {{document_title}} has been processed successfully.',
     ARRAY['user_name', 'document_title']),
    
    ('review_needed', 'documents',
     'Document review needed: {{document_title}}',
     '<p>Hi {{user_name}},</p><p>Document <strong>{{document_title}}</strong> needs your review (confidence: {{confidence}}%).</p>',
     'Hi {{user_name}}, Document {{document_title}} needs your review (confidence: {{confidence}}%).',
     ARRAY['user_name', 'document_title', 'confidence']);

-- ============================================================================
-- WEBHOOKS & INTEGRATIONS
-- ============================================================================

CREATE TYPE webhook_event AS ENUM (
    'document.created',
    'document.processed',
    'document.updated',
    'document.deleted',
    'workflow.completed',
    'workflow.failed'
);

-- ----------------------------------------------------------------------------
-- WEBHOOKS
-- ----------------------------------------------------------------------------

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Webhook config
    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    
    -- Events to listen to
    events webhook_event[] NOT NULL,
    
    -- Security
    secret VARCHAR(255), -- For HMAC signature
    
    -- Filters
    filters JSONB, -- Additional filtering beyond events
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    headers JSONB, -- Custom headers to send
    
    -- Stats
    total_deliveries INTEGER DEFAULT 0,
    successful_deliveries INTEGER DEFAULT 0,
    failed_deliveries INTEGER DEFAULT 0,
    last_delivery_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_webhooks_user ON webhooks(user_id);
CREATE INDEX idx_webhooks_active ON webhooks(is_active) WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- WEBHOOK_DELIVERIES - Delivery log
-- ----------------------------------------------------------------------------

CREATE TABLE webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    webhook_id UUID NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    
    -- Event
    event webhook_event NOT NULL,
    payload JSONB NOT NULL,
    
    -- Delivery
    attempt INTEGER DEFAULT 1,
    
    -- Response
    http_status INTEGER,
    response_body TEXT,
    response_headers JSONB,
    
    -- Timing
    duration_ms INTEGER,
    
    -- Status
    success BOOLEAN,
    error_message TEXT,
    
    -- Retry
    next_retry_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id, created_at DESC);
CREATE INDEX idx_webhook_deliveries_retry ON webhook_deliveries(next_retry_at) 
    WHERE success = FALSE AND next_retry_at IS NOT NULL;

-- ----------------------------------------------------------------------------
-- DOCUMENT_EXPORTS - Export history
-- ----------------------------------------------------------------------------

CREATE TYPE export_format AS ENUM (
    'pdf',
    'json',
    'xml',
    'csv',
    'excel',
    'zip'
);

CREATE TABLE document_exports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Export config
    export_format export_format NOT NULL,
    
    -- Documents included
    document_ids UUID[] NOT NULL,
    filters JSONB, -- Query used to select documents
    
    -- Output
    file_path TEXT,
    file_size BIGINT,
    download_url TEXT,
    
    -- Status
    status VARCHAR(50) DEFAULT 'processing', -- processing, completed, failed
    
    -- Expiry
    expires_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_document_exports_user ON document_exports(user_id, created_at DESC);
CREATE INDEX idx_document_exports_expires ON document_exports(expires_at) 
    WHERE status = 'completed';

-- ----------------------------------------------------------------------------
-- INTEGRATIONS - External system connections
-- ----------------------------------------------------------------------------

CREATE TYPE integration_type AS ENUM (
    'accounting', -- DATEV, Lexoffice, etc.
    'erp',        -- SAP, etc.
    'storage',    -- Dropbox, Google Drive
    'email',      -- IMAP, Exchange
    'custom'
);

CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Identity
    name VARCHAR(255) NOT NULL,
    type integration_type NOT NULL,
    provider VARCHAR(100), -- 'datev', 'lexoffice', 'sap', etc.
    
    -- Configuration
    config JSONB NOT NULL, -- Encrypted credentials, endpoints, etc.
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    
    -- Health
    health_status VARCHAR(50) DEFAULT 'unknown', -- healthy, degraded, down, unknown
    last_health_check_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_integrations_type ON integrations(type);
CREATE INDEX idx_integrations_active ON integrations(is_active) WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- INTEGRATION_LOGS - Integration event log
-- ----------------------------------------------------------------------------

CREATE TABLE integration_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    
    -- Event
    event_type VARCHAR(100) NOT NULL, -- 'sync', 'export', 'import', 'error'
    
    -- Details
    message TEXT,
    details JSONB,
    
    -- Documents affected
    document_ids UUID[],
    
    -- Status
    success BOOLEAN,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_integration_logs_integration ON integration_logs(integration_id, created_at DESC);
CREATE INDEX idx_integration_logs_error ON integration_logs(integration_id) WHERE success = FALSE;

MONITORING & SYSTEM
sql-- ============================================================================
-- SYSTEM MONITORING & CONFIGURATION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- SYSTEM_METRICS - Overall system health
-- ----------------------------------------------------------------------------

CREATE TABLE system_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    metric_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- System resources
    cpu_usage DECIMAL(5,2),
    ram_usage_gb DECIMAL(10,2),
    ram_total_gb DECIMAL(10,2),
    disk_usage_gb DECIMAL(10,2),
    disk_total_gb DECIMAL(10,2),
    
    -- GPU metrics (if available)
    gpu_usage DECIMAL(5,2),
    gpu_memory_used_gb DECIMAL(10,2),
    gpu_memory_total_gb DECIMAL(10,2),
    gpu_temperature DECIMAL(5,2),
    
    -- Application metrics
    active_jobs INTEGER,
    queued_jobs INTEGER,
    active_users INTEGER,
    documents_today INTEGER,
    
    -- Performance
    avg_response_time_ms INTEGER,
    p95_response_time_ms INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_system_metrics_timestamp ON system_metrics(metric_timestamp DESC);

-- Partition by month
CREATE TABLE system_metrics_y2025m01 PARTITION OF system_metrics
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

-- ----------------------------------------------------------------------------
-- ERROR_LOGS - Application errors
-- ----------------------------------------------------------------------------

CREATE TYPE error_severity AS ENUM (
    'debug',
    'info',
    'warning',
    'error',
    'critical'
);

CREATE TABLE error_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Error details
    severity error_severity NOT NULL,
    error_code VARCHAR(50),
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    
    -- Context
    user_id UUID REFERENCES users(id),
    document_id UUID REFERENCES documents(id),
    job_id UUID REFERENCES processing_jobs(id),
    
    -- Request context
    request_path TEXT,
    request_method VARCHAR(10),
    request_params JSONB,
    
    -- Environment
    hostname VARCHAR(255),
    process_id INTEGER,
    
    -- Grouping (for similar errors)
    error_hash VARCHAR(64), -- Hash for grouping
    occurrence_count INTEGER DEFAULT 1,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_error_logs_severity ON error_logs(severity, created_at DESC);
CREATE INDEX idx_error_logs_hash ON error_logs(error_hash);
CREATE INDEX idx_error_logs_user ON error_logs(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_error_logs_document ON error_logs(document_id) WHERE document_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- SYSTEM_SETTINGS - Global configuration
-- ----------------------------------------------------------------------------

CREATE TABLE system_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    key VARCHAR(255) NOT NULL UNIQUE,
    value JSONB NOT NULL,
    
    description TEXT,
    
    -- Type validation
    value_type VARCHAR(50) NOT NULL, -- 'string', 'number', 'boolean', 'json'
    
    -- Editing
    is_editable BOOLEAN DEFAULT TRUE,
    is_sensitive BOOLEAN DEFAULT FALSE, -- Mask in UI
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by UUID REFERENCES users(id)
);

-- Default settings
INSERT INTO system_settings (key, value, value_type, description) VALUES
    ('ocr.default_backend', '"cpu_surya"', 'string', 'Default OCR backend'),
    ('ocr.confidence_threshold', '80', 'number', 'Minimum confidence for auto-approval'),
    ('ocr.batch_size', '10', 'number', 'Max documents per batch'),
    ('storage.max_file_size_mb', '50', 'number', 'Maximum file upload size in MB'),
    ('storage.retention_days', '90', 'number', 'Document retention period'),
    ('notifications.enabled', 'true', 'boolean', 'Enable notifications system'),
    ('webhooks.max_retries', '3', 'number', 'Maximum webhook delivery retries'),
    ('security.session_timeout_hours', '24', 'number', 'Session timeout in hours'),
    ('security.password_min_length', '8', 'number', 'Minimum password length');

-- ----------------------------------------------------------------------------
-- FEATURE_FLAGS - Feature toggles
-- ----------------------------------------------------------------------------

CREATE TABLE feature_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    
    -- Status
    is_enabled BOOLEAN DEFAULT FALSE,
    
    -- Rollout
    rollout_percentage INTEGER DEFAULT 0, -- 0-100
    enabled_for_user_ids UUID[],
    enabled_for_roles VARCHAR(50)[],
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by UUID REFERENCES users(id)
);

-- Default feature flags
INSERT INTO feature_flags (name, description, is_enabled) VALUES
    ('advanced_ocr', 'Enable advanced OCR features', false),
    ('workflow_automation', 'Enable workflow automation', true),
    ('ml_training', 'Enable ML model training', false),
    ('api_v2', 'Enable API v2 endpoints', false);

-- ----------------------------------------------------------------------------
-- SCHEDULED_TASKS - Cron jobs
-- ----------------------------------------------------------------------------

CREATE TYPE task_frequency AS ENUM (
    'minutely',
    'hourly',
    'daily',
    'weekly',
    'monthly',
    'custom'
);

CREATE TABLE scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Task definition
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    
    -- Schedule
    frequency task_frequency NOT NULL,
    cron_expression VARCHAR(100), -- For 'custom' frequency
    
    -- Execution
    task_type VARCHAR(100) NOT NULL, -- 'cleanup', 'backup', 'sync', etc.
    task_config JSONB,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Execution history
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_run_success BOOLEAN,
    last_run_duration_ms INTEGER,
    next_run_at TIMESTAMP WITH TIME ZONE,
    
    -- Stats
    total_runs INTEGER DEFAULT 0,
    successful_runs INTEGER DEFAULT 0,
    failed_runs INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scheduled_tasks_next_run ON scheduled_tasks(next_run_at) 
    WHERE is_active = TRUE;

-- Default tasks
INSERT INTO scheduled_tasks (name, description, frequency, task_type, task_config, is_active) VALUES
    ('cleanup_old_sessions', 'Remove expired sessions', 'daily', 'cleanup', 
     '{"target": "sessions", "older_than_days": 7}'::jsonb, true),
    
    ('update_supplier_stats', 'Update supplier statistics', 'daily', 'stats',
     '{"target": "suppliers"}'::jsonb, true),
    
    ('backup_database', 'Daily database backup', 'daily', 'backup',
     '{"retention_days": 30}'::jsonb, true),
    
    ('clean_temp_files', 'Remove temporary files', 'hourly', 'cleanup',
     '{"target": "temp_files", "older_than_hours": 24}'::jsonb, true);
```

---

## 🔗 BEZIEHUNGSDIAGRAMM (Simplified)
```
┌──────────────────────────────────────────────────────────────────┐
│                         USER LAYER                                │
│                                                                    │
│  users ──┬── user_roles ── roles ── role_permissions ── permissions
│          ├── api_keys                                             │
│          ├── sessions                                             │
│          └── notification_preferences                             │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DOCUMENT LAYER                               │
│                                                                    │
│  documents ──┬── document_pages                                  │
│              ├── document_versions                                │
│              ├── document_tags ── tags                            │
│              ├── document_relations                               │
│              ├── processing_jobs ──┬── job_events                │
│              │                      └── ocr_results               │
│              └── categories                                       │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SUPPLIER LAYER                                 │
│                                                                    │
│  suppliers ──┬── supplier_contacts                               │
│              ├── supplier_templates                               │
│              └── extraction_rules ── extraction_rule_versions    │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                   AUTOMATION LAYER                                │
│                                                                    │
│  workflows ──┬── workflow_steps                                  │
│              └── workflow_executions ── workflow_step_executions │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                 INTEGRATION LAYER                                 │
│                                                                    │
│  webhooks ── webhook_deliveries                                  │
│  integrations ── integration_logs                                 │
│  notifications                                                     │
│  email_queue ── email_templates                                  │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                   MONITORING LAYER                                │
│                                                                    │
│  backend_metrics                                                  │
│  system_metrics                                                   │
│  error_logs                                                       │
│  audit_logs                                                       │
└──────────────────────────────────────────────────────────────────┘