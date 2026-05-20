/**
 * DLP Admin Feature
 */

export { DLPAdminPage } from './DLPAdminPage';
export { dlpApi } from './api/dlp-api';
export type {
  DLPPolicy,
  DLPAction,
  SensitiveDataType,
  DLPCheckResult,
  ScanResponse,
} from './api/dlp-api';
export {
  useDLPPolicies,
  useDLPPolicy,
  useCreatePolicy,
  useUpdatePolicy,
  useDeletePolicy,
  useCheckAccess,
  useScanSensitiveData,
} from './hooks/use-dlp';
