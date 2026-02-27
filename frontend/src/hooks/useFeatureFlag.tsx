import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { QUERY_SEMI_STATIC } from '@/lib/api/query-config';

interface FeatureFlagResult {
  flag_key: string;
  enabled: boolean;
  variant: string | null;
  reason: string;
}

interface AllFlagsResult {
  [key: string]: {
    enabled: boolean;
    variant: string | null;
  };
}

/**
 * Hook für Feature-Flag Evaluation.
 *
 * @param key - Feature-Flag Key
 * @returns Feature-Flag Evaluation Result
 *
 * @example
 * const { isEnabled, variant } = useFeatureFlag('new_ocr_pipeline');
 * if (isEnabled) { ... }
 */
export function useFeatureFlag(key: string) {
  const query = useQuery<FeatureFlagResult>({
    queryKey: ['feature-flags', 'evaluate', key],
    queryFn: async () => {
      const response = await apiClient.get(`/feature-flags/evaluate/${key}`);
      return response.data;
    },
    ...QUERY_SEMI_STATIC, // 5min staleTime, 30min gcTime
    retry: 1,
  });

  return {
    isEnabled: query.data?.enabled ?? false,
    variant: query.data?.variant ?? null,
    isLoading: query.isLoading,
    error: query.error,
  };
}

/**
 * Hook für alle Feature-Flags auf einmal.
 */
export function useAllFeatureFlags() {
  const query = useQuery<AllFlagsResult>({
    queryKey: ['feature-flags', 'evaluate-all'],
    queryFn: async () => {
      const response = await apiClient.get('/feature-flags/evaluate-all');
      return response.data;
    },
    ...QUERY_SEMI_STATIC, // 5min staleTime, 30min gcTime
    retry: 1,
  });

  return {
    flags: query.data ?? {},
    isEnabled: (key: string) => query.data?.[key]?.enabled ?? false,
    getVariant: (key: string) => query.data?.[key]?.variant ?? null,
    isLoading: query.isLoading,
    error: query.error,
  };
}
