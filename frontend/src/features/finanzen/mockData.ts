// Finanzen-Modul: Mock-Daten für Jahr-Ordner und Kategorien

import type { FinanceYear, FinanceDocumentCategory, FinanceAggregations, FinancePackageType } from './types';

/**
 * Mock-Daten für Finanz-Jahre
 */
export const MOCK_FINANCE_YEARS: FinanceYear[] = [
  {
    id: '2024',
    year: 2024,
    isActive: true,
    lastDocumentDate: '2024-12-20',
    documentCounts: {
      grundabgabenbescheid: 1,
      steuerbescheide: 4,
      vorauszahlungen: 8,
      steuererklärungen: 2,
      finanzamt_korrespondenz: 5,
      lohn_gehalt: 24,
      sozialversicherung: 12,
      berufsgenossenschaft: 2,
      arbeitsverträge: 3,
      betriebshaftpflicht: 1,
      sachversicherungen: 2,
      kfz_versicherung: 1,
      rechtsschutz: 1,
      kontoauszüge: 48,
      kreditverträge: 2,
      buergschaften: 0,
      darlehen: 1,
    },
    totalDocuments: 117,
    totalNachzahlung: 12500.00,
    totalErstattung: 3200.00,
    pendingDeadlines: 3,
  },
  {
    id: '2023',
    year: 2023,
    isActive: false,
    lastDocumentDate: '2023-12-31',
    documentCounts: {
      grundabgabenbescheid: 1,
      steuerbescheide: 6,
      vorauszahlungen: 8,
      steuererklärungen: 4,
      finanzamt_korrespondenz: 8,
      lohn_gehalt: 24,
      sozialversicherung: 12,
      berufsgenossenschaft: 2,
      arbeitsverträge: 2,
      betriebshaftpflicht: 1,
      sachversicherungen: 2,
      kfz_versicherung: 1,
      rechtsschutz: 1,
      kontoauszüge: 52,
      kreditverträge: 1,
      buergschaften: 1,
      darlehen: 1,
    },
    totalDocuments: 127,
    totalNachzahlung: 8900.00,
    totalErstattung: 4500.00,
    pendingDeadlines: 0,
  },
  {
    id: '2022',
    year: 2022,
    isActive: false,
    lastDocumentDate: '2022-12-31',
    documentCounts: {
      grundabgabenbescheid: 1,
      steuerbescheide: 5,
      vorauszahlungen: 8,
      steuererklärungen: 4,
      finanzamt_korrespondenz: 6,
      lohn_gehalt: 24,
      sozialversicherung: 12,
      berufsgenossenschaft: 2,
      arbeitsverträge: 1,
      betriebshaftpflicht: 1,
      sachversicherungen: 2,
      kfz_versicherung: 1,
      rechtsschutz: 1,
      kontoauszüge: 48,
      kreditverträge: 1,
      buergschaften: 0,
      darlehen: 1,
    },
    totalDocuments: 118,
    totalNachzahlung: 6200.00,
    totalErstattung: 2100.00,
    pendingDeadlines: 0,
  },
  {
    id: '2021',
    year: 2021,
    isActive: false,
    lastDocumentDate: '2021-12-31',
    documentCounts: {
      grundabgabenbescheid: 1,
      steuerbescheide: 4,
      vorauszahlungen: 8,
      steuererklärungen: 4,
      finanzamt_korrespondenz: 4,
      lohn_gehalt: 24,
      sozialversicherung: 12,
      berufsgenossenschaft: 2,
      arbeitsverträge: 0,
      betriebshaftpflicht: 1,
      sachversicherungen: 2,
      kfz_versicherung: 1,
      rechtsschutz: 1,
      kontoauszüge: 48,
      kreditverträge: 0,
      buergschaften: 0,
      darlehen: 1,
    },
    totalDocuments: 113,
    totalNachzahlung: 5100.00,
    totalErstattung: 1800.00,
    pendingDeadlines: 0,
  },
];

// ==================== HELPER FUNCTIONS ====================

/**
 * Gibt alle Finanz-Jahre zurück (sortiert nach Jahr absteigend)
 */
export function getAllFinanceYears(): FinanceYear[] {
  return [...MOCK_FINANCE_YEARS].sort((a, b) => b.year - a.year);
}

/**
 * Findet ein Finanz-Jahr anhand der ID
 */
export function getFinanceYearById(yearId: string): FinanceYear | undefined {
  return MOCK_FINANCE_YEARS.find(y => y.id === yearId);
}

/**
 * Gibt die Gesamtzahl der Dokumente eines Jahres zurück
 */
export function getFinanceYearTotalDocuments(year: FinanceYear): number {
  return year.totalDocuments;
}

/**
 * Gibt die Anzahl offener Fristen eines Jahres zurück
 */
export function getFinanceYearPendingDeadlines(year: FinanceYear): number {
  return year.pendingDeadlines;
}

/**
 * Berechnet den Saldo (Erstattung - Nachzahlung) eines Jahres
 */
