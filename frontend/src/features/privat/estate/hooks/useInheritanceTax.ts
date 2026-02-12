/**
 * Inheritance Tax Hook
 *
 * Berechnet Erbschaftsteuer-Szenarien nach deutschem Recht
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import {
  estatePlanningService,
  type InheritanceTaxCalculation,
  type InheritanceTaxScenario,
  type UsufructCalculation,
  type RelationshipType,
} from '@/lib/api/services/estate-planning';
import { estateQueryKeys } from './useEstateOverview';

// ==================== Constants ====================

/**
 * Deutsche Erbschaftsteuer-Freibeträge (Stand 2024)
 * Alle 10 Jahre erneuerbar
 */
export const TAX_ALLOWANCES: Record<RelationshipType, number> = {
  ehepartner: 500000,
  lebenspartner: 500000,
  kind: 400000,
  stiefkind: 400000,
  enkelkind: 200000, // wenn Eltern verstorben
  enkelkind_eltern_leben: 100000,
  elternteil: 100000, // nur bei Erbschaft
  geschwister: 20000,
  neffe_nichte: 20000,
  sonstige_verwandte: 20000,
  nicht_verwandt: 20000,
};

/**
 * Versorgungsfreibeträge (nur bei Erbschaft, nicht Schenkung)
 */
export const CARE_ALLOWANCES = {
  ehepartner: 256000,
  kind_0_5: 52000,
  kind_5_10: 41000,
  kind_10_15: 30700,
  kind_15_20: 20500,
  kind_20_27: 10300,
};

/**
 * Steuerklassen-Zuordnung
 */
export const TAX_CLASS_MAPPING: Record<RelationshipType, 'I' | 'II' | 'III'> = {
  ehepartner: 'I',
  lebenspartner: 'I',
  kind: 'I',
  stiefkind: 'I',
  enkelkind: 'I',
  enkelkind_eltern_leben: 'I',
  elternteil: 'I',
  geschwister: 'II',
  neffe_nichte: 'II',
  sonstige_verwandte: 'II',
  nicht_verwandt: 'III',
};

/**
 * Steuersätze nach Klasse und Betrag
 */
export const TAX_RATES: Array<{
  upTo: number;
  classI: number;
  classII: number;
  classIII: number;
}> = [
  { upTo: 75000, classI: 7, classII: 15, classIII: 30 },
  { upTo: 300000, classI: 11, classII: 20, classIII: 30 },
  { upTo: 600000, classI: 15, classII: 25, classIII: 30 },
  { upTo: 6000000, classI: 19, classII: 30, classIII: 30 },
  { upTo: 13000000, classI: 23, classII: 35, classIII: 50 },
  { upTo: 26000000, classI: 27, classII: 40, classIII: 50 },
  { upTo: Infinity, classI: 30, classII: 43, classIII: 50 },
];

/**
 * Relationship Display Names (German)
 */
export const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  ehepartner: 'Ehepartner/in',
  lebenspartner: 'Lebenspartner/in',
  kind: 'Kind',
  stiefkind: 'Stiefkind',
  enkelkind: 'Enkelkind (Eltern verstorben)',
  enkelkind_eltern_leben: 'Enkelkind (Eltern leben)',
  elternteil: 'Elternteil',
  geschwister: 'Geschwister',
  neffe_nichte: 'Neffe/Nichte',
  sonstige_verwandte: 'Sonstige Verwandte',
  nicht_verwandt: 'Nicht verwandt',
};

// ==================== Hooks ====================

/**
 * Berechnet Erbschaftsteuer für alle Begünstigten
 */
export function useInheritanceTax(
  spaceId: string,
  options?: {
    isInheritance?: boolean;
  } & Omit<UseQueryOptions<InheritanceTaxCalculation>, 'queryKey' | 'queryFn'>
) {
  const { isInheritance, ...queryOptions } = options ?? {};

  return useQuery({
    queryKey: [...estateQueryKeys.taxCalculation(spaceId), isInheritance],
    queryFn: () => estatePlanningService.calculateInheritanceTax(spaceId, { isInheritance }),
    enabled: !!spaceId,
    staleTime: 2 * 60 * 1000, // 2 Minuten
    ...queryOptions,
  });
}

