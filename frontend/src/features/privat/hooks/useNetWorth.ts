/**
 * useNetWorth - Aggregated Net Worth Data Hook
 *
 * Aggregates data from multiple sources:
 * - Immobilien (Properties)
 * - Fahrzeuge (Vehicles)
 * - Anlagen (Investments)
 * - Kredite (Loans)
 *
 * Provides calculated net worth and historical trends
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import { privatIntelligenceService } from '@/lib/api/services/privat-intelligence';
import * as privatApi from '../api/privat-api';
import type {
  NetWorthComponents,
  PrivatPropertyWithDetails,
  PrivatVehicleWithStats,
  PrivatInvestmentWithStats,
  PrivatLoanWithStats,
} from '@/types/privat';

// ==================== Types ====================

export interface NetWorthHistoryEntry {
  date: string;
  totalAssets: number;
  totalLiabilities: number;
  netWorth: number;
}

export interface AssetBreakdown {
  category: string;
  label: string;
  value: number;
  count: number;
  percentage: number;
  color: string;
  items: Array<{
    id: string;
    name: string;
    value: number;
  }>;
}

export interface LiabilityBreakdown {
  category: string;
  label: string;
  value: number;
  count: number;
  percentage: number;
  color: string;
  items: Array<{
    id: string;
    name: string;
    outstanding: number;
    monthlyPayment?: number;
  }>;
}

export interface NetWorthSummary {
  totalAssets: number;
  totalLiabilities: number;
  netWorth: number;
  monthlyChange: number;
  monthlyChangePercent: number;
  assetBreakdown: AssetBreakdown[];
  liabilityBreakdown: LiabilityBreakdown[];
  history: NetWorthHistoryEntry[];
  lastUpdated: string;
}

// ==================== Constants ====================

export const ASSET_COLORS = {
  properties: '#3b82f6',    // Blue
  vehicles: '#10b981',      // Emerald
  investments: '#f59e0b',   // Amber
  bankAccounts: '#22c55e',  // Green
  other: '#8b5cf6',         // Violet
};

export const LIABILITY_COLORS = {
  mortgages: '#ef4444',     // Red
  loans: '#f97316',         // Orange
  creditCards: '#ec4899',   // Pink
  other: '#6b7280',         // Gray
};

export const ASSET_LABELS: Record<string, string> = {
  properties: 'Immobilien',
  vehicles: 'Fahrzeuge',
  investments: 'Anlagen',
  bankAccounts: 'Bankkonten',
  other: 'Sonstiges',
};

export const LIABILITY_LABELS: Record<string, string> = {
  mortgages: 'Hypotheken',
  loans: 'Kredite',
  creditCards: 'Kreditkarten',
  other: 'Sonstige',
};

// ==================== Query Keys ====================

export const netWorthQueryKeys = {
  all: ['networth'] as const,
  summary: (spaceId: string) => [...netWorthQueryKeys.all, 'summary', spaceId] as const,
  history: (spaceId: string, months?: number) => [...netWorthQueryKeys.all, 'history', spaceId, months] as const,
  breakdown: (spaceId: string) => [...netWorthQueryKeys.all, 'breakdown', spaceId] as const,
};

// ==================== Utility Functions ====================

/**
 * Formats a number as German currency (1.234,56 EUR)
 */
