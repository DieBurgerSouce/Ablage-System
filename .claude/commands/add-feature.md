# Add New Feature Command

Structured workflow for implementing new features.

**Instructions:**
1. **Planning Phase:**
   - Read feature requirements from user
   - Check [component_integration_map.md](../Relations/Integration_Maps/component_integration_map.md) for integration points
   - Identify affected components
   - Create TODO list with TodoWrite

2. **Design Phase:**
   - Create interface/API design
   - Update architecture docs if needed
   - Get user approval on design

3. **Implementation Phase:**
   - Create feature branch: `git checkout -b feature/TICKET-123-description`
   - Implement following [async_patterns.md](../Static_Knowledge/Patterns/async_patterns.md)
   - Add comprehensive type hints
   - Follow [code_review_checklist.md](../Static_Knowledge/Checklists/code_review_checklist.md)

4. **Testing Phase:**
   - Write unit tests (>80% coverage)
   - Write integration tests
   - Run full test suite: `pytest --cov=app`
   - Fix any failing tests

5. **Documentation Phase:**
   - Add/update docstrings
   - Update CLAUDE.md if APIs changed
   - Update relevant guides

6. **Review Phase:**
   - Self-review using checklist
   - Create PR with descriptive title
   - Request review from 2 team members

**Quality Gates:**
- [ ] Tests pass with >80% coverage
- [ ] Ruff & mypy clean
- [ ] Documentation complete
- [ ] Self-reviewed with checklist
- [ ] No hardcoded secrets
- [ ] German language for user-facing content

**Example Workflow:**
```bash
# Start feature
git checkout -b feature/OCR-123-add-fraktur-support

# Implement
code app/ocr_backends/deepseek.py

# Test
pytest tests/ocr_backends/test_deepseek.py -v --cov

# Commit
git add .
git commit -m "feat(ocr): add Fraktur script support to DeepSeek backend"

# Push & PR
git push -u origin feature/OCR-123-add-fraktur-support
```
