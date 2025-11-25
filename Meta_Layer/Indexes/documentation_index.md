# Documentation Index - Master Index aller Dokumentationen
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23
**Total Documents:** 130+
**Total Size:** ~3.5 MB

---

## 📑 Inhaltsverzeichnis

1. [Über diesen Index](#über-diesen-index)
2. [Dokumentation nach Layer](#dokumentation-nach-layer)
3. [Dokumentation nach Kategorie](#dokumentation-nach-kategorie)
4. [Dokumentation nach Thema](#dokumentation-nach-thema)
5. [Schnellzugriff nach Rolle](#schnellzugriff-nach-rolle)
6. [Dokumentations-Roadmap](#dokumentations-roadmap)
7. [Wartung dieses Index](#wartung-dieses-index)

---

## Über diesen Index

Dieser Master-Index organisiert **alle 130+ Dokumentationsdateien** des Ablage-Systems für schnellen Zugriff.

### Verwendung

**Nach Layer suchen:**
- [Meta_Layer](#meta_layer-knowledge-navigation) - Navigation & Übersicht
- [Static_Knowledge](#static_knowledge-permanent-assets) - Permanentes Wissen
- [Relations](#relations-connections--workflows) - Beziehungen & Workflows
- [Execution_Layer](#execution_layer-agents--automation) - Agents & Automation
- [Dynamic_Knowledge](#dynamic_knowledge-session-learning) - Session-basiertes Lernen

**Nach Kategorie suchen:**
- [Architecture](#architecture) | [API](#api) | [Infrastructure](#infrastructure) | [Security](#security) | [Testing](#testing)

**Nach Rolle suchen:**
- [Entwickler](#für-entwickler) | [DevOps](#für-devops) | [Architekten](#für-architekten) | [Security](#für-security-team)

### Legende

- 📄 Dokumentation
- 📋 Checkliste
- 🎯 Entscheidung (ADR)
- 📖 Guide/Tutorial
- 🔧 Runbook/SOP
- 🏗️ Architektur
- 📊 Analyse
- 🧪 Testing
- 🔒 Security
- 💾 Code

---

## Dokumentation nach Layer

### META_LAYER (Knowledge Navigation)

**Zweck:** Hilft beim Navigieren durch das Wissenssystem

#### Maps of Content (MOCs)
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📄 [MOC_Development.md](../MOC_Development.md) | Development workflows & tools | `#development` `#moc` |
| 📄 [MOC_Operations.md](../MOC_Operations.md) | Operational procedures | `#operations` `#moc` |
| 📄 [MOC_OCR.md](../MOC_OCR.md) | OCR processing workflows | `#ocr` `#moc` |
| 📄 [MOC_Security.md](../MOC_Security.md) | Security guidelines | `#security` `#moc` |
| 📄 [MOC_Performance.md](../MOC_Performance.md) | Performance optimization | `#performance` `#moc` |
| 📄 [MOC_Testing.md](../MOC_Testing.md) | Testing strategies | `#testing` `#moc` |

#### Architecture Overview
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 🏗️ [KNOWLEDGE_ARCHITECTURE.md](../KNOWLEDGE_ARCHITECTURE.md) | 5-layer system architecture | `#architecture` `#core` |
| 🏗️ [KNOWLEDGE_ARCHITECTURE_COMPLETE.md](../KNOWLEDGE_ARCHITECTURE_COMPLETE.md) | Complete architecture spec | `#architecture` `#reference` |
| 🏗️ [KNOWLEDGE_ARCHITECTURE_INDEX.md](../KNOWLEDGE_ARCHITECTURE_INDEX.md) | Architecture index | `#architecture` `#index` |

#### Quick References
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📄 [Quick_Reference_Guide.md](../Quick_Reference_Guide.md) | Command quick reference | `#quickref` `#commands` |
| 📄 [GETTING_STARTED.md](../../GETTING_STARTED.md) | Getting started guide | `#quickstart` `#onboarding` |
| 📄 [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md) | Current implementation status | `#status` `#progress` |

#### Knowledge Graph
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [Knowledge_Graph.md](../Knowledge_Graph.md) | Visual knowledge relationships | `#visualization` `#graph` |

---

### STATIC_KNOWLEDGE (Permanent Assets)

**Zweck:** Wiederverwendbares, permanentes Wissen

#### Architecture Documentation
| Datei | Beschreibung | Größe | Tags |
|-------|--------------|-------|------|
| 🏗️ [agents_skills_hooks_guide.md](../../Static_Knowledge/Architecture/agents_skills_hooks_guide.md) | Agent system architecture | ~1,800 lines | `#agents` `#architecture` |
| 🏗️ [agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md) | Implementation patterns | ~1,500 lines | `#patterns` `#implementation` |
| 🏗️ [skill_catalog.md](../../Static_Knowledge/Architecture/skill_catalog.md) | Complete skill catalog | ~1,200 lines | `#skills` `#catalog` |
| 🏗️ [hook_registry_system.md](../../Static_Knowledge/Architecture/hook_registry_system.md) | Hook system | ~1,800 lines | `#hooks` `#registry` |
| 🏗️ [agent_testing_guide.md](../../Static_Knowledge/Architecture/agent_testing_guide.md) | Testing strategies | ~1,600 lines | `#testing` `#agents` |
| 🏗️ [agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md) | Deployment guide | ~1,400 lines | `#deployment` `#operations` |
| 🏗️ [advanced_agent_patterns.md](../../Static_Knowledge/Architecture/advanced_agent_patterns.md) | Advanced patterns | ~1,300 lines | `#patterns` `#advanced` |
| 🏗️ [multi_tenant_architecture.md](../../Static_Knowledge/Architecture/multi_tenant_architecture.md) | Multi-tenant design | - | `#architecture` `#multitenant` |

#### API Documentation
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📖 [api_overview.md](../../Static_Knowledge/API/api_overview.md) | API structure | `#api` `#overview` |
| 📖 [api_endpoints.md](../../Static_Knowledge/API/api_endpoints.md) | Endpoint documentation | `#api` `#endpoints` |
| 📖 [api_client_examples.md](../../Static_Knowledge/API/api_client_examples.md) | Client usage examples | `#api` `#examples` |
| 📖 [api_versioning_strategy.md](../../Static_Knowledge/API/api_versioning_strategy.md) | Versioning approach | `#api` `#versioning` |

#### Infrastructure Documentation
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📖 [docker_setup.md](../../Static_Knowledge/Infrastructure/docker_setup.md) | Docker configuration | `#docker` `#infrastructure` |
| 📖 [terraform_infrastructure.md](../../Static_Knowledge/Infrastructure/terraform_infrastructure.md) | IaC with Terraform | `#terraform` `#iac` |
| 📖 [ansible_configuration.md](../../Static_Knowledge/Infrastructure/ansible_configuration.md) | Ansible automation | `#ansible` `#automation` |
| 📖 [ci_cd_pipeline.md](../../Static_Knowledge/Infrastructure/ci_cd_pipeline.md) | CI/CD setup | `#cicd` `#automation` |
| 📖 [database_optimization.md](../../Static_Knowledge/Infrastructure/database_optimization.md) | DB performance | `#database` `#optimization` |

#### Security Documentation
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 🔒 [security_hardening.md](../../Static_Knowledge/Security/security_hardening.md) | Security measures | `#security` `#hardening` |
| 🔒 [rate_limiting.md](../../Static_Knowledge/Security/rate_limiting.md) | API rate limiting | `#security` `#api` |
| 🔒 [gdpr_compliance.md](../../Static_Knowledge/Security/gdpr_compliance.md) | GDPR compliance | `#security` `#gdpr` |

#### Monitoring & Operations
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [prometheus_monitoring.md](../../Static_Knowledge/Monitoring/prometheus_monitoring.md) | Prometheus setup | `#monitoring` `#prometheus` |
| 📊 [grafana_dashboards.md](../../Static_Knowledge/Monitoring/grafana_dashboards.md) | Grafana dashboards | `#monitoring` `#grafana` |
| 📊 [loki_logging.md](../../Static_Knowledge/Monitoring/loki_logging.md) | Loki log aggregation | `#monitoring` `#logging` |
| 🔧 [operations_runbook.md](../../Static_Knowledge/Operations/operations_runbook.md) | Operations procedures | `#operations` `#runbook` |

#### Performance
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [performance_optimization.md](../../Static_Knowledge/Performance/performance_optimization.md) | Optimization guide | `#performance` `#optimization` |
| 📊 [performance_benchmarking.md](../../Static_Knowledge/Performance/performance_benchmarking.md) | Benchmarking | `#performance` `#benchmarking` |

#### Frontend
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📖 [frontend_architecture.md](../../Static_Knowledge/Frontend/frontend_architecture.md) | Frontend structure | `#frontend` `#architecture` |
| 📖 [display_modes.md](../../Static_Knowledge/Frontend/display_modes.md) | 4 display modes | `#frontend` `#ui` |

#### Development
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📖 [development_setup.md](../../Static_Knowledge/Development/development_setup.md) | Dev environment | `#development` `#setup` |
| 🧪 [testing_strategy.md](../../Static_Knowledge/Testing/testing_strategy.md) | Test approach | `#testing` `#strategy` |

#### Architecture Decision Records (ADRs)
| Datei | Beschreibung | Datum | Tags |
|-------|--------------|-------|------|
| 🎯 [adr_001_backend_selection.md](../../Static_Knowledge/ADRs/adr_001_backend_selection.md) | OCR backend strategy | - | `#adr` `#ocr` |
| 🎯 [adr_002_gpu_fallback.md](../../Static_Knowledge/ADRs/adr_002_gpu_fallback.md) | GPU fallback mechanism | - | `#adr` `#gpu` |
| 🎯 [adr_003_german_text_norm.md](../../Static_Knowledge/ADRs/adr_003_german_text_norm.md) | German text normalization | - | `#adr` `#german` |
| 🎯 [adr_004_template_extraction.md](../../Static_Knowledge/ADRs/adr_004_template_extraction.md) | Template extraction | - | `#adr` `#extraction` |
| 🎯 [adr_005_api_versioning.md](../../Static_Knowledge/ADRs/adr_005_api_versioning.md) | API versioning | - | `#adr` `#api` |
| 🎯 [adr_006_ocr_backend_selection.md](../../Static_Knowledge/ADRs/adr_006_ocr_backend_selection.md) | OCR selection logic | - | `#adr` `#ocr` |
| 🎯 [adr_007_german_nlp.md](../../Static_Knowledge/ADRs/adr_007_german_nlp.md) | German NLP approach | - | `#adr` `#nlp` |

#### Standard Operating Procedures (SOPs)
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 🔧 [sop_001_install_ocr_backends.md](../../Static_Knowledge/SOPs/sop_001_install_ocr_backends.md) | Installing OCR backends | `#sop` `#ocr` |
| 🔧 [sop_002_handle_gpu_oom.md](../../Static_Knowledge/SOPs/sop_002_handle_gpu_oom.md) | GPU OOM handling | `#sop` `#gpu` |
| 🔧 [sop_003_add_document_template.md](../../Static_Knowledge/SOPs/sop_003_add_document_template.md) | Adding templates | `#sop` `#templates` |
| 🔧 [sop_004_security_incident.md](../../Static_Knowledge/SOPs/sop_004_security_incident.md) | Security incidents | `#sop` `#security` |
| 🔧 [sop_005_database_backup.md](../../Static_Knowledge/SOPs/sop_005_database_backup.md) | Database backup | `#sop` `#database` |

#### Skills (YAML + Documentation)
| Skill | YAML Config | Documentation | Tags |
|-------|-------------|---------------|------|
| GPU Management | [gpu_management_skill.yaml](../../Static_Knowledge/Skills/gpu_management_skill.yaml) | In skill_catalog.md | `#skill` `#gpu` |
| German Text Processing | [german_text_processing_skill.yaml](../../Static_Knowledge/Skills/german_text_processing_skill.yaml) | In skill_catalog.md | `#skill` `#german` |
| Backend Selection | [backend_selection_skill.yaml](../../Static_Knowledge/Skills/backend_selection_skill.yaml) | In skill_catalog.md | `#skill` `#ocr` |
| Image Preprocessing | [image_preprocessing_skill.yaml](../../Static_Knowledge/Skills/image_preprocessing_skill.yaml) | - | `#skill` `#image` |
| Template Extraction | [template_extraction_skill.yaml](../../Static_Knowledge/Skills/template_extraction_skill.yaml) | In skill_catalog.md | `#skill` `#extraction` |
| Error Recovery | [error_recovery_skill.yaml](../../Static_Knowledge/Skills/error_recovery_skill.yaml) | - | `#skill` `#errors` |
| Monitoring & Observability | [monitoring_observability_skill.yaml](../../Static_Knowledge/Skills/monitoring_observability_skill.yaml) | - | `#skill` `#monitoring` |
| Backup & DR | [backup_disaster_recovery_skill.yaml](../../Static_Knowledge/Skills/backup_disaster_recovery_skill.yaml) | - | `#skill` `#backup` |
| Performance Tuning | [performance_tuning_skill.yaml](../../Static_Knowledge/Skills/performance_tuning_skill.yaml) | - | `#skill` `#performance` |
| Error Handling | [error_handling_skill.yaml](../../Static_Knowledge/Skills/error_handling_skill.yaml) | - | `#skill` `#errors` |

#### Reference Materials
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 💾 [code_snippets_fastapi.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_fastapi.md) | FastAPI patterns | `#code` `#fastapi` |
| 💾 [code_snippets_gpu.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gpu.md) | GPU patterns | `#code` `#gpu` |
| 💾 [code_snippets_german.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_german.md) | German text patterns | `#code` `#german` |
| 💾 [code_snippets_gdpr.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gdpr.md) | GDPR patterns | `#code` `#gdpr` |
| 💾 [code_snippets_redis.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_redis.md) | Redis patterns | `#code` `#redis` |
| 📄 [template_invoice.yaml](../../Static_Knowledge/References/Templates/template_invoice.yaml) | Invoice template | `#template` `#invoice` |
| 📄 [template_delivery_note.yaml](../../Static_Knowledge/References/Templates/template_delivery_note.yaml) | Delivery note template | `#template` `#delivery` |
| 📄 [template_contract.yaml](../../Static_Knowledge/References/Templates/template_contract.yaml) | Contract template | `#template` `#contract` |
| 📄 [glossary_business.md](../../Static_Knowledge/References/Glossaries/glossary_business.md) | Business terms (DE) | `#glossary` `#business` |
| 📄 [glossary_technical.md](../../Static_Knowledge/References/Glossaries/glossary_technical.md) | Technical terms | `#glossary` `#technical` |

#### AI Prompts
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📄 [prompt_template_code_review.yaml](../../Static_Knowledge/References/Prompts/prompt_template_code_review.yaml) | Code review prompt | `#prompt` `#review` |
| 📄 [prompt_template_debugging.yaml](../../Static_Knowledge/References/Prompts/prompt_template_debugging.yaml) | Debugging prompt | `#prompt` `#debugging` |
| 📄 [prompt_template_optimization.yaml](../../Static_Knowledge/References/Prompts/prompt_template_optimization.yaml) | Optimization prompt | `#prompt` `#optimization` |

---

### RELATIONS (Connections & Workflows)

**Zweck:** Definiert Beziehungen zwischen Komponenten

#### Workflows
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📋 [workflow_document_processing.yaml](../../Relations/Workflows/workflow_document_processing.yaml) | End-to-end processing | `#workflow` `#ocr` |
| 📋 [workflow_ci_cd.yaml](../../Relations/Workflows/workflow_ci_cd.yaml) | CI/CD pipeline | `#workflow` `#cicd` |
| 📋 [workflow_ocr_backend_selection.yaml](../../Relations/Workflows/workflow_ocr_backend_selection.yaml) | Backend routing | `#workflow` `#ocr` |
| 📋 [workflow_user_onboarding.yaml](../../Relations/Workflows/workflow_user_onboarding.yaml) | User onboarding | `#workflow` `#users` |

#### Playbooks
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📖 [playbook_error_response.md](../../Relations/Playbooks/playbook_error_response.md) | Error handling | `#playbook` `#errors` |
| 📖 [playbook_database_performance.md](../../Relations/Playbooks/playbook_database_performance.md) | DB performance | `#playbook` `#database` |
| 📖 [playbook_api_debugging.md](../../Relations/Playbooks/playbook_api_debugging.md) | API troubleshooting | `#playbook` `#api` |

#### Decision Trees
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 🌳 [decision_tree_backend_selection.yaml](../../Relations/Decision_Trees/decision_tree_backend_selection.yaml) | OCR backend choice | `#decision` `#ocr` |
| 🌳 [decision_tree_error_handling.yaml](../../Relations/Decision_Trees/decision_tree_error_handling.yaml) | Error classification | `#decision` `#errors` |
| 🌳 [decision_tree_security_incident.yaml](../../Relations/Decision_Trees/decision_tree_security_incident.yaml) | Security response | `#decision` `#security` |
| 🌳 [decision_tree_cache_invalidation.yaml](../../Relations/Decision_Trees/decision_tree_cache_invalidation.yaml) | Cache refresh | `#decision` `#cache` |
| 🌳 [decision_tree_gpu_allocation.yaml](../../Relations/Decision_Trees/decision_tree_gpu_allocation.yaml) | GPU resource allocation | `#decision` `#gpu` |
| 🌳 [decision_tree_ocr_backend.yaml](../../Relations/Decision_Trees/decision_tree_ocr_backend.yaml) | OCR routing (alt) | `#decision` `#ocr` |
| 🌳 [decision_tree_error_recovery.yaml](../../Relations/Decision_Trees/decision_tree_error_recovery.yaml) | Error recovery | `#decision` `#errors` |

#### Dependencies
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [dependencies_services.yaml](../../Relations/Dependencies/dependencies_services.yaml) | Service dependencies | `#dependencies` `#services` |
| 📊 [dependencies_models.yaml](../../Relations/Dependencies/dependencies_models.yaml) | Model dependencies | `#dependencies` `#models` |
| 📊 [dependencies_infrastructure.yaml](../../Relations/Dependencies/dependencies_infrastructure.yaml) | Infrastructure deps | `#dependencies` `#infrastructure` |

#### Hooks
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 🔗 [hooks_post_ocr.yaml](../../Relations/Hooks/hooks_post_ocr.yaml) | Post-OCR actions | `#hooks` `#ocr` |
| 🔗 [hooks_deployment.yaml](../../Relations/Hooks/hooks_deployment.yaml) | Deployment hooks | `#hooks` `#deployment` |
| 🔗 [hooks_document_processing.yaml](../../Relations/Hooks/hooks_document_processing.yaml) | Processing hooks | `#hooks` `#processing` |
| 🔗 [hooks_system_health.yaml](../../Relations/Hooks/hooks_system_health.yaml) | Health check hooks | `#hooks` `#health` |

---

### EXECUTION_LAYER (Agents & Automation)

**Zweck:** Autonome Agents die Aktionen ausführen

#### Main Agents (Python)
| Datei | Status | Beschreibung | Tags |
|-------|--------|--------------|------|
| 💾 [ocr_processing_agent.py](../../Execution_Layer/Agents/ocr_processing_agent.py) | Skeleton | End-to-end OCR | `#agent` `#ocr` |
| 💾 [template_extraction_agent.py](../../Execution_Layer/Agents/template_extraction_agent.py) | Skeleton | Data extraction | `#agent` `#extraction` |
| 💾 [quality_assurance_agent.py](../../Execution_Layer/Agents/quality_assurance_agent.py) | Skeleton | QA validation | `#agent` `#qa` |
| 💾 [document_classifier_agent.py](../../Execution_Layer/Agents/document_classifier_agent.py) | Skeleton | Classification | `#agent` `#classification` |
| 💾 [monitoring_agent.py](../../Execution_Layer/Agents/monitoring_agent.py) | Skeleton | System monitoring | `#agent` `#monitoring` |

#### Sub-Agents (Python)
| Datei | Status | Beschreibung | Tags |
|-------|--------|--------------|------|
| 💾 [ocr_backend_agent.py](../../Execution_Layer/Sub_Agents/ocr_backend_agent.py) | Skeleton | Backend selection | `#subagent` `#ocr` |
| 💾 [validation_sub_agent.py](../../Execution_Layer/Sub_Agents/validation_sub_agent.py) | Skeleton | Result validation | `#subagent` `#validation` |
| 💾 [storage_sub_agent.py](../../Execution_Layer/Sub_Agents/storage_sub_agent.py) | Skeleton | Storage management | `#subagent` `#storage` |
| 💾 [invoice_data_extractor.py](../../Execution_Layer/Sub_Agents/invoice_data_extractor.py) | Skeleton | Invoice extraction | `#subagent` `#invoice` |
| 💾 [german_entity_extractor.py](../../Execution_Layer/Sub_Agents/german_entity_extractor.py) | Skeleton | German NER | `#subagent` `#german` |

#### Validators (Python)
| Datei | Status | Beschreibung | Tags |
|-------|--------|--------------|------|
| 💾 [ocr_quality_validator.py](../../Execution_Layer/Validators/ocr_quality_validator.py) | Skeleton | OCR quality checks | `#validator` `#ocr` |
| 💾 [compliance_validator.py](../../Execution_Layer/Validators/compliance_validator.py) | Skeleton | GDPR compliance | `#validator` `#gdpr` |
| 💾 [german_text_validator.py](../../Execution_Layer/Validators/german_text_validator.py) | Skeleton | German validation | `#validator` `#german` |
| 💾 [document_upload_validator.py](../../Execution_Layer/Validators/document_upload_validator.py) | Skeleton | Upload validation | `#validator` `#upload` |
| 💾 [api_request_validator.py](../../Execution_Layer/Validators/api_request_validator.py) | Skeleton | API validation | `#validator` `#api` |
| 💾 [backup_validator.py](../../Execution_Layer/Validators/backup_validator.py) | Skeleton | Backup integrity | `#validator` `#backup` |
| 💾 [gdpr_compliance_checker.py](../../Execution_Layer/Validators/gdpr_compliance_checker.py) | Skeleton | GDPR checks | `#validator` `#gdpr` |

#### Operational Documentation
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📋 [daily_operations_checklist.md](../../Execution_Layer/Operations/daily_operations_checklist.md) | Daily tasks | `#operations` `#daily` |
| 🌳 [gpu_troubleshooting_decision_tree.md](../../Execution_Layer/Operations/gpu_troubleshooting_decision_tree.md) | GPU troubleshooting | `#operations` `#gpu` |
| 🔧 [performance_degradation_runbook.md](../../Execution_Layer/Operations/performance_degradation_runbook.md) | Performance issues | `#runbook` `#performance` |
| 🔧 [security_incident_runbook.md](../../Execution_Layer/Operations/security_incident_runbook.md) | Security incidents | `#runbook` `#security` |
| 📋 [weekly_maintenance_runbook.md](../../Execution_Layer/Operations/weekly_maintenance_runbook.md) | Weekly maintenance | `#runbook` `#maintenance` |
| 📋 [monthly_health_audit_runbook.md](../../Execution_Layer/Operations/monthly_health_audit_runbook.md) | Monthly audit | `#runbook` `#audit` |
| 📋 [pre_deployment_checklist.md](../../Execution_Layer/Operations/pre_deployment_checklist.md) | Pre-deploy checks | `#checklist` `#deployment` |
| 📋 [post_deployment_checklist.md](../../Execution_Layer/Operations/post_deployment_checklist.md) | Post-deploy checks | `#checklist` `#deployment` |
| 📖 [developer_onboarding_curriculum.md](../../Execution_Layer/Operations/developer_onboarding_curriculum.md) | Developer onboarding | `#onboarding` `#training` |

---

### DYNAMIC_KNOWLEDGE (Session Learning)

**Zweck:** Lernen und Kontext aus aktuellen Sessions

#### Learnings
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [learning_gpu_oom_insights.md](../../Dynamic_Knowledge/Learnings/learning_gpu_oom_insights.md) | GPU OOM lessons | `#learning` `#gpu` |
| 📊 [learning_german_ocr_challenges.md](../../Dynamic_Knowledge/Learnings/learning_german_ocr_challenges.md) | German OCR insights | `#learning` `#german` |
| 📊 [learning_deployment_gotchas.md](../../Dynamic_Knowledge/Learnings/learning_deployment_gotchas.md) | Deployment surprises | `#learning` `#deployment` |
| 📊 [learning_redis_performance.md](../../Dynamic_Knowledge/Learnings/learning_redis_performance.md) | Redis optimization | `#learning` `#redis` |
| 📊 [learning_api_design.md](../../Dynamic_Knowledge/Learnings/learning_api_design.md) | API design lessons | `#learning` `#api` |
| 📊 [learning_celery_optimization.md](../../Dynamic_Knowledge/Learnings/learning_celery_optimization.md) | Celery optimization | `#learning` `#celery` |

#### Experiments
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📊 [experiment_ocr_backend_comparison.md](../../Dynamic_Knowledge/Experiments/experiment_ocr_backend_comparison.md) | Backend performance | `#experiment` `#ocr` |

#### Logs
| Datei | Beschreibung | Format | Tags |
|-------|--------------|--------|------|
| 📊 [implementation_log.jsonl](../../Dynamic_Knowledge/Logs/implementation_log.jsonl) | Implementation history | JSONL | `#log` `#history` |
| 📊 [error_log.jsonl](../../Dynamic_Knowledge/Logs/error_log.jsonl) | Structured errors | JSONL | `#log` `#errors` |
| 📊 [performance_log.jsonl](../../Dynamic_Knowledge/Logs/performance_log.jsonl) | Performance metrics | JSONL | `#log` `#performance` |
| 📊 [celery_worker_crash_log.jsonl](../../Dynamic_Knowledge/Logs/celery_worker_crash_log.jsonl) | Worker crashes | JSONL | `#log` `#celery` |
| 📊 [gdpr_compliance_audit_log.jsonl](../../Dynamic_Knowledge/Logs/gdpr_compliance_audit_log.jsonl) | GDPR audit trail | JSONL | `#log` `#gdpr` |

#### Context & Bookmarks
| Datei | Beschreibung | Tags |
|-------|--------------|------|
| 📄 [current_session_context.md](../../Dynamic_Knowledge/Context/current_session_context.md) | Current session | `#context` `#session` |
| 📄 [code_hotspots.md](../../Dynamic_Knowledge/Bookmarks/code_hotspots.md) | Critical code locations | `#bookmark` `#code` |
| 📄 [external_resources.md](../../Dynamic_Knowledge/Bookmarks/external_resources.md) | External references | `#bookmark` `#external` |

---

## Dokumentation nach Kategorie

### Architecture
- [agents_skills_hooks_guide.md](../../Static_Knowledge/Architecture/agents_skills_hooks_guide.md)
- [agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md)
- [skill_catalog.md](../../Static_Knowledge/Architecture/skill_catalog.md)
- [hook_registry_system.md](../../Static_Knowledge/Architecture/hook_registry_system.md)
- [multi_tenant_architecture.md](../../Static_Knowledge/Architecture/multi_tenant_architecture.md)
- [KNOWLEDGE_ARCHITECTURE.md](../KNOWLEDGE_ARCHITECTURE.md)
- [frontend_architecture.md](../../Static_Knowledge/Frontend/frontend_architecture.md)

### API
- [api_overview.md](../../Static_Knowledge/API/api_overview.md)
- [api_endpoints.md](../../Static_Knowledge/API/api_endpoints.md)
- [api_client_examples.md](../../Static_Knowledge/API/api_client_examples.md)
- [api_versioning_strategy.md](../../Static_Knowledge/API/api_versioning_strategy.md)

### Infrastructure
- [docker_setup.md](../../Static_Knowledge/Infrastructure/docker_setup.md)
- [terraform_infrastructure.md](../../Static_Knowledge/Infrastructure/terraform_infrastructure.md)
- [ansible_configuration.md](../../Static_Knowledge/Infrastructure/ansible_configuration.md)
- [ci_cd_pipeline.md](../../Static_Knowledge/Infrastructure/ci_cd_pipeline.md)
- [database_optimization.md](../../Static_Knowledge/Infrastructure/database_optimization.md)

### Security
- [security_hardening.md](../../Static_Knowledge/Security/security_hardening.md)
- [rate_limiting.md](../../Static_Knowledge/Security/rate_limiting.md)
- [gdpr_compliance.md](../../Static_Knowledge/Security/gdpr_compliance.md)
- [MOC_Security.md](../MOC_Security.md)

### Testing
- [agent_testing_guide.md](../../Static_Knowledge/Architecture/agent_testing_guide.md)
- [testing_strategy.md](../../Static_Knowledge/Testing/testing_strategy.md)
- [MOC_Testing.md](../MOC_Testing.md)

### Performance
- [performance_optimization.md](../../Static_Knowledge/Performance/performance_optimization.md)
- [performance_benchmarking.md](../../Static_Knowledge/Performance/performance_benchmarking.md)
- [MOC_Performance.md](../MOC_Performance.md)

### Operations
- [operations_runbook.md](../../Static_Knowledge/Operations/operations_runbook.md)
- [agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md)
- [MOC_Operations.md](../MOC_Operations.md)

### Monitoring
- [prometheus_monitoring.md](../../Static_Knowledge/Monitoring/prometheus_monitoring.md)
- [grafana_dashboards.md](../../Static_Knowledge/Monitoring/grafana_dashboards.md)
- [loki_logging.md](../../Static_Knowledge/Monitoring/loki_logging.md)

---

## Dokumentation nach Thema

### GPU Management
- [gpu_management_skill.yaml](../../Static_Knowledge/Skills/gpu_management_skill.yaml)
- [adr_002_gpu_fallback.md](../../Static_Knowledge/ADRs/adr_002_gpu_fallback.md)
- [sop_002_handle_gpu_oom.md](../../Static_Knowledge/SOPs/sop_002_handle_gpu_oom.md)
- [learning_gpu_oom_insights.md](../../Dynamic_Knowledge/Learnings/learning_gpu_oom_insights.md)
- [code_snippets_gpu.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gpu.md)
- [gpu_troubleshooting_decision_tree.md](../../Execution_Layer/Operations/gpu_troubleshooting_decision_tree.md)
- [decision_tree_gpu_allocation.yaml](../../Relations/Decision_Trees/decision_tree_gpu_allocation.yaml)

### OCR Processing
- [MOC_OCR.md](../MOC_OCR.md)
- [backend_selection_skill.yaml](../../Static_Knowledge/Skills/backend_selection_skill.yaml)
- [adr_001_backend_selection.md](../../Static_Knowledge/ADRs/adr_001_backend_selection.md)
- [adr_006_ocr_backend_selection.md](../../Static_Knowledge/ADRs/adr_006_ocr_backend_selection.md)
- [sop_001_install_ocr_backends.md](../../Static_Knowledge/SOPs/sop_001_install_ocr_backends.md)
- [workflow_ocr_backend_selection.yaml](../../Relations/Workflows/workflow_ocr_backend_selection.yaml)
- [decision_tree_backend_selection.yaml](../../Relations/Decision_Trees/decision_tree_backend_selection.yaml)
- [ocr_processing_agent.py](../../Execution_Layer/Agents/ocr_processing_agent.py)
- [experiment_ocr_backend_comparison.md](../../Dynamic_Knowledge/Experiments/experiment_ocr_backend_comparison.md)

### German Language Processing
- [german_text_processing_skill.yaml](../../Static_Knowledge/Skills/german_text_processing_skill.yaml)
- [adr_003_german_text_norm.md](../../Static_Knowledge/ADRs/adr_003_german_text_norm.md)
- [adr_007_german_nlp.md](../../Static_Knowledge/ADRs/adr_007_german_nlp.md)
- [code_snippets_german.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_german.md)
- [german_text_validator.py](../../Execution_Layer/Validators/german_text_validator.py)
- [german_entity_extractor.py](../../Execution_Layer/Sub_Agents/german_entity_extractor.py)
- [learning_german_ocr_challenges.md](../../Dynamic_Knowledge/Learnings/learning_german_ocr_challenges.md)

### Agents & Automation
- [agents_skills_hooks_guide.md](../../Static_Knowledge/Architecture/agents_skills_hooks_guide.md)
- [agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md)
- [agent_testing_guide.md](../../Static_Knowledge/Architecture/agent_testing_guide.md)
- [agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md)
- [advanced_agent_patterns.md](../../Static_Knowledge/Architecture/advanced_agent_patterns.md)
- All files in [Execution_Layer/Agents/](../../Execution_Layer/Agents/)

### Skills System
- [skill_catalog.md](../../Static_Knowledge/Architecture/skill_catalog.md)
- All files in [Static_Knowledge/Skills/](../../Static_Knowledge/Skills/)

### Hooks System
- [hook_registry_system.md](../../Static_Knowledge/Architecture/hook_registry_system.md)
- All files in [Relations/Hooks/](../../Relations/Hooks/)

### GDPR & Security
- [gdpr_compliance.md](../../Static_Knowledge/Security/gdpr_compliance.md)
- [code_snippets_gdpr.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gdpr.md)
- [compliance_validator.py](../../Execution_Layer/Validators/compliance_validator.py)
- [gdpr_compliance_checker.py](../../Execution_Layer/Validators/gdpr_compliance_checker.py)
- [gdpr_compliance_audit_log.jsonl](../../Dynamic_Knowledge/Logs/gdpr_compliance_audit_log.jsonl)

---

## Schnellzugriff nach Rolle

### Für Entwickler

**Setup & Onboarding:**
- [GETTING_STARTED.md](../../GETTING_STARTED.md)
- [development_setup.md](../../Static_Knowledge/Development/development_setup.md)
- [developer_onboarding_curriculum.md](../../Execution_Layer/Operations/developer_onboarding_curriculum.md)
- [Quick_Reference_Guide.md](../Quick_Reference_Guide.md)

**Architecture:**
- [KNOWLEDGE_ARCHITECTURE.md](../KNOWLEDGE_ARCHITECTURE.md)
- [agents_skills_hooks_guide.md](../../Static_Knowledge/Architecture/agents_skills_hooks_guide.md)
- [agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md)

**API Development:**
- [api_overview.md](../../Static_Knowledge/API/api_overview.md)
- [api_endpoints.md](../../Static_Knowledge/API/api_endpoints.md)
- [api_client_examples.md](../../Static_Knowledge/API/api_client_examples.md)
- [code_snippets_fastapi.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_fastapi.md)

**Testing:**
- [agent_testing_guide.md](../../Static_Knowledge/Architecture/agent_testing_guide.md)
- [testing_strategy.md](../../Static_Knowledge/Testing/testing_strategy.md)

**Code Reference:**
- [code_snippets_fastapi.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_fastapi.md)
- [code_snippets_gpu.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gpu.md)
- [code_snippets_german.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_german.md)
- [code_snippets_redis.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_redis.md)

### Für DevOps

**Deployment:**
- [agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md)
- [docker_setup.md](../../Static_Knowledge/Infrastructure/docker_setup.md)
- [terraform_infrastructure.md](../../Static_Knowledge/Infrastructure/terraform_infrastructure.md)
- [ansible_configuration.md](../../Static_Knowledge/Infrastructure/ansible_configuration.md)
- [ci_cd_pipeline.md](../../Static_Knowledge/Infrastructure/ci_cd_pipeline.md)

**Operations:**
- [operations_runbook.md](../../Static_Knowledge/Operations/operations_runbook.md)
- [daily_operations_checklist.md](../../Execution_Layer/Operations/daily_operations_checklist.md)
- [weekly_maintenance_runbook.md](../../Execution_Layer/Operations/weekly_maintenance_runbook.md)
- [monthly_health_audit_runbook.md](../../Execution_Layer/Operations/monthly_health_audit_runbook.md)

**Monitoring:**
- [prometheus_monitoring.md](../../Static_Knowledge/Monitoring/prometheus_monitoring.md)
- [grafana_dashboards.md](../../Static_Knowledge/Monitoring/grafana_dashboards.md)
- [loki_logging.md](../../Static_Knowledge/Monitoring/loki_logging.md)

**Troubleshooting:**
- [gpu_troubleshooting_decision_tree.md](../../Execution_Layer/Operations/gpu_troubleshooting_decision_tree.md)
- [performance_degradation_runbook.md](../../Execution_Layer/Operations/performance_degradation_runbook.md)
- [playbook_error_response.md](../../Relations/Playbooks/playbook_error_response.md)
- [playbook_database_performance.md](../../Relations/Playbooks/playbook_database_performance.md)

**Checklists:**
- [pre_deployment_checklist.md](../../Execution_Layer/Operations/pre_deployment_checklist.md)
- [post_deployment_checklist.md](../../Execution_Layer/Operations/post_deployment_checklist.md)

### Für Architekten

**Architecture Overview:**
- [KNOWLEDGE_ARCHITECTURE.md](../KNOWLEDGE_ARCHITECTURE.md)
- [KNOWLEDGE_ARCHITECTURE_COMPLETE.md](../KNOWLEDGE_ARCHITECTURE_COMPLETE.md)
- [Knowledge_Graph.md](../Knowledge_Graph.md)

**Architecture Documentation:**
- [agents_skills_hooks_guide.md](../../Static_Knowledge/Architecture/agents_skills_hooks_guide.md)
- [multi_tenant_architecture.md](../../Static_Knowledge/Architecture/multi_tenant_architecture.md)
- [frontend_architecture.md](../../Static_Knowledge/Frontend/frontend_architecture.md)

**Decision Records:**
- All [ADRs](../../Static_Knowledge/ADRs/)

**Advanced Patterns:**
- [advanced_agent_patterns.md](../../Static_Knowledge/Architecture/advanced_agent_patterns.md)
- [agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md)

### Für Security Team

**Security Guidelines:**
- [MOC_Security.md](../MOC_Security.md)
- [security_hardening.md](../../Static_Knowledge/Security/security_hardening.md)
- [rate_limiting.md](../../Static_Knowledge/Security/rate_limiting.md)
- [gdpr_compliance.md](../../Static_Knowledge/Security/gdpr_compliance.md)

**Incident Response:**
- [sop_004_security_incident.md](../../Static_Knowledge/SOPs/sop_004_security_incident.md)
- [security_incident_runbook.md](../../Execution_Layer/Operations/security_incident_runbook.md)
- [decision_tree_security_incident.yaml](../../Relations/Decision_Trees/decision_tree_security_incident.yaml)

**Code Reference:**
- [code_snippets_gdpr.md](../../Static_Knowledge/References/Code_Snippets/code_snippets_gdpr.md)

---

## Dokumentations-Roadmap

### Phase 1: Foundation ✅ (Complete)
- ✅ Core architecture documentation
- ✅ API documentation
- ✅ Infrastructure guides
- ✅ Security guidelines
- ✅ 7 ADRs (Architecture Decision Records)
- ✅ 5 SOPs (Standard Operating Procedures)

### Phase 2: Agents & Automation ✅ (Complete)
- ✅ Agents/Skills/Hooks architecture
- ✅ Agent implementation patterns
- ✅ Skill catalog
- ✅ Hook registry system
- ✅ Testing guide
- ✅ Deployment operations
- ✅ Advanced patterns

### Phase 3: Operations & Monitoring ✅ (Complete)
- ✅ Operations runbooks
- ✅ Monitoring setup (Prometheus, Grafana, Loki)
- ✅ Performance optimization
- ✅ Troubleshooting guides
- ✅ Checklists (daily, weekly, monthly)

### Phase 4: Polish & Optimization 🚧 (In Progress)
- ✅ Documentation index (this file)
- ⏳ Code index
- ⏳ Tag system
- ⏳ Troubleshooting guides (GPU, OCR quality, deployment)
- ⏳ Implementation guides

### Phase 5: Enhancement 📅 (Planned)
- Component integration map
- Async patterns guide
- Code review checklist
- End-to-end examples
- FAQ

---

## Wartung dieses Index

### Aktualisierungsregeln

1. **Neue Dokumente** müssen hier registriert werden
2. **Update-Frequenz:** Nach jedem neuen Dokument
3. **Verantwortlichkeit:** Dokumentations-Team
4. **Review-Zyklus:** Monatlich

### Konventionen

**Dateinamen:**
- Lowercase mit underscores: `my_document.md`
- Versionierung in Dateinamen vermeiden
- Präfixe für Typ: `adr_`, `sop_`, `playbook_`, etc.

**Tags:**
- Lowercase
- Mit `#` Präfix
- Max 5 Tags pro Dokument
- Konsistent über Dokumente hinweg

**Links:**
- Relative Pfade verwenden
- Von diesem Dokument zum Ziel
- Bei Umstrukturierung aktualisieren

### Statistiken

**Aktueller Stand:**
- Total Dokumente: 130+
- Markdown Files: 130
- YAML Files: 62
- Python Files: 50
- Gesamtgröße: ~3.5 MB
- Letzte Aktualisierung: 2025-01-23

---

**Version:** 1.0
**Letzte Aktualisierung:** 2025-01-23
**Nächste Review:** 2025-02-23
**Maintainer:** Documentation Team
