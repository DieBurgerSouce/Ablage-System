/**
 * Estate Planning API Service
 *
 * Nachlassplanung für das Privat-Modul:
 * - Erbschaftsteuer-Berechnung (deutsches Recht)
 * - Begünstigte/Erben-Verwaltung
 * - Vollmachten-Management
 * - Niessbrauch-Berechnung
 * - Zeitgesteuerter Dokumentenzugriff
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Class ====================

export class EstatePlanningApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'EstatePlanningApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new EstatePlanningApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new EstatePlanningApiError(`${context}: ${message}`, 400, error);
    }

    throw new EstatePlanningApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new EstatePlanningApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Types ====================

export type RelationshipType =
  | 'ehepartner'
  | 'lebenspartner'
  | 'kind'
  | 'stiefkind'
  | 'enkelkind'
  | 'enkelkind_eltern_leben'
  | 'elternteil'
  | 'geschwister'
  | 'neffe_nichte'
  | 'sonstige_verwandte'
  | 'nicht_verwandt';

export type TaxClass = 'klasse_i' | 'klasse_ii' | 'klasse_iii';

export type PowerOfAttorneyType =
  | 'vorsorgevollmacht'
  | 'generalvollmacht'
  | 'bankvollmacht'
  | 'patientenverfuegung'
  | 'betreuungsverfuegung'
  | 'sorgerechtsverfuegung';

export type DocumentAccessTrigger =
  | 'death'
  | 'incapacity'
  | 'date'
  | 'age'
  | 'manual';

export interface Beneficiary {
  id: string;
  name: string;
  relationship: RelationshipType;
  birthDate?: string;
  sharePercent: number;
  specificBequest?: number;
  taxClass: TaxClass;
  personalAllowance: number;
  careAllowance: number;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface BeneficiaryCreate {
  name: string;
  relationship: RelationshipType;
  birthDate?: string;
  sharePercent: number;
  specificBequest?: number;
  notes?: string;
}

export interface BeneficiaryUpdate {
  name?: string;
  relationship?: RelationshipType;
  birthDate?: string;
  sharePercent?: number;
  specificBequest?: number;
  notes?: string;
}

export interface PowerOfAttorney {
  id: string;
  poaType: PowerOfAttorneyType;
  title: string;
  grantedTo: string;
  grantedDate?: string;
  validFrom?: string;
  validUntil?: string;
  documentId?: string;
  isActive: boolean;
  scope?: string;
  notarized: boolean;
  lastReviewed?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PowerOfAttorneyCreate {
  poaType: PowerOfAttorneyType;
  title: string;
  grantedTo: string;
  grantedDate?: string;
  validFrom?: string;
  validUntil?: string;
  documentId?: string;
  scope?: string;
  notarized?: boolean;
}

export interface PowerOfAttorneyUpdate {
  title?: string;
  grantedTo?: string;
  grantedDate?: string;
  validFrom?: string;
  validUntil?: string;
  isActive?: boolean;
  scope?: string;
  notarized?: boolean;
  lastReviewed?: string;
}

export interface InheritanceTaxScenario {
  beneficiaryId: string;
  beneficiaryName: string;
  relationship: RelationshipType;
  taxClass: TaxClass;
  grossInheritance: number;
  taxableInheritance: number;
  personalAllowance: number;
  careAllowance: number;
  householdAllowance: number;
  otherDeductions: number;
  taxBase: number;
  taxRate: number;
  taxAmount: number;
  effectiveTaxRate: number;
}

export interface InheritanceTaxCalculation {
  spaceId: string;
  totalEstate: number;
  totalTax: number;
  averageEffectiveRate: number;
  scenarios: InheritanceTaxScenario[];
  calculatedAt: string;
}

export interface UsufructCalculation {
  assetValue: number;
  usufructValue: number;
  netGiftValue: number;
  personalAllowance: number;
  taxableAmount: number;
  taxAmount: number;
  taxRate: string;
  savingsVsDirectGift: number;
  recommendation: string;
}

export interface HeirDocumentAccess {
  id: string;
  heirName: string;
  heirEmail?: string;
  documents: string[];
  folders: string[];
  trigger: DocumentAccessTrigger;
  triggerDate?: string;
  triggerAge?: number;
  isActive: boolean;
  accessGranted: boolean;
  accessGrantedAt?: string;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface HeirDocumentAccessCreate {
  heirName: string;
  heirEmail?: string;
  documents: string[];
  folders: string[];
  trigger: DocumentAccessTrigger;
  triggerDate?: string;
  triggerAge?: number;
  notes?: string;
}

export interface TenYearGiftPlan {
  beneficiaryId: string;
  beneficiaryName: string;
  allowancePer10Years: number;
  currentGiftsInPeriod: number;
  remainingAllowance: number;
  periodStart: string;
  periodEnd: string;
  nextRenewalDate: string;
  recommendedGifts: Array<{
    amount: number;
    date: string;
    taxFree: boolean;
    estimatedTax: number;
    description: string;
  }>;
  totalTaxSavings: number;
}

export interface EstateSummary {
  spaceId: string;
  totalAssets: number;
  totalLiabilities: number;
  netEstate: number;
  realEstateValue: number;
  investmentValue: number;
  vehicleValue: number;
  otherAssets: number;
  mortgageDebt: number;
  otherDebt: number;
  beneficiaries: Beneficiary[];
  totalShares: number;
  taxScenarios: InheritanceTaxScenario[];
  totalEstimatedTax: number;
  activePowersOfAttorney: PowerOfAttorney[];
  missingEssentialPoas: string[];
  heirDocumentAccess: HeirDocumentAccess[];
  recommendations: string[];
  warnings: string[];
  calculatedAt: string;
}

export interface EstateOverview {
  summary: EstateSummary;
  taxCalculation: InheritanceTaxCalculation;
  giftPlans: TenYearGiftPlan[];
}

// ==================== Backend Types ====================

interface BeneficiaryBackend {
  id: string;
  name: string;
  relationship: RelationshipType;
  birth_date?: string;
  share_percent: number;
  specific_bequest?: number;
  tax_class: TaxClass;
  personal_allowance: number;
  care_allowance: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

interface PowerOfAttorneyBackend {
  id: string;
  poa_type: PowerOfAttorneyType;
  title: string;
  granted_to: string;
  granted_date?: string;
  valid_from?: string;
  valid_until?: string;
  document_id?: string;
  is_active: boolean;
  scope?: string;
  notarized: boolean;
  last_reviewed?: string;
  created_at: string;
  updated_at: string;
}

interface InheritanceTaxScenarioBackend {
  beneficiary_id: string;
  beneficiary_name: string;
  relationship: RelationshipType;
  tax_class: TaxClass;
  gross_inheritance: number;
  taxable_inheritance: number;
  personal_allowance: number;
  care_allowance: number;
  household_allowance: number;
  other_deductions: number;
  tax_base: number;
  tax_rate: number;
  tax_amount: number;
  effective_tax_rate: number;
}

interface InheritanceTaxCalculationBackend {
  space_id: string;
  total_estate: number;
  total_tax: number;
  average_effective_rate: number;
  scenarios: InheritanceTaxScenarioBackend[];
  calculated_at: string;
}

interface UsufructCalculationBackend {
  asset_value: string;
  usufruct_value: string;
  net_gift_value: string;
  personal_allowance: string;
  taxable_amount: string;
  tax_amount: string;
  tax_rate: string;
  savings_vs_direct_gift: string;
  recommendation: string;
}

interface HeirDocumentAccessBackend {
  id: string;
  heir_name: string;
  heir_email?: string;
  documents: string[];
  folders: string[];
  trigger: DocumentAccessTrigger;
  trigger_date?: string;
  trigger_age?: number;
  is_active: boolean;
  access_granted: boolean;
  access_granted_at?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

interface TenYearGiftPlanBackend {
  beneficiary_id: string;
  beneficiary_name: string;
  allowance_per_10_years: number;
  current_gifts_in_period: number;
  remaining_allowance: number;
  period_start: string;
  period_end: string;
  next_renewal_date: string;
  recommended_gifts: Array<{
    amount: number;
    date: string;
    tax_free: boolean;
    estimated_tax: number;
    description: string;
  }>;
  total_tax_savings: number;
}

interface EstateSummaryBackend {
  space_id: string;
  total_assets: number;
  total_liabilities: number;
  net_estate: number;
  real_estate_value: number;
  investment_value: number;
  vehicle_value: number;
  other_assets: number;
  mortgage_debt: number;
  other_debt: number;
  beneficiaries: BeneficiaryBackend[];
  total_shares: number;
  tax_scenarios: InheritanceTaxScenarioBackend[];
  total_estimated_tax: number;
  active_powers_of_attorney: PowerOfAttorneyBackend[];
  missing_essential_poas: string[];
  heir_document_access: HeirDocumentAccessBackend[];
  recommendations: string[];
  warnings: string[];
  calculated_at: string;
}

// ==================== Transformers ====================

function transformBeneficiary(data: BeneficiaryBackend): Beneficiary {
  return {
    id: data.id,
    name: data.name,
    relationship: data.relationship,
    birthDate: data.birth_date,
    sharePercent: data.share_percent,
    specificBequest: data.specific_bequest,
    taxClass: data.tax_class,
    personalAllowance: data.personal_allowance,
    careAllowance: data.care_allowance,
    notes: data.notes,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

function transformPowerOfAttorney(data: PowerOfAttorneyBackend): PowerOfAttorney {
  return {
    id: data.id,
    poaType: data.poa_type,
    title: data.title,
    grantedTo: data.granted_to,
    grantedDate: data.granted_date,
    validFrom: data.valid_from,
    validUntil: data.valid_until,
    documentId: data.document_id,
    isActive: data.is_active,
    scope: data.scope,
    notarized: data.notarized,
    lastReviewed: data.last_reviewed,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

function transformTaxScenario(data: InheritanceTaxScenarioBackend): InheritanceTaxScenario {
  return {
    beneficiaryId: data.beneficiary_id,
    beneficiaryName: data.beneficiary_name,
    relationship: data.relationship,
    taxClass: data.tax_class,
    grossInheritance: data.gross_inheritance,
    taxableInheritance: data.taxable_inheritance,
    personalAllowance: data.personal_allowance,
    careAllowance: data.care_allowance,
    householdAllowance: data.household_allowance,
    otherDeductions: data.other_deductions,
    taxBase: data.tax_base,
    taxRate: data.tax_rate,
    taxAmount: data.tax_amount,
    effectiveTaxRate: data.effective_tax_rate,
  };
}

function transformTaxCalculation(data: InheritanceTaxCalculationBackend): InheritanceTaxCalculation {
  return {
    spaceId: data.space_id,
    totalEstate: data.total_estate,
    totalTax: data.total_tax,
    averageEffectiveRate: data.average_effective_rate,
    scenarios: data.scenarios.map(transformTaxScenario),
    calculatedAt: data.calculated_at,
  };
}

function transformUsufructCalculation(data: UsufructCalculationBackend): UsufructCalculation {
  return {
    assetValue: parseFloat(data.asset_value),
    usufructValue: parseFloat(data.usufruct_value),
    netGiftValue: parseFloat(data.net_gift_value),
    personalAllowance: parseFloat(data.personal_allowance),
    taxableAmount: parseFloat(data.taxable_amount),
    taxAmount: parseFloat(data.tax_amount),
    taxRate: data.tax_rate,
    savingsVsDirectGift: parseFloat(data.savings_vs_direct_gift),
    recommendation: data.recommendation,
  };
}

function transformHeirDocumentAccess(data: HeirDocumentAccessBackend): HeirDocumentAccess {
  return {
    id: data.id,
    heirName: data.heir_name,
    heirEmail: data.heir_email,
    documents: data.documents,
    folders: data.folders,
    trigger: data.trigger,
    triggerDate: data.trigger_date,
    triggerAge: data.trigger_age,
    isActive: data.is_active,
    accessGranted: data.access_granted,
    accessGrantedAt: data.access_granted_at,
    notes: data.notes,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

function transformGiftPlan(data: TenYearGiftPlanBackend): TenYearGiftPlan {
  return {
    beneficiaryId: data.beneficiary_id,
    beneficiaryName: data.beneficiary_name,
    allowancePer10Years: data.allowance_per_10_years,
    currentGiftsInPeriod: data.current_gifts_in_period,
    remainingAllowance: data.remaining_allowance,
    periodStart: data.period_start,
    periodEnd: data.period_end,
    nextRenewalDate: data.next_renewal_date,
    recommendedGifts: data.recommended_gifts.map((g) => ({
      amount: g.amount,
      date: g.date,
      taxFree: g.tax_free,
      estimatedTax: g.estimated_tax,
      description: g.description,
    })),
    totalTaxSavings: data.total_tax_savings,
  };
}

function transformEstateSummary(data: EstateSummaryBackend): EstateSummary {
  return {
    spaceId: data.space_id,
    totalAssets: data.total_assets,
    totalLiabilities: data.total_liabilities,
    netEstate: data.net_estate,
    realEstateValue: data.real_estate_value,
    investmentValue: data.investment_value,
    vehicleValue: data.vehicle_value,
    otherAssets: data.other_assets,
    mortgageDebt: data.mortgage_debt,
    otherDebt: data.other_debt,
    beneficiaries: data.beneficiaries.map(transformBeneficiary),
    totalShares: data.total_shares,
    taxScenarios: data.tax_scenarios.map(transformTaxScenario),
    totalEstimatedTax: data.total_estimated_tax,
    activePowersOfAttorney: data.active_powers_of_attorney.map(transformPowerOfAttorney),
    missingEssentialPoas: data.missing_essential_poas,
    heirDocumentAccess: data.heir_document_access.map(transformHeirDocumentAccess),
    recommendations: data.recommendations,
    warnings: data.warnings,
    calculatedAt: data.calculated_at,
  };
}

// ==================== API Service ====================

export const estatePlanningService = {
  // ==================== Estate Overview ====================

  /**
   * Holt die Nachlassübersicht
   */
  getEstateOverview: async (spaceId: string): Promise<EstateOverview> => {
    try {
      const response = await apiClient.get<{
        summary: EstateSummaryBackend;
        tax_calculation: InheritanceTaxCalculationBackend;
        gift_plans: TenYearGiftPlanBackend[];
      }>(`/privat/estate-planning/spaces/${spaceId}/overview`);

      return {
        summary: transformEstateSummary(response.data.summary),
        taxCalculation: transformTaxCalculation(response.data.tax_calculation),
        giftPlans: response.data.gift_plans.map(transformGiftPlan),
      };
    } catch (error) {
      handleApiError(error, 'Nachlassübersicht laden');
    }
  },

  /**
   * Holt die Nachlass-Zusammenfassung
   */
  getEstateSummary: async (spaceId: string): Promise<EstateSummary> => {
    try {
      const response = await apiClient.get<EstateSummaryBackend>(
        `/privat/estate-planning/spaces/${spaceId}/summary`
      );
      return transformEstateSummary(response.data);
    } catch (error) {
      handleApiError(error, 'Nachlass-Zusammenfassung laden');
    }
  },

  // ==================== Beneficiaries ====================

  /**
   * Listet alle Begünstigten
   */
  listBeneficiaries: async (spaceId: string): Promise<Beneficiary[]> => {
    try {
      const response = await apiClient.get<BeneficiaryBackend[]>(
        `/privat/estate-planning/spaces/${spaceId}/beneficiaries`
      );
      return response.data.map(transformBeneficiary);
    } catch (error) {
      handleApiError(error, 'Begünstigte laden');
    }
  },

  /**
   * Erstellt einen Begünstigten
   */
  createBeneficiary: async (spaceId: string, data: BeneficiaryCreate): Promise<Beneficiary> => {
    try {
      const response = await apiClient.post<BeneficiaryBackend>(
        `/privat/estate-planning/spaces/${spaceId}/beneficiaries`,
        {
          name: data.name,
          relationship: data.relationship,
          birth_date: data.birthDate,
          share_percent: data.sharePercent,
          specific_bequest: data.specificBequest,
          notes: data.notes,
        }
      );
      return transformBeneficiary(response.data);
    } catch (error) {
      handleApiError(error, 'Begünstigten erstellen');
    }
  },

  /**
   * Aktualisiert einen Begünstigten
   */
  updateBeneficiary: async (
    beneficiaryId: string,
    data: BeneficiaryUpdate
  ): Promise<Beneficiary> => {
    try {
      const response = await apiClient.patch<BeneficiaryBackend>(
        `/privat/estate-planning/beneficiaries/${beneficiaryId}`,
        {
          name: data.name,
          relationship: data.relationship,
          birth_date: data.birthDate,
          share_percent: data.sharePercent,
          specific_bequest: data.specificBequest,
          notes: data.notes,
        }
      );
      return transformBeneficiary(response.data);
    } catch (error) {
      handleApiError(error, 'Begünstigten aktualisieren');
    }
  },

  /**
   * Löscht einen Begünstigten
   */
  deleteBeneficiary: async (beneficiaryId: string): Promise<void> => {
    try {
      await apiClient.delete(`/privat/estate-planning/beneficiaries/${beneficiaryId}`);
    } catch (error) {
      handleApiError(error, 'Begünstigten löschen');
    }
  },

  // ==================== Inheritance Tax ====================

  /**
   * Berechnet die Erbschaftsteuer
   */
  calculateInheritanceTax: async (
    spaceId: string,
    options?: { isInheritance?: boolean }
  ): Promise<InheritanceTaxCalculation> => {
    try {
      const params = new URLSearchParams();
      if (options?.isInheritance !== undefined) {
        params.append('is_inheritance', String(options.isInheritance));
      }

      const url = `/privat/estate-planning/spaces/${spaceId}/calculate-tax${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<InheritanceTaxCalculationBackend>(url);
      return transformTaxCalculation(response.data);
    } catch (error) {
      handleApiError(error, 'Erbschaftsteuer berechnen');
    }
  },

  /**
   * Simuliert Erbschaftsteuer für einen einzelnen Erben
   */
  simulateTaxForHeir: async (
    spaceId: string,
    params: {
      relationship: RelationshipType;
      amount: number;
      birthDate?: string;
      isInheritance?: boolean;
    }
  ): Promise<InheritanceTaxScenario> => {
    try {
      const response = await apiClient.post<InheritanceTaxScenarioBackend>(
        `/privat/estate-planning/spaces/${spaceId}/simulate-tax`,
        {
          relationship: params.relationship,
          amount: params.amount,
          birth_date: params.birthDate,
          is_inheritance: params.isInheritance ?? true,
        }
      );
      return transformTaxScenario(response.data);
    } catch (error) {
      handleApiError(error, 'Steuer simulieren');
    }
  },

  // ==================== Usufruct (Niessbrauch) ====================

  /**
   * Berechnet den Niessbrauch-Wert
   */
  calculateUsufruct: async (params: {
    assetValue: number;
    annualYieldRate: number;
    beneficiaryAge: number;
    relationship: RelationshipType;
    gender?: 'm' | 'f';
  }): Promise<UsufructCalculation> => {
    try {
      const response = await apiClient.post<UsufructCalculationBackend>(
        `/privat/estate-planning/calculate-usufruct`,
        {
          asset_value: params.assetValue,
          annual_yield_rate: params.annualYieldRate,
          beneficiary_age: params.beneficiaryAge,
          relationship: params.relationship,
          gender: params.gender || 'm',
        }
      );
      return transformUsufructCalculation(response.data);
    } catch (error) {
      handleApiError(error, 'Niessbrauch berechnen');
    }
  },

  // ==================== Powers of Attorney ====================

  /**
   * Listet alle Vollmachten
   */
  listPowersOfAttorney: async (spaceId: string): Promise<PowerOfAttorney[]> => {
    try {
      const response = await apiClient.get<PowerOfAttorneyBackend[]>(
        `/privat/estate-planning/spaces/${spaceId}/powers-of-attorney`
      );
      return response.data.map(transformPowerOfAttorney);
    } catch (error) {
      handleApiError(error, 'Vollmachten laden');
    }
  },

  /**
   * Erstellt eine Vollmacht
   */
  createPowerOfAttorney: async (
    spaceId: string,
    data: PowerOfAttorneyCreate
  ): Promise<PowerOfAttorney> => {
    try {
      const response = await apiClient.post<PowerOfAttorneyBackend>(
        `/privat/estate-planning/spaces/${spaceId}/powers-of-attorney`,
        {
          poa_type: data.poaType,
          title: data.title,
          granted_to: data.grantedTo,
          granted_date: data.grantedDate,
          valid_from: data.validFrom,
          valid_until: data.validUntil,
          document_id: data.documentId,
          scope: data.scope,
          notarized: data.notarized,
        }
      );
      return transformPowerOfAttorney(response.data);
    } catch (error) {
      handleApiError(error, 'Vollmacht erstellen');
    }
  },

  /**
   * Aktualisiert eine Vollmacht
   */
  updatePowerOfAttorney: async (
    poaId: string,
    data: PowerOfAttorneyUpdate
  ): Promise<PowerOfAttorney> => {
    try {
      const response = await apiClient.patch<PowerOfAttorneyBackend>(
        `/privat/estate-planning/powers-of-attorney/${poaId}`,
        {
          title: data.title,
          granted_to: data.grantedTo,
          granted_date: data.grantedDate,
          valid_from: data.validFrom,
          valid_until: data.validUntil,
          is_active: data.isActive,
          scope: data.scope,
          notarized: data.notarized,
          last_reviewed: data.lastReviewed,
        }
      );
      return transformPowerOfAttorney(response.data);
    } catch (error) {
      handleApiError(error, 'Vollmacht aktualisieren');
    }
  },

  /**
   * Löscht eine Vollmacht
   */
  deletePowerOfAttorney: async (poaId: string): Promise<void> => {
    try {
      await apiClient.delete(`/privat/estate-planning/powers-of-attorney/${poaId}`);
    } catch (error) {
      handleApiError(error, 'Vollmacht löschen');
    }
  },

  // ==================== Heir Document Access ====================

  /**
   * Listet alle zeitgesteuerten Zugriffe
   */
  listHeirDocumentAccess: async (spaceId: string): Promise<HeirDocumentAccess[]> => {
    try {
      const response = await apiClient.get<HeirDocumentAccessBackend[]>(
        `/privat/estate-planning/spaces/${spaceId}/heir-access`
      );
      return response.data.map(transformHeirDocumentAccess);
    } catch (error) {
      handleApiError(error, 'Erben-Zugriffe laden');
    }
  },

  /**
   * Erstellt einen zeitgesteuerten Zugriff
   */
  createHeirDocumentAccess: async (
    spaceId: string,
    data: HeirDocumentAccessCreate
  ): Promise<HeirDocumentAccess> => {
    try {
      const response = await apiClient.post<HeirDocumentAccessBackend>(
        `/privat/estate-planning/spaces/${spaceId}/heir-access`,
        {
          heir_name: data.heirName,
          heir_email: data.heirEmail,
          documents: data.documents,
          folders: data.folders,
          trigger: data.trigger,
          trigger_date: data.triggerDate,
          trigger_age: data.triggerAge,
          notes: data.notes,
        }
      );
      return transformHeirDocumentAccess(response.data);
    } catch (error) {
      handleApiError(error, 'Erben-Zugriff erstellen');
    }
  },

  /**
   * Löscht einen zeitgesteuerten Zugriff
   */
  deleteHeirDocumentAccess: async (accessId: string): Promise<void> => {
    try {
      await apiClient.delete(`/privat/estate-planning/heir-access/${accessId}`);
    } catch (error) {
      handleApiError(error, 'Erben-Zugriff löschen');
    }
  },

  // ==================== Gift Planning ====================

  /**
   * Holt den 10-Jahres-Schenkungsplan
   */
  getGiftPlan: async (spaceId: string, beneficiaryId: string): Promise<TenYearGiftPlan> => {
    try {
      const response = await apiClient.get<TenYearGiftPlanBackend>(
        `/privat/estate-planning/spaces/${spaceId}/beneficiaries/${beneficiaryId}/gift-plan`
      );
      return transformGiftPlan(response.data);
    } catch (error) {
      handleApiError(error, 'Schenkungsplan laden');
    }
  },

  /**
   * Simuliert einen Schenkungsplan
   */
  simulateGiftPlan: async (
    spaceId: string,
    params: {
      beneficiaryId: string;
      totalIntendedGift: number;
      existingGifts?: Array<{ date: string; amount: number }>;
    }
  ): Promise<TenYearGiftPlan> => {
    try {
      const response = await apiClient.post<TenYearGiftPlanBackend>(
        `/privat/estate-planning/spaces/${spaceId}/simulate-gift-plan`,
        {
          beneficiary_id: params.beneficiaryId,
          total_intended_gift: params.totalIntendedGift,
          existing_gifts: params.existingGifts?.map((g) => ({
            date: g.date,
            amount: g.amount,
          })),
        }
      );
      return transformGiftPlan(response.data);
    } catch (error) {
      handleApiError(error, 'Schenkungsplan simulieren');
    }
  },
};

export default estatePlanningService;
