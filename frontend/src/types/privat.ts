/**
 * Privat-Modul - TypeScript Types
 *
 * Type definitions for Personal Document Management
 * Used across frontend components and API integration
 */

// =============================================================================
// ENUMS
// =============================================================================

/** Space type - personal or shared */
export type PrivatSpaceType = 'personal' | 'shared';

/** Access level for space permissions */
export type PrivatAccessLevel = 'read' | 'write' | 'manage' | 'admin';

/** Document type classification */
export type PrivatDocumentType =
  | 'contract'
  | 'invoice'
  | 'receipt'
  | 'certificate'
  | 'insurance_policy'
  | 'tax_document'
  | 'correspondence'
  | 'photo'
  | 'other';

/** Deadline type classification */
export type PrivatDeadlineType =
  | 'insurance_payment'
  | 'loan_payment'
  | 'tax_deadline'
  | 'contract_renewal'
  | 'vehicle_inspection'
  | 'registration_renewal'
  | 'custom';

/** Insurance type */
export type InsuranceType =
  | 'health'
  | 'life'
  | 'liability'
  | 'household'
  | 'building'
  | 'vehicle'
  | 'legal'
  | 'disability'
  | 'travel'
  | 'other';

/** Vehicle type */
export type VehicleType =
  | 'car'
  | 'motorcycle'
  | 'truck'
  | 'trailer'
  | 'other';

/** Fuel type */
export type FuelType =
  | 'petrol'
  | 'diesel'
  | 'electric'
  | 'hybrid'
  | 'lpg'
  | 'other';

/** Loan type */
export type LoanType =
  | 'mortgage'
  | 'personal'
  | 'car'
  | 'student'
  | 'business'
  | 'other';

/** Investment type */
export type InvestmentType =
  | 'savings'
  | 'stocks'
  | 'bonds'
  | 'fund'
  | 'etf'
  | 'real_estate'
  | 'crypto'
  | 'pension'
  | 'other';

/** Emergency access request status */
export type PrivatEmergencyAccessStatus =
  | 'pending'
  | 'approved'
  | 'denied'
  | 'expired';

// =============================================================================
// SPACE INTERFACES
// =============================================================================

