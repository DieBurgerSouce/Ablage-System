/**
 * Payment Behavior Feature Module
 *
 * Public exports fuer Zahlungsverhaltens-Analyse.
 */

// Types
export * from './types/payment-behavior-types';

// API
export { paymentBehaviorService, PaymentBehaviorApiError } from './api/payment-behavior-api';

// Hooks
export {
  paymentBehaviorKeys,
  usePaymentBehaviorReport,
  useCustomerPaymentBehavior,
  useCustomerRanking,
  useCategoryDistribution,
  usePaymentBehaviorDashboard,
} from './hooks/use-payment-behavior-queries';

// Components
export { PaymentBehaviorDashboard } from './components/PaymentBehaviorDashboard';
