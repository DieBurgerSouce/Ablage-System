/**
 * Persona-Credentials fuer den Perception-Audit — Single Source of Truth.
 * Muss mit scripts/seed_perception.py uebereinstimmen. Alles synthetisch,
 * niemals echte Accounts verwenden.
 */
export interface Persona {
  key: 'p1' | 'p2' | 'p3' | 'p4';
  label: string;
  email: string;
  password: string;
}

export const PERSONAS: Record<Persona['key'], Persona> = {
  p1: { key: 'p1', label: 'Azubi', email: 'azubi@localhost.com', password: 'azubi123' },
  p2: { key: 'p2', label: 'Prokurist', email: 'prokurist@localhost.com', password: 'prokurist123' },
  p3: { key: 'p3', label: 'Steuerberaterin', email: 'pruefer@localhost.com', password: 'pruefer123' },
  p4: { key: 'p4', label: 'Familienmitglied', email: 'familie@localhost.com', password: 'familie123' },
};

export const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';
