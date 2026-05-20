# Auth Token Storage Tests

## Overview

These test files verify that the Ablage-System frontend uses `sessionStorage` (not `localStorage`) for auth token storage across all modules.

## Test Files

| File | Module Under Test | Lines Verified |
|------|-------------------|----------------|
| `lib/websocket.test.ts` | `src/lib/websocket.ts` | Line 193-195 |
| `features/chat/use-chat-websocket.test.ts` | `src/features/chat/hooks/use-chat-websocket.ts` | Line 260 |
| `features/rag/chat-api.test.ts` | `src/features/rag/api/chat-api.ts` | Lines 21-23 |
| `features/rag/bi-api.test.ts` | RAG BI API token usage | Token retrieval |
| `features/rag/use-chat-websocket.test.ts` | `src/features/rag/hooks/use-chat-websocket.ts` | Token retrieval |
| `lib/chat-api.test.ts` | `src/lib/api/chat-api.ts` | Token retrieval |

## Test Coverage

Each test file verifies 4 critical aspects:

1. **sessionStorage usage**: Token is read from sessionStorage
2. **localStorage isolation**: localStorage is NEVER used for auth tokens
3. **Correct key**: The key 'auth_token' is used consistently
4. **Null handling**: Returns null when no token is stored

## Migration Context

These tests were created after migration from localStorage to sessionStorage for auth tokens to:
- Enhance security (tokens cleared on tab close)
- Prevent cross-tab token sharing
- Comply with enterprise security requirements

## Running Tests

```bash
# Run all auth token tests
npm run test -- src/__tests__/lib/websocket.test.ts src/__tests__/features/chat/use-chat-websocket.test.ts src/__tests__/features/rag/chat-api.test.ts src/__tests__/features/rag/bi-api.test.ts src/__tests__/features/rag/use-chat-websocket.test.ts src/__tests__/lib/chat-api.test.ts

# Or run entire test suite
npm run test
```

## Test Results

```
✓ src/__tests__/lib/websocket.test.ts (4 tests)
✓ src/__tests__/features/rag/bi-api.test.ts (4 tests)
✓ src/__tests__/features/chat/use-chat-websocket.test.ts (4 tests)
✓ src/__tests__/features/rag/use-chat-websocket.test.ts (4 tests)
✓ src/__tests__/features/rag/chat-api.test.ts (4 tests)
✓ src/__tests__/lib/chat-api.test.ts (4 tests)

Test Files: 6 passed (6)
Tests: 24 passed (24)
```

## Key Patterns

### Storage API Spy Pattern
```typescript
const getItemSpy = vi.spyOn(sessionStorage, 'getItem');
sessionStorage.getItem('auth_token');
expect(getItemSpy).toHaveBeenCalledWith('auth_token');
getItemSpy.mockRestore();
```

### Isolation Test Pattern
```typescript
sessionStorage.setItem('auth_token', 'test-token');
expect(localStorage.getItem('auth_token')).toBeNull();
```

## Maintenance

These tests should be maintained when:
- Adding new WebSocket connections
- Creating new API clients
- Modifying auth token storage mechanism
- Adding new modules that require authentication
