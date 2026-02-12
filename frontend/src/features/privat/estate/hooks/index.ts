/**
 * Estate Planning Hooks - Index
 *
 * Zentrale Exports für alle Estate Planning Hooks
 */

export {
  estateQueryKeys,
  useEstateOverview,
  useEstateSummary,
} from './useEstateOverview';

export {
  useInheritanceTax,
  useSimulateTax,
  useCalculateUsufruct,
  calculateTaxLocal,
  calculateTaxRateLocal,
  TAX_ALLOWANCES,
  CARE_ALLOWANCES,
  TAX_CLASS_MAPPING,
  TAX_RATES,
  RELATIONSHIP_LABELS,
} from './useInheritanceTax';

export {
  useBeneficiaries,
  useGiftPlan,
  useCreateBeneficiary,
  useUpdateBeneficiary,
  useDeleteBeneficiary,
  useSimulateGiftPlan,
} from './useBeneficiaries';

export {
  usePowersOfAttorney,
  useHeirDocumentAccess,
  useCreatePowerOfAttorney,
  useUpdatePowerOfAttorney,
  useDeletePowerOfAttorney,
  useCreateHeirDocumentAccess,
  useDeleteHeirDocumentAccess,
  getMissingEssentialPoas,
  formatPoaDate,
  POA_TYPE_LABELS,
  POA_TYPE_DESCRIPTIONS,
  ESSENTIAL_POAS,
} from './usePowerOfAttorney';