export function formatCurrencyDE(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Formats a number with German number format (1.234,56)
 */
export function formatNumberDE(value: number, decimals = 0): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Formats percentage with German locale
 */
export function formatPercentDE(value: number, decimals = 1): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

/**
 * Abbreviates large numbers for display
 */
export function abbreviateNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${formatNumberDE(value / 1_000_000, 2)} Mio.`;
  } else if (Math.abs(value) >= 1_000) {
    return `${formatNumberDE(value / 1_000, 1)} Tsd.`;
  }
  return formatNumberDE(value, 0);
}

// ==================== Main Hook ====================

interface UseNetWorthOptions {
  enabled?: boolean;
  refetchInterval?: number;
}

export function useNetWorth(spaceId: string, options: UseNetWorthOptions = {}) {
  const { enabled = true, refetchInterval } = options;

  // Fetch net worth from intelligence service
  const netWorthQuery = useQuery({
    queryKey: netWorthQueryKeys.summary(spaceId),
    queryFn: () => privatIntelligenceService.getNetWorth(spaceId),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval,
  });

  // Fetch properties for detailed breakdown
  const propertiesQuery = useQuery({
    queryKey: ['privat', 'properties', spaceId],
    queryFn: () => privatApi.listProperties(spaceId, {}),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch vehicles for detailed breakdown
  const vehiclesQuery = useQuery({
    queryKey: ['privat', 'vehicles', spaceId],
    queryFn: () => privatApi.listVehicles(spaceId, {}),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch investments for detailed breakdown
  const investmentsQuery = useQuery({
    queryKey: ['privat', 'investments', spaceId],
    queryFn: () => privatApi.listInvestments(spaceId, {}),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch loans for detailed breakdown
  const loansQuery = useQuery({
    queryKey: ['privat', 'loans', spaceId],
    queryFn: () => privatApi.listLoans(spaceId, {}),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch historical snapshots for trend
  const snapshotsQuery = useQuery({
    queryKey: netWorthQueryKeys.history(spaceId, 12),
    queryFn: () => privatApi.listPortfolioSnapshots(spaceId, 12),
    enabled: enabled && !!spaceId,
    staleTime: 5 * 60 * 1000,
  });

  // Combined loading state
  const isLoading =
    netWorthQuery.isLoading ||
    propertiesQuery.isLoading ||
    vehiclesQuery.isLoading ||
    investmentsQuery.isLoading ||
    loansQuery.isLoading ||
    snapshotsQuery.isLoading;

  // Combined fetching state
  const isFetching =
    netWorthQuery.isFetching ||
    propertiesQuery.isFetching ||
    vehiclesQuery.isFetching ||
    investmentsQuery.isFetching ||
    loansQuery.isFetching ||
    snapshotsQuery.isFetching;

  // Combined error
  const error =
    netWorthQuery.error ||
    propertiesQuery.error ||
    vehiclesQuery.error ||
    investmentsQuery.error ||
    loansQuery.error ||
    snapshotsQuery.error;

  // Build summary data
  const summary = buildNetWorthSummary(
    netWorthQuery.data,
    propertiesQuery.data?.items,
    vehiclesQuery.data?.items,
    investmentsQuery.data?.items,
    loansQuery.data?.items,
    snapshotsQuery.data
  );

  return {
    summary,
    netWorth: netWorthQuery.data,
    properties: propertiesQuery.data?.items ?? [],
    vehicles: vehiclesQuery.data?.items ?? [],
    investments: investmentsQuery.data?.items ?? [],
    loans: loansQuery.data?.items ?? [],
    history: snapshotsQuery.data ?? [],
    isLoading,
    isFetching,
    error,
    refetch: async () => {
      await Promise.all([
        netWorthQuery.refetch(),
        propertiesQuery.refetch(),
        vehiclesQuery.refetch(),
        investmentsQuery.refetch(),
        loansQuery.refetch(),
        snapshotsQuery.refetch(),
      ]);
    },
  };
}

// ==================== Helper Functions ====================

function buildNetWorthSummary(
  netWorth?: NetWorthComponents,
  properties?: PrivatPropertyWithDetails[],
  vehicles?: PrivatVehicleWithStats[],
  investments?: PrivatInvestmentWithStats[],
  loans?: PrivatLoanWithStats[],
  snapshots?: privatApi.PortfolioSnapshot[]
): NetWorthSummary | undefined {
  if (!netWorth) return undefined;

  // Calculate monthly change from snapshots
  const sortedSnapshots = (snapshots ?? [])
    .sort((a, b) => new Date(b.snapshotDate).getTime() - new Date(a.snapshotDate).getTime());

  const currentNetWorth = netWorth.netWorth;
  const previousNetWorth = sortedSnapshots[1]?.netWorth ?? currentNetWorth;
  const monthlyChange = currentNetWorth - previousNetWorth;
  const monthlyChangePercent = previousNetWorth !== 0
    ? (monthlyChange / Math.abs(previousNetWorth)) * 100
    : 0;

  // Build asset breakdown
  const assetBreakdown = buildAssetBreakdown(netWorth, properties, vehicles, investments);

  // Build liability breakdown
  const liabilityBreakdown = buildLiabilityBreakdown(netWorth, loans);

  // Build history from snapshots
  const history = buildHistory(sortedSnapshots);

  return {
    totalAssets: netWorth.totalAssets,
    totalLiabilities: netWorth.totalLiabilities,
    netWorth: netWorth.netWorth,
    monthlyChange,
    monthlyChangePercent,
    assetBreakdown,
    liabilityBreakdown,
    history,
    lastUpdated: netWorth.calculatedAt,
  };
}

function buildAssetBreakdown(
  netWorth: NetWorthComponents,
  properties?: PrivatPropertyWithDetails[],
  vehicles?: PrivatVehicleWithStats[],
  investments?: PrivatInvestmentWithStats[]
): AssetBreakdown[] {
  const totalAssets = netWorth.totalAssets || 1; // Avoid division by zero

  const breakdown: AssetBreakdown[] = [];

  // Properties
  const propertiesValue = netWorth.components.properties.value;
  if (propertiesValue > 0) {
    breakdown.push({
      category: 'properties',
      label: ASSET_LABELS.properties,
      value: propertiesValue,
      count: netWorth.components.properties.count,
      percentage: (propertiesValue / totalAssets) * 100,
      color: ASSET_COLORS.properties,
      items: (properties ?? []).map(p => ({
        id: p.id,
        name: p.name,
        value: p.currentValue ?? p.purchasePrice ?? 0,
      })),
    });
  }

  // Vehicles
  const vehiclesValue = netWorth.components.vehicles.value;
  if (vehiclesValue > 0) {
    breakdown.push({
      category: 'vehicles',
      label: ASSET_LABELS.vehicles,
      value: vehiclesValue,
      count: netWorth.components.vehicles.count,
      percentage: (vehiclesValue / totalAssets) * 100,
      color: ASSET_COLORS.vehicles,
      items: (vehicles ?? []).map(v => ({
        id: v.id,
        name: v.name,
        value: v.purchasePrice ?? 0,
      })),
    });
  }

  // Investments
  const investmentsValue = netWorth.components.investments.value;
  if (investmentsValue > 0) {
    breakdown.push({
      category: 'investments',
      label: ASSET_LABELS.investments,
      value: investmentsValue,
      count: netWorth.components.investments.count,
      percentage: (investmentsValue / totalAssets) * 100,
      color: ASSET_COLORS.investments,
      items: (investments ?? []).map(i => ({
        id: i.id,
        name: i.name,
        value: i.currentValue,
      })),
    });
  }

  return breakdown.sort((a, b) => b.value - a.value);
}

function buildLiabilityBreakdown(
  netWorth: NetWorthComponents,
  loans?: PrivatLoanWithStats[]
): LiabilityBreakdown[] {
  const totalLiabilities = netWorth.totalLiabilities || 1; // Avoid division by zero

  const breakdown: LiabilityBreakdown[] = [];

  // Group loans by type
  const loansByType = (loans ?? []).reduce((acc, loan) => {
    const type = loan.loanType === 'mortgage' ? 'mortgages' : 'loans';
    if (!acc[type]) {
      acc[type] = [];
    }
    acc[type].push(loan);
    return acc;
  }, {} as Record<string, PrivatLoanWithStats[]>);

  // Mortgages
  const mortgages = loansByType['mortgages'] ?? [];
  const mortgagesValue = mortgages.reduce((sum, l) => sum + l.currentBalance, 0);
  if (mortgagesValue > 0) {
    breakdown.push({
      category: 'mortgages',
      label: LIABILITY_LABELS.mortgages,
      value: mortgagesValue,
      count: mortgages.length,
      percentage: (mortgagesValue / totalLiabilities) * 100,
      color: LIABILITY_COLORS.mortgages,
      items: mortgages.map(l => ({
        id: l.id,
        name: l.name,
        outstanding: l.currentBalance,
        monthlyPayment: l.monthlyPayment,
      })),
    });
  }

  // Other Loans
  const otherLoans = loansByType['loans'] ?? [];
  const loansValue = otherLoans.reduce((sum, l) => sum + l.currentBalance, 0);
  if (loansValue > 0) {
    breakdown.push({
      category: 'loans',
      label: LIABILITY_LABELS.loans,
      value: loansValue,
      count: otherLoans.length,
      percentage: (loansValue / totalLiabilities) * 100,
      color: LIABILITY_COLORS.loans,
      items: otherLoans.map(l => ({
        id: l.id,
        name: l.name,
        outstanding: l.currentBalance,
        monthlyPayment: l.monthlyPayment,
      })),
    });
  }

  return breakdown.sort((a, b) => b.value - a.value);
}

function buildHistory(snapshots: privatApi.PortfolioSnapshot[]): NetWorthHistoryEntry[] {
  return snapshots
    .slice(0, 12)
    .reverse()
    .map(s => ({
      date: s.snapshotDate,
      totalAssets: s.totalAssets,
      totalLiabilities: s.totalLiabilities,
      netWorth: s.netWorth,
    }));
}

// ==================== Refresh Hook ====================

export function useRefreshNetWorth() {
  const queryClient = useQueryClient();

  return async (spaceId: string) => {
    await queryClient.invalidateQueries({ queryKey: netWorthQueryKeys.all });
    // Also trigger a new snapshot creation
    try {
      await privatApi.createPortfolioSnapshot(spaceId);
    } catch (error) {
      // Snapshot creation failed, but data is still refreshed
      logger.error('Fehler beim Erstellen des Snapshots:', error);
    }
  };
}

export default useNetWorth;
