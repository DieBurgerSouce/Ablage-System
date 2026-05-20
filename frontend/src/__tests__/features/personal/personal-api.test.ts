import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { listEmployees } from '@/features/personal/api/personal-api';

describe('personal-api - Auth Token Enforcement', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('apiRequest sollte ohne Token mit "Nicht authentifiziert" throwen', async () => {
    await expect(listEmployees()).rejects.toThrow('Nicht authentifiziert');
  });

  it('apiRequest sollte mit Whitespace-Token throwen', async () => {
    sessionStorage.setItem('auth_token', '   ');
    await expect(listEmployees()).rejects.toThrow('Nicht authentifiziert');
  });
});
