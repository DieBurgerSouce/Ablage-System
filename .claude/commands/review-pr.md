# Review Pull Request Command

Perform comprehensive code review using project checklist.

**Instructions:**
1. Read changed files in current branch:
   ```bash
   git diff main --name-only
   git diff main
   ```
2. Use [code_review_checklist.md](../Static_Knowledge/Checklists/code_review_checklist.md)
3. Check EVERY applicable item:
   - Code Style & Standards
   - Testing (coverage, quality)
   - Security (auth, input validation, secrets)
   - Performance (queries, caching, async)
   - GPU-specific (if applicable)
   - German Language (user-facing content)
   - Error Handling
4. Run automated checks:
   ```bash
   ruff check .
   mypy app/
   pytest --cov=app --cov-report=term-missing
   ```
5. Provide structured feedback:
   - ✅ Approved items
   - 🔄 Changes requested (blocking)
   - 💡 Suggestions (non-blocking)
6. Generate review comment template

**Output Format:**
```markdown
## Code Review

### ✅ Approved
- Code style: Ruff clean
- Type hints: Complete
- Tests: 87% coverage

### 🔄 Changes Requested (Blocking)
1. Security: [ ] Line 42 - Hardcoded API key
2. Testing: [ ] Missing GPU memory test

### 💡 Suggestions (Non-Blocking)
- Consider caching in line 67
- Refactor function X for readability

**Verdict:** Changes Requested / Approved
```
