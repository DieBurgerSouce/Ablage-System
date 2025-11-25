# Find Documentation Command

Quickly find relevant documentation.

**Instructions:**
1. Ask user what they're looking for (or infer from context)
2. Search in multiple indexes:
   - [documentation_index.md](../Meta_Layer/Indexes/documentation_index.md) - All docs
   - [code_index.md](../Meta_Layer/Indexes/code_index.md) - All code files
   - [tag_system.md](../Meta_Layer/Tags/tag_system.md) - Tag-based search
3. Use grep for tag-based search:
   ```bash
   grep "#gpu" Meta_Layer/Indexes/documentation_index.md
   grep "#ocr" Meta_Layer/Indexes/*.md
   ```
4. Present results with direct links
5. Suggest related documentation

**Common Queries:**
- "GPU problems" → [gpu_troubleshooting_guide.md](../Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md)
- "OCR quality" → [ocr_quality_troubleshooting.md](../Execution_Layer/Troubleshooting/ocr_quality_troubleshooting.md)
- "Agent implementation" → [agent_implementation_patterns.md](../Static_Knowledge/Architecture/agent_implementation_patterns.md)
- "Deployment" → [agent_deployment_operations.md](../Static_Knowledge/Architecture/agent_deployment_operations.md)
- "Testing" → [agent_testing_guide.md](../Static_Knowledge/Architecture/agent_testing_guide.md)
- "Async patterns" → [async_patterns.md](../Static_Knowledge/Patterns/async_patterns.md)
- "Code review" → [code_review_checklist.md](../Static_Knowledge/Checklists/code_review_checklist.md)
- "System architecture" → [component_integration_map.md](../Relations/Integration_Maps/component_integration_map.md)
- "Implementation plan" → [agent_implementation_roadmap.md](../Static_Knowledge/Implementation_Guides/agent_implementation_roadmap.md)

**Tag Examples:**
```bash
# Find all GPU-related docs
grep "#gpu" Meta_Layer/Indexes/documentation_index.md

# Find all developer-targeted docs
grep "#developer" Meta_Layer/Indexes/documentation_index.md

# Find all critical files
grep "#critical" Meta_Layer/Indexes/code_index.md
```
