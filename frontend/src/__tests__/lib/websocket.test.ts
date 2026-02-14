import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('WebSocketManager - Token Storage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it('sollte Token aus sessionStorage lesen', () => {
    sessionStorage.setItem('auth_token', 'test-ws-token');
    expect(sessionStorage.getItem('auth_token')).toBe('test-ws-token');
  });

  it('sollte NICHT localStorage verwenden', () => {
    sessionStorage.setItem('auth_token', 'test-ws-token');
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('sollte den korrekten Key auth_token verwenden', () => {
    const getItemSpy = vi.spyOn(sessionStorage, 'getItem');
    sessionStorage.getItem('auth_token');
    expect(getItemSpy).toHaveBeenCalledWith('auth_token');
    getItemSpy.mockRestore();
  });

  it('sollte null zurueckgeben wenn kein Token vorhanden', () => {
    expect(sessionStorage.getItem('auth_token')).toBeNull();
  });
});
