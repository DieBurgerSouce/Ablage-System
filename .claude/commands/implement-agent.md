# Implement Agent Command

Generate a complete agent implementation from skeleton.

**Instructions:**
1. Ask user which agent to implement (or detect from current file)
2. Read the agent skeleton file
3. Check [agent_implementation_patterns.md](../Static_Knowledge/Architecture/agent_implementation_patterns.md) for pattern
4. Check [agent_implementation_roadmap.md](../Static_Knowledge/Implementation_Guides/agent_implementation_roadmap.md) for requirements
5. Generate complete implementation with:
   - Full BaseAgent inheritance
   - Async process_task method
   - GPU resource management (if applicable)
   - Error handling with retries
   - Metrics & logging
   - Comprehensive docstrings
6. Generate corresponding test file with:
   - Unit tests for all methods
   - Integration tests for workflows
   - GPU tests (if applicable)
   - >80% coverage
7. Update code_index.md status: ⚪ Skeleton → ✅ Implemented

**Quality Checks:**
- [ ] Type hints on all functions
- [ ] Async/await properly used
- [ ] Error handling comprehensive
- [ ] Tests pass
- [ ] Coverage >80%
- [ ] Docstrings complete