export function getFinanceYearSaldo(year: FinanceYear): number {
  return year.totalErstattung - year.totalNachzahlung;
}

/**
 * Gibt die Dokumentanzahl für eine Kategorie in einem Jahr zurück
 */
export function getFinanceYearCategoryCount(
  year: FinanceYear,
  category: FinanceDocumentCategory
): number {
  return year.documentCounts[category] || 0;
}

/**
 * Berechnet Aggregationen über alle Jahre
 */
export function getFinanceOverallAggregations(): FinanceAggregations {
  const years = getAllFinanceYears();

  let totalDocuments = 0;
  let totalNachzahlung = 0;
  let totalErstattung = 0;
  let pendingDeadlines = 0;

  const documentsByPackage: Record<FinancePackageType, number> = {
    steuern: 0,
    personal: 0,
    versicherung: 0,
    bank: 0,
  };

  // Kategorien nach Paket
  const steuerCategories: FinanceDocumentCategory[] = [
    'grundabgabenbescheid',
    'steuerbescheide',
    'vorauszahlungen',
    'steuererklärungen',
    'finanzamt_korrespondenz',
  ];
  const personalCategories: FinanceDocumentCategory[] = [
    'lohn_gehalt',
    'sozialversicherung',
    'berufsgenossenschaft',
    'arbeitsverträge',
  ];
  const versicherungCategories: FinanceDocumentCategory[] = [
    'betriebshaftpflicht',
    'sachversicherungen',
    'kfz_versicherung',
    'rechtsschutz',
  ];
  const bankCategories: FinanceDocumentCategory[] = [
    'kontoauszüge',
    'kreditverträge',
    'buergschaften',
    'darlehen',
  ];

  for (const year of years) {
    totalDocuments += year.totalDocuments;
    totalNachzahlung += year.totalNachzahlung;
    totalErstattung += year.totalErstattung;
    pendingDeadlines += year.pendingDeadlines;

    // Pakete summieren
    for (const cat of steuerCategories) {
      documentsByPackage.steuern += year.documentCounts[cat] || 0;
    }
    for (const cat of personalCategories) {
      documentsByPackage.personal += year.documentCounts[cat] || 0;
    }
    for (const cat of versicherungCategories) {
      documentsByPackage.versicherung += year.documentCounts[cat] || 0;
    }
    for (const cat of bankCategories) {
      documentsByPackage.bank += year.documentCounts[cat] || 0;
    }
  }

  return {
    totalDocuments,
    totalNachzahlung,
    totalErstattung,
    saldo: totalErstattung - totalNachzahlung,
    pendingDeadlines,
    documentsByPackage,
  };
}

/**
 * Berechnet Aggregationen für ein einzelnes Jahr
 */
export function getFinanceYearAggregations(year: FinanceYear): FinanceAggregations {
  const documentsByPackage: Record<FinancePackageType, number> = {
    steuern: 0,
    personal: 0,
    versicherung: 0,
    bank: 0,
  };

  // Kategorien nach Paket
  const steuerCategories: FinanceDocumentCategory[] = [
    'grundabgabenbescheid',
    'steuerbescheide',
    'vorauszahlungen',
    'steuererklärungen',
    'finanzamt_korrespondenz',
  ];
  const personalCategories: FinanceDocumentCategory[] = [
    'lohn_gehalt',
    'sozialversicherung',
    'berufsgenossenschaft',
    'arbeitsverträge',
  ];
  const versicherungCategories: FinanceDocumentCategory[] = [
    'betriebshaftpflicht',
    'sachversicherungen',
    'kfz_versicherung',
    'rechtsschutz',
  ];
  const bankCategories: FinanceDocumentCategory[] = [
    'kontoauszüge',
    'kreditverträge',
    'buergschaften',
    'darlehen',
  ];

  for (const cat of steuerCategories) {
    documentsByPackage.steuern += year.documentCounts[cat] || 0;
  }
  for (const cat of personalCategories) {
    documentsByPackage.personal += year.documentCounts[cat] || 0;
  }
  for (const cat of versicherungCategories) {
    documentsByPackage.versicherung += year.documentCounts[cat] || 0;
  }
  for (const cat of bankCategories) {
    documentsByPackage.bank += year.documentCounts[cat] || 0;
  }

  return {
    totalDocuments: year.totalDocuments,
    totalNachzahlung: year.totalNachzahlung,
    totalErstattung: year.totalErstattung,
    saldo: year.totalErstattung - year.totalNachzahlung,
    pendingDeadlines: year.pendingDeadlines,
    documentsByPackage,
  };
}

/**
 * Formatiert einen Geldbetrag für die Anzeige
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

/**
 * Formatiert einen Saldo mit Vorzeichen
 */
export function formatSaldo(saldo: number): string {
  const formatted = formatCurrency(Math.abs(saldo));
  if (saldo > 0) {
    return `+${formatted}`;
  } else if (saldo < 0) {
    return `-${formatted}`;
  }
  return formatted;
}

/**
 * Formatiert ein Datum für die Anzeige
 */
export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}