/**
 * Simuliert Steuer für einen einzelnen Erben
 */
export function useSimulateTax() {
  return useMutation({
    mutationFn: ({
      spaceId,
      relationship,
      amount,
      birthDate,
      isInheritance,
    }: {
      spaceId: string;
      relationship: RelationshipType;
      amount: number;
      birthDate?: string;
      isInheritance?: boolean;
    }) =>
      estatePlanningService.simulateTaxForHeir(spaceId, {
        relationship,
        amount,
        birthDate,
        isInheritance,
      }),
  });
}

/**
 * Berechnet Niessbrauch-Wert
 */
export function useCalculateUsufruct() {
  return useMutation({
    mutationFn: (params: {
      assetValue: number;
      annualYieldRate: number;
      beneficiaryAge: number;
      relationship: RelationshipType;
      gender?: 'm' | 'f';
    }) => estatePlanningService.calculateUsufruct(params),
  });
}

// ==================== Utility Functions ====================

/**
 * Berechnet den Steuersatz lokal (für schnelle UI-Updates)
 */
export function calculateTaxRateLocal(
  taxableAmount: number,
  taxClass: 'I' | 'II' | 'III'
): number {
  for (const bracket of TAX_RATES) {
    if (taxableAmount <= bracket.upTo) {
      switch (taxClass) {
        case 'I':
          return bracket.classI;
        case 'II':
          return bracket.classII;
        case 'III':
          return bracket.classIII;
      }
    }
  }
  return TAX_RATES[TAX_RATES.length - 1][`class${taxClass}` as keyof typeof TAX_RATES[0]] as number;
}

/**
 * Berechnet die Steuer lokal (für schnelle UI-Updates)
 */
export function calculateTaxLocal(
  grossAmount: number,
  relationship: RelationshipType,
  isInheritance: boolean = true,
  beneficiaryAge?: number
): {
  personalAllowance: number;
  careAllowance: number;
  taxableAmount: number;
  taxRate: number;
  taxAmount: number;
  effectiveRate: number;
} {
  const personalAllowance = TAX_ALLOWANCES[relationship];

  // Versorgungsfreibetrag nur bei Erbschaft
  let careAllowance = 0;
  if (isInheritance) {
    if (relationship === 'ehepartner' || relationship === 'lebenspartner') {
      careAllowance = CARE_ALLOWANCES.ehepartner;
    } else if ((relationship === 'kind' || relationship === 'stiefkind') && beneficiaryAge !== undefined) {
      if (beneficiaryAge < 5) careAllowance = CARE_ALLOWANCES.kind_0_5;
      else if (beneficiaryAge < 10) careAllowance = CARE_ALLOWANCES.kind_5_10;
      else if (beneficiaryAge < 15) careAllowance = CARE_ALLOWANCES.kind_10_15;
      else if (beneficiaryAge < 20) careAllowance = CARE_ALLOWANCES.kind_15_20;
      else if (beneficiaryAge < 27) careAllowance = CARE_ALLOWANCES.kind_20_27;
    }
  }

  const totalAllowance = personalAllowance + careAllowance;
  const taxableAmount = Math.max(0, grossAmount - totalAllowance);
  const taxClass = TAX_CLASS_MAPPING[relationship];
  const taxRate = calculateTaxRateLocal(taxableAmount, taxClass);
  const taxAmount = (taxableAmount * taxRate) / 100;
  const effectiveRate = grossAmount > 0 ? (taxAmount / grossAmount) * 100 : 0;

  return {
    personalAllowance,
    careAllowance,
    taxableAmount,
    taxRate,
    taxAmount,
    effectiveRate,
  };
}