/** Space base interface */
export interface PrivatSpace {
  id: string;
  name: string;
  description?: string;
  spaceType: PrivatSpaceType;
  ownerId: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Space with statistics */
export interface PrivatSpaceWithStats extends PrivatSpace {
  documentCount: number;
  folderCount: number;
  totalSizeBytes: number;
  pendingDeadlines: number;
}

/** Space create request */
export interface PrivatSpaceCreate {
  name: string;
  description?: string;
  spaceType: PrivatSpaceType;
}

/** Space update request */
export interface PrivatSpaceUpdate {
  name?: string;
  description?: string;
}

/** Space access permission */
export interface PrivatSpaceAccess {
  id: string;
  spaceId: string;
  userId: string;
  accessLevel: PrivatAccessLevel;
  grantedBy: string;
  grantedAt: string;
  expiresAt?: string;
  isActive: boolean;
}

/** Space access create request */
export interface PrivatSpaceAccessCreate {
  userId: string;
  accessLevel: PrivatAccessLevel;
  expiresAt?: string;
}

// =============================================================================
// FOLDER INTERFACES
// =============================================================================

/** Folder base interface */
export interface PrivatFolder {
  id: string;
  spaceId: string;
  parentId?: string;
  name: string;
  path: string;
  icon?: string;
  color?: string;
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
}

/** Folder tree node */
export interface PrivatFolderTree extends PrivatFolder {
  children: PrivatFolderTree[];
  documentCount: number;
}

/** Folder create request */
export interface PrivatFolderCreate {
  parentId?: string;
  name: string;
  icon?: string;
  color?: string;
}

/** Folder update request */
export interface PrivatFolderUpdate {
  name?: string;
  icon?: string;
  color?: string;
  sortOrder?: number;
}

// =============================================================================
// DOCUMENT INTERFACES
// =============================================================================

/** Document base interface */
export interface PrivatDocument {
  id: string;
  spaceId: string;
  folderId?: string;
  title: string;
  documentType: PrivatDocumentType;
  filePath?: string;
  fileSize?: number;
  mimeType?: string;
  description?: string;
  tags?: string[];
  isExtraEncrypted: boolean;
  passwordHint?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Document create request */
export interface PrivatDocumentCreate {
  folderId?: string;
  title: string;
  documentType: PrivatDocumentType;
  filePath?: string;
  fileSize?: number;
  mimeType?: string;
  description?: string;
  tags?: string[];
  passwordHint?: string;
}

/** Document update request */
export interface PrivatDocumentUpdate {
  folderId?: string;
  title?: string;
  documentType?: PrivatDocumentType;
  description?: string;
  tags?: string[];
}

/** Document list response */
export interface PrivatDocumentListResponse {
  items: PrivatDocument[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

// =============================================================================
// PROPERTY INTERFACES
// =============================================================================

/** Property base interface */
export interface PrivatProperty {
  id: string;
  spaceId: string;
  name: string;
  propertyType: string;
  addressStreet?: string;
  addressCity?: string;
  addressZip?: string;
  addressCountry?: string;
  purchaseDate?: string;
  purchasePrice?: number;
  currentValue?: number;
  sizeSqm?: number;
  rooms?: number;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Property with details (tenants, income) */
export interface PrivatPropertyWithDetails extends PrivatProperty {
  tenants: PrivatTenant[];
  totalRentalIncome: number;
  occupancyRate: number;
  averageRent: number;
}

/** Property create request */
export interface PrivatPropertyCreate {
  name: string;
  propertyType: string;
  addressStreet?: string;
  addressCity?: string;
  addressZip?: string;
  addressCountry?: string;
  purchaseDate?: string;
  purchasePrice?: number;
  currentValue?: number;
  sizeSqm?: number;
  rooms?: number;
  notes?: string;
}

/** Property update request */
export interface PrivatPropertyUpdate {
  name?: string;
  propertyType?: string;
  addressStreet?: string;
  addressCity?: string;
  addressZip?: string;
  addressCountry?: string;
  currentValue?: number;
  sizeSqm?: number;
  rooms?: number;
  notes?: string;
}

/** Property list response */
export interface PrivatPropertyListResponse {
  items: PrivatPropertyWithDetails[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

// =============================================================================
// TENANT INTERFACES
// =============================================================================

/** Tenant base interface */
export interface PrivatTenant {
  id: string;
  propertyId: string;
  firstName: string;
  lastName: string;
  email?: string;
  phone?: string;
  moveInDate?: string;
  moveOutDate?: string;
  monthlyRent?: number;
  deposit?: number;
  depositPaid: boolean;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Tenant create request */
export interface PrivatTenantCreate {
  firstName: string;
  lastName: string;
  email?: string;
  phone?: string;
  moveInDate?: string;
  monthlyRent?: number;
  deposit?: number;
  notes?: string;
}

/** Tenant update request */
export interface PrivatTenantUpdate {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  moveOutDate?: string;
  monthlyRent?: number;
  notes?: string;
}

// =============================================================================
// RENTAL INCOME INTERFACES
// =============================================================================

/** Rental income entry */
export interface PrivatRentalIncome {
  id: string;
  tenantId: string;
  amount: number;
  paymentDate: string;
  periodStart?: string;
  periodEnd?: string;
  paymentMethod?: string;
  notes?: string;
  createdAt: string;
}

/** Rental income create request */
export interface PrivatRentalIncomeCreate {
  amount: number;
  paymentDate: string;
  periodStart?: string;
  periodEnd?: string;
  paymentMethod?: string;
  notes?: string;
}

// =============================================================================
// VEHICLE INTERFACES
// =============================================================================

/** Vehicle base interface */
export interface PrivatVehicle {
  id: string;
  spaceId: string;
  name: string;
  vehicleType: VehicleType;
  brand?: string;
  model?: string;
  year?: number;
  licensePlate?: string;
  vin?: string;
  fuelType?: FuelType;
  purchaseDate?: string;
  purchasePrice?: number;
  currentMileage?: number;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Vehicle with statistics */
export interface PrivatVehicleWithStats extends PrivatVehicle {
  averageConsumption?: number;
  totalFuelCost?: number;
  costPerKm?: number;
  lastFuelDate?: string;
}

/** Vehicle create request */
export interface PrivatVehicleCreate {
  name: string;
  vehicleType: VehicleType;
  brand?: string;
  model?: string;
  year?: number;
  licensePlate?: string;
  vin?: string;
  fuelType?: FuelType;
  purchaseDate?: string;
  purchasePrice?: number;
  currentMileage?: number;
  notes?: string;
}

/** Vehicle update request */
export interface PrivatVehicleUpdate {
  name?: string;
  vehicleType?: VehicleType;
  brand?: string;
  model?: string;
  licensePlate?: string;
  currentMileage?: number;
  notes?: string;
}

/** Vehicle list response */
export interface PrivatVehicleListResponse {
  items: PrivatVehicleWithStats[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

// =============================================================================
// FUEL LOG INTERFACES
// =============================================================================

/** Fuel log entry */
export interface PrivatFuelLog {
  id: string;
  vehicleId: string;
  date: string;
  mileage: number;
  liters: number;
  pricePerLiter: number;
  totalCost: number;
  fuelType?: FuelType;
  station?: string;
  isFullTank: boolean;
  notes?: string;
  createdAt: string;
}

/** Fuel log create request */
export interface PrivatFuelLogCreate {
  date: string;
  mileage: number;
  liters: number;
  pricePerLiter: number;
  fuelType?: FuelType;
  station?: string;
  isFullTank?: boolean;
  notes?: string;
}

/** Fuel statistics */
export interface PrivatFuelStatistics {
  averageConsumption: number;
  totalLiters: number;
  totalCost: number;
  costPerKm: number;
  averagePricePerLiter: number;
  totalDistance: number;
}

// =============================================================================
// INSURANCE INTERFACES
// =============================================================================

/** Insurance base interface */
export interface PrivatInsurance {
  id: string;
  spaceId: string;
  name: string;
  insuranceType: InsuranceType;
  provider?: string;
  policyNumber?: string;
  premium?: number;
  premiumInterval?: string;
  coverageAmount?: number;
  deductible?: number;
  startDate?: string;
  endDate?: string;
  cancellationPeriod?: number;
  autoRenewal: boolean;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Insurance with deadline info */
export interface PrivatInsuranceWithDeadlines extends PrivatInsurance {
  upcomingPayment?: string;
  daysUntilPayment?: number;
  annualCost?: number;
}

/** Insurance create request */
export interface PrivatInsuranceCreate {
  name: string;
  insuranceType: InsuranceType;
  provider?: string;
  policyNumber?: string;
  premium?: number;
  premiumInterval?: string;
  coverageAmount?: number;
  deductible?: number;
  startDate?: string;
  endDate?: string;
  cancellationPeriod?: number;
  autoRenewal?: boolean;
  notes?: string;
}

/** Insurance update request */
export interface PrivatInsuranceUpdate {
  name?: string;
  insuranceType?: InsuranceType;
  provider?: string;
  policyNumber?: string;
  premium?: number;
  premiumInterval?: string;
  coverageAmount?: number;
  deductible?: number;
  endDate?: string;
  cancellationPeriod?: number;
  autoRenewal?: boolean;
  notes?: string;
}

/** Insurance list response */
export interface PrivatInsuranceListResponse {
  items: PrivatInsuranceWithDeadlines[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

// =============================================================================
// LOAN INTERFACES
// =============================================================================

/** Loan base interface */
export interface PrivatLoan {
  id: string;
  spaceId: string;
  name: string;
  loanType: LoanType;
  lender?: string;
  principalAmount: number;
  currentBalance: number;
  interestRate?: number;
  monthlyPayment?: number;
  startDate?: string;
  endDate?: string;
  nextPaymentDate?: string;
  accountNumber?: string;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Loan with statistics */
export interface PrivatLoanWithStats extends PrivatLoan {
  totalPaid: number;
  totalInterestPaid: number;
  remainingMonths?: number;
  payoffDate?: string;
}

/** Loan create request */
export interface PrivatLoanCreate {
  name: string;
  loanType: LoanType;
  lender?: string;
  principalAmount: number;
  currentBalance: number;
  interestRate?: number;
  monthlyPayment?: number;
  startDate?: string;
  endDate?: string;
  nextPaymentDate?: string;
  accountNumber?: string;
  notes?: string;
}

/** Loan update request */
export interface PrivatLoanUpdate {
  name?: string;
  loanType?: LoanType;
  lender?: string;
  interestRate?: number;
  monthlyPayment?: number;
  nextPaymentDate?: string;
  notes?: string;
}

/** Loan list response */
export interface PrivatLoanListResponse {
  items: PrivatLoanWithStats[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

// =============================================================================
// INVESTMENT INTERFACES
// =============================================================================

/** Investment base interface */
export interface PrivatInvestment {
  id: string;
  spaceId: string;
  name: string;
  investmentType: InvestmentType;
  institution?: string;
  accountNumber?: string;
  initialAmount: number;
  currentValue: number;
  interestRate?: number;
  startDate?: string;
  maturityDate?: string;
  isTaxable: boolean;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Investment with statistics */
export interface PrivatInvestmentWithStats extends PrivatInvestment {
  totalReturn: number;
  returnPercentage: number;
  annualReturn?: number;
}

/** Investment create request */
export interface PrivatInvestmentCreate {
  name: string;
  investmentType: InvestmentType;
  institution?: string;
  accountNumber?: string;
  initialAmount: number;
  currentValue: number;
  interestRate?: number;
  startDate?: string;
  maturityDate?: string;
  isTaxable?: boolean;
  notes?: string;
}

/** Investment update request */
export interface PrivatInvestmentUpdate {
  name?: string;
  investmentType?: InvestmentType;
  institution?: string;
  currentValue?: number;
  interestRate?: number;
  maturityDate?: string;
  notes?: string;
}

/** Investment list response */
export interface PrivatInvestmentListResponse {
  items: PrivatInvestmentWithStats[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

/** Portfolio breakdown */
export interface PrivatPortfolioBreakdown {
  breakdown: Record<string, { value: number; percentage: number }>;
  total: number;
}

// =============================================================================
// DEADLINE INTERFACES
// =============================================================================

/** Deadline base interface */
export interface PrivatDeadline {
  id: string;
  spaceId: string;
  title: string;
  description?: string;
  deadlineType: PrivatDeadlineType;
  dueDate: string;
  reminderDays?: number[];
  isRecurring: boolean;
  recurrenceInterval?: string;
  priority?: number;
  relatedEntityType?: string;
  relatedEntityId?: string;
  isCompleted: boolean;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
}

/** Deadline with status info */
export interface PrivatDeadlineWithStatus extends PrivatDeadline {
  daysRemaining: number;
  isOverdue: boolean;
  nextReminder?: string;
  relatedEntityName?: string;
}

/** Deadline create request */
export interface PrivatDeadlineCreate {
  title: string;
  description?: string;
  deadlineType: PrivatDeadlineType;
  dueDate: string;
  reminderDays?: number[];
  isRecurring?: boolean;
  recurrenceInterval?: string;
  priority?: number;
  relatedEntityType?: string;
  relatedEntityId?: string;
}

/** Deadline update request */
export interface PrivatDeadlineUpdate {
  title?: string;
  description?: string;
  deadlineType?: PrivatDeadlineType;
  dueDate?: string;
  reminderDays?: number[];
  isRecurring?: boolean;
  recurrenceInterval?: string;
  priority?: number;
}

/** Deadline list response */
export interface PrivatDeadlineListResponse {
  items: PrivatDeadlineWithStatus[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

/** Dashboard deadline widget */
export interface PrivatDeadlineWidget {
  today: PrivatDeadlineWithStatus[];
  thisWeek: PrivatDeadlineWithStatus[];
  thisMonth: PrivatDeadlineWithStatus[];
  overdue: PrivatDeadlineWithStatus[];
}

// =============================================================================
// EMERGENCY ACCESS INTERFACES
// =============================================================================

/** Emergency contact */
export interface PrivatEmergencyContact {
  id: string;
  spaceId: string;
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  relationship?: string;
  waitingPeriodDays: number;
  notes?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Emergency contact create request */
export interface PrivatEmergencyContactCreate {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  relationship?: string;
  waitingPeriodDays?: number;
  notes?: string;
}

/** Emergency contact update request */
export interface PrivatEmergencyContactUpdate {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  relationship?: string;
  waitingPeriodDays?: number;
  notes?: string;
}

/** Emergency access request */
export interface PrivatEmergencyAccessRequest {
  id: string;
  spaceId: string;
  contactId: string;
  status: PrivatEmergencyAccessStatus;
  reason?: string;
  requestedAt: string;
  waitingUntil: string;
  approvedAt?: string;
  deniedAt?: string;
  deniedReason?: string;
}

/** Emergency access request create */
export interface PrivatEmergencyAccessRequestCreate {
  spaceId: string;
  reason: string;
}

// =============================================================================
// DASHBOARD INTERFACES
// =============================================================================

/** Dashboard statistics */
export interface PrivatDashboardStats {
  totalSpaces: number;
  totalDocuments: number;
  totalProperties: number;
  totalVehicles: number;
  totalInsurances: number;
  totalLoans: number;
  totalInvestments: number;
  upcomingDeadlines: number;
  overdueDeadlines: number;
}

/** Financial summary */
export interface PrivatFinancialSummary {
  netWorth: number;
  totalInvestments: number;
  totalLoans: number;
  monthlyLoanPayments: number;
  annualInsuranceCost: number;
  investmentReturnPercentage: number;
}

// =============================================================================
// UTILITY TYPES
// =============================================================================

/** Generic paginated response */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

/** API error response */
export interface ApiError {
  detail: string;
  code?: string;
}

// =============================================================================
// ENTERPRISE INTELLIGENCE INTERFACES
// =============================================================================

/** Investment Performance Analytics */
export interface InvestmentPerformance {
  investmentId: string;
  name: string;
  investmentType: InvestmentType;
  initialAmount: number;
  currentValue: number;
  absoluteReturn: number;
  percentageReturn: number;
  annualizedReturn: number;
  holdingPeriodDays: number;
  holdingPeriodYears: number;
  calculatedAt: string;
}

/** Portfolio Allocation */
export interface PortfolioAllocation {
  spaceId: string;
  totalValue: number;
  investmentCount: number;
  allocationByType: Record<string, { value: number; percentage: number; count: number }>;
  topHoldings: Array<{ name: string; value: number; percentage: number }>;
  calculatedAt: string;
}

/** Diversification Score */
export interface DiversificationScore {
  spaceId: string;
  herfindahlIndex: number;
  diversificationScore: number;
  interpretation: 'schlecht' | 'mittel' | 'gut' | 'sehr_gut';
  typeCount: number;
  dominantType: string;
  dominantTypePercentage: number;
  recommendations: string[];
  calculatedAt: string;
}

/** Risk Profile */
export interface RiskProfile {
  spaceId: string;
  overallRiskScore: number;
  riskCategory: 'konservativ' | 'ausgewogen' | 'wachstum' | 'aggressiv';
  riskByType: Record<string, { allocation: number; riskLevel: number; contribution: number }>;
  volatilityEstimate: number;
  recommendations: string[];
  calculatedAt: string;
}

/** Rebalancing Suggestion */
export interface RebalancingSuggestion {
  spaceId: string;
  currentAllocation: Record<string, number>;
  targetAllocation: Record<string, number>;
  rebalanceActions: Array<{
    type: string;
    currentPercentage: number;
    targetPercentage: number;
    action: 'kaufen' | 'verkaufen' | 'halten';
    amountToAdjust: number;
  }>;
  totalAdjustmentNeeded: number;
  calculatedAt: string;
}

/** Full Investment Analytics */
export interface InvestmentFullAnalytics {
  spaceId: string;
  allocation: PortfolioAllocation;
  diversification: DiversificationScore;
  riskProfile: RiskProfile;
  rebalancing: RebalancingSuggestion;
  calculatedAt: string;
}

/** Net Worth Components */
export interface NetWorthComponents {
  spaceId: string;
  totalAssets: number;
  totalLiabilities: number;
  netWorth: number;
  components: {
    properties: { count: number; value: number };
    vehicles: { count: number; value: number };
    investments: { count: number; value: number };
    loans: { count: number; outstanding: number };
  };
  assetAllocation: Record<string, { value: number; percentage: number }>;
  calculatedAt: string;
}

/** Financial Health Score Dimension */
export interface HealthDimension {
  score: number;
  weight: number;
  contribution: number;
  interpretation: string;
  recommendations: string[];
}

/** Financial Health Score */
export interface FinancialHealthScore {
  spaceId: string;
  overallScore: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  dimensions: {
    netWorthTrend: HealthDimension;
    debtManagement: HealthDimension;
    insuranceCoverage: HealthDimension;
    liquidity: HealthDimension;
    retirementReadiness: HealthDimension;
    diversification: HealthDimension;
  };
  topStrengths: string[];
  topWeaknesses: string[];
  actionItems: string[];
  calculatedAt: string;
}

/** Smart Recommendation */
export interface SmartRecommendation {
  id: string;
  category: 'refinancing' | 'rebalancing' | 'insurance_gap' | 'emergency_fund' | 'high_cost' | 'deadline' | 'general';
  priority: 'niedrig' | 'mittel' | 'hoch' | 'kritisch';
  title: string;
  description: string;
  potentialSavings?: number;
  potentialGain?: number;
  relatedEntityType?: string;
  relatedEntityId?: string;
  relatedEntityName?: string;
  actionUrl?: string;
  createdAt: string;
}

/** Smart Recommendations List */
export interface SmartRecommendationsList {
  spaceId: string;
  recommendations: SmartRecommendation[];
  totalCount: number;
  criticalCount: number;
  highCount: number;
  potentialTotalSavings: number;
  generatedAt: string;
}

/** Loan Extra Payment Scenario */
export interface ExtraPaymentScenario {
  loanId: string;
  loanName: string;
  currentBalance: number;
  currentMonthlyPayment: number;
  currentRemainingMonths: number;
  currentTotalInterest: number;
  extraMonthlyPayment: number;
  newMonthlyPayment: number;
  newRemainingMonths: number;
  newTotalInterest: number;
  interestSaved: number;
  monthsSaved: number;
  newPayoffDate: string;
  calculatedAt: string;
}

/** Loan Refinancing Scenario */
export interface RefinancingScenario {
  loanId: string;
  loanName: string;
  currentBalance: number;
  currentRate: number;
  currentMonthlyPayment: number;
  currentRemainingMonths: number;
  currentTotalCost: number;
  newRate: number;
  estimatedPrepaymentPenalty: number;
  refinancingCosts: number;
  newMonthlyPayment: number;
  newTotalCost: number;
  totalSavings: number;
  breakEvenMonths: number;
  isWorthwhile: boolean;
  recommendation: string;
  calculatedAt: string;
}

/** Amortization Schedule Entry */
export interface AmortizationEntry {
  month: number;
  date: string;
  payment: number;
  principal: number;
  interest: number;
  balance: number;
  cumulativeInterest: number;
  cumulativePrincipal: number;
}

/** Full Amortization Schedule */
export interface FullAmortizationSchedule {
  loanId: string;
  loanName: string;
  principalAmount: number;
  interestRate: number;
  monthlyPayment: number;
  totalMonths: number;
  totalInterest: number;
  totalCost: number;
  schedule: AmortizationEntry[];
  summary: {
    firstYearInterest: number;
    lastYearInterest: number;
    halfwayDate: string;
    halfwayBalance: number;
  };
  calculatedAt: string;
}

/** Loan Comparison */
export interface LoanComparison {
  loanId: string;
  loanName: string;
  scenarios: Array<{
    name: string;
    monthlyPayment: number;
    totalMonths: number;
    totalInterest: number;
    totalCost: number;
    payoffDate: string;
  }>;
  recommendation: string;
  calculatedAt: string;
}

/** Property Intelligence KPIs */
export interface PropertyIntelligence {
  propertyId: string;
  name: string;
  estimatedValue: number;
  purchasePrice: number;
  valueAppreciation: number;
  valueAppreciationRate: number;
  grossYield: number;
  netYield: number;
  annualRoi: number;
  totalCostsYtd: number;
  occupancyRate: number;
  calculatedAt: string;
}

/** Vehicle Intelligence KPIs */
export interface VehicleIntelligence {
  vehicleId: string;
  name: string;
  purchasePrice: number;
  currentValue: number;
  totalDepreciation: number;
  depreciationRate: number;
  annualDepreciation: number;
  totalCostOfOwnership: number;
  costPerKm: number;
  costPerMonth: number;
  nextServiceDate?: string;
  nextServiceEstimatedCost?: number;
  calculatedAt: string;
}
