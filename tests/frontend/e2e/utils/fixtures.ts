/**
 * Test Data Fixtures for E2E Tests
 *
 * Provides reusable test data generators and constants.
 */

import { v4 as uuidv4 } from 'uuid';

// ============================================================================
// Document Fixtures
// ============================================================================

export interface TestDocument {
  id: string;
  title: string;
  documentType: string;
  filename: string;
  mimeType: string;
}

export function generateTestDocument(
  overrides: Partial<TestDocument> = {}
): TestDocument {
  const id = uuidv4();
  return {
    id,
    title: `Test-Dokument ${id.slice(0, 8)}`,
    documentType: 'invoice',
    filename: `test_${id.slice(0, 8)}.pdf`,
    mimeType: 'application/pdf',
    ...overrides,
  };
}

export const DOCUMENT_TYPES = {
  invoice: 'Rechnung',
  contract: 'Vertrag',
  deliveryNote: 'Lieferschein',
  quote: 'Angebot',
  other: 'Sonstiges',
} as const;

// ============================================================================
// Entity Fixtures
// ============================================================================

export interface TestEntity {
  id: string;
  name: string;
  type: 'customer' | 'supplier';
  email: string;
  customerNumber?: string;
  supplierNumber?: string;
}

export function generateTestCustomer(
  overrides: Partial<TestEntity> = {}
): TestEntity {
  const id = uuidv4();
  return {
    id,
    name: `Test Kunde ${id.slice(0, 8)}`,
    type: 'customer',
    email: `kunde_${id.slice(0, 8)}@test.local`,
    customerNumber: `K-${Math.floor(Math.random() * 100000)}`,
    ...overrides,
  };
}

export function generateTestSupplier(
  overrides: Partial<TestEntity> = {}
): TestEntity {
  const id = uuidv4();
  return {
    id,
    name: `Test Lieferant ${id.slice(0, 8)}`,
    type: 'supplier',
    email: `lieferant_${id.slice(0, 8)}@test.local`,
    supplierNumber: `L-${Math.floor(Math.random() * 100000)}`,
    ...overrides,
  };
}

// ============================================================================
// Contract Fixtures
// ============================================================================

export interface TestContract {
  id: string;
  title: string;
  contractNumber: string;
  status: 'active' | 'expired' | 'draft';
  startDate: string;
  endDate: string;
  value: number;
}

export function generateTestContract(
  overrides: Partial<TestContract> = {}
): TestContract {
  const id = uuidv4();
  const startDate = new Date();
  const endDate = new Date();
  endDate.setFullYear(endDate.getFullYear() + 1);

  return {
    id,
    title: `Test Vertrag ${id.slice(0, 8)}`,
    contractNumber: `V-${Math.floor(Math.random() * 100000)}`,
    status: 'active',
    startDate: startDate.toISOString().split('T')[0],
    endDate: endDate.toISOString().split('T')[0],
    value: Math.floor(Math.random() * 100000) + 1000,
    ...overrides,
  };
}

// ============================================================================
// Notification Fixtures
// ============================================================================

export const NOTIFICATION_CHANNELS = [
  { key: 'email', label: 'E-Mail', gdprRequired: false },
  { key: 'slack', label: 'Slack', gdprRequired: false },
  { key: 'teams', label: 'Microsoft Teams', gdprRequired: false },
  { key: 'sms', label: 'SMS', gdprRequired: true },
  { key: 'push', label: 'Push-Benachrichtigung', gdprRequired: false },
] as const;

export const NOTIFICATION_SEVERITIES = [
  { key: 'info', label: 'Information' },
  { key: 'low', label: 'Niedrig' },
  { key: 'medium', label: 'Mittel' },
  { key: 'high', label: 'Hoch' },
  { key: 'critical', label: 'Kritisch' },
] as const;

// ============================================================================
// Alert Fixtures
// ============================================================================

export const ALERT_CATEGORIES = [
  { key: 'fraud', label: 'Betrug' },
  { key: 'risk', label: 'Risiko' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'deadline', label: 'Frist' },
  { key: 'system', label: 'System' },
  { key: 'security', label: 'Sicherheit' },
  { key: 'quality', label: 'Qualitaet' },
  { key: 'workflow', label: 'Workflow' },
] as const;

// ============================================================================
// Workflow Fixtures
// ============================================================================

export interface TestWorkflowVersion {
  id: string;
  version: string;
  status: 'draft' | 'active' | 'deprecated';
  changeType: 'major' | 'minor' | 'patch';
}

export function generateTestWorkflowVersion(
  overrides: Partial<TestWorkflowVersion> = {}
): TestWorkflowVersion {
  const id = uuidv4();
  return {
    id,
    version: '1.0.0',
    status: 'draft',
    changeType: 'minor',
    ...overrides,
  };
}

// ============================================================================
// File Generation Fixtures
// ============================================================================

/**
 * Create a minimal valid PDF buffer for testing
 */
export function createTestPdfBuffer(): Buffer {
  const pdfContent = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 120 >>
stream
BT
/F1 12 Tf
100 700 Td
(RECHNUNG Nr. 2024-0001) Tj
0 -20 Td
(Betrag: 1.234,56 EUR) Tj
ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000436 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
512
%%EOF`;
  return Buffer.from(pdfContent, 'utf-8');
}

/**
 * Create a minimal valid PNG buffer for testing
 */
export function createTestImageBuffer(): Buffer {
  // Minimal valid PNG (1x1 white pixel)
  const pngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
  return Buffer.from(pngBase64, 'base64');
}

// ============================================================================
// German Locale Data
// ============================================================================

export const GERMAN_MONTHS = [
  'Januar',
  'Februar',
  'Maerz',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
];

export const GERMAN_WEEKDAYS = [
  'Montag',
  'Dienstag',
  'Mittwoch',
  'Donnerstag',
  'Freitag',
  'Samstag',
  'Sonntag',
];

// ============================================================================
// Tax Fixtures (German)
// ============================================================================

export const TAX_CATEGORIES = {
  paragraph9: {
    key: '9',
    label: 'Werbungskosten (Paragraph 9 EStG)',
    examples: ['Arbeitsmittel', 'Fahrtkosten', 'Fortbildung'],
  },
  paragraph10: {
    key: '10',
    label: 'Sonderausgaben (Paragraph 10 EStG)',
    examples: ['Versicherungen', 'Altersvorsorge', 'Spenden'],
  },
  paragraph33: {
    key: '33',
    label: 'Aussergewoehnliche Belastungen (Paragraph 33 EStG)',
    examples: ['Krankheitskosten', 'Behinderung', 'Pflege'],
  },
  paragraph35a: {
    key: '35a',
    label: 'Haushaltsnahe Dienstleistungen (Paragraph 35a EStG)',
    examples: ['Handwerker', 'Haushaltshilfe', 'Gartenpflege'],
  },
} as const;

// ============================================================================
// Retirement Planning Fixtures
// ============================================================================

export const RETIREMENT_PLANS = {
  riester: {
    key: 'riester',
    label: 'Riester-Rente',
    maxContribution: 2100,
  },
  ruerup: {
    key: 'ruerup',
    label: 'Ruerup-Rente (Basisrente)',
    maxContribution: 26528,
  },
  betrieblich: {
    key: 'betrieblich',
    label: 'Betriebliche Altersvorsorge',
    maxContribution: 7008,
  },
} as const;

// ============================================================================
// Estate Planning Fixtures
// ============================================================================

export const INHERITANCE_TAX_CLASSES = {
  I: {
    label: 'Steuerklasse I',
    description: 'Ehepartner, Kinder, Enkel',
    rates: [7, 11, 15, 19, 23, 27, 30],
  },
  II: {
    label: 'Steuerklasse II',
    description: 'Eltern, Grosseltern, Geschwister',
    rates: [15, 20, 25, 30, 35, 40, 43],
  },
  III: {
    label: 'Steuerklasse III',
    description: 'Alle uebrigen',
    rates: [30, 30, 30, 30, 50, 50, 50],
  },
} as const;

export const TAX_ALLOWANCES = {
  spouse: { amount: 500000, label: 'Ehepartner' },
  child: { amount: 400000, label: 'Kinder' },
  grandchild: { amount: 200000, label: 'Enkel' },
  parent: { amount: 100000, label: 'Eltern (bei Erbschaft)' },
  sibling: { amount: 20000, label: 'Geschwister' },
  other: { amount: 20000, label: 'Sonstige' },
} as const;
