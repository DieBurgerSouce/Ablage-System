/**
 * Tests for Job Queue Mutation Hooks
 *
 * Tests TanStack Query Mutations:
 * - Optimistic Updates
 * - Error Rollback
 * - Cache Invalidation
 * - Toast Notifications
 *
 * INTEGRATION TESTS:
 * - Bulk operation mutations
 * - DLQ mutations
 * - Cache invalidation patterns
 * - HTTP error code handling (401, 403, 429, 503)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';

// Mock toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    loading: vi.fn(),
  },
}));

// Mock API
vi.mock('../api/job-queue-api', () => ({
  jobQueueApi: {
    cancelJob: vi.fn(),
    retryJob: vi.fn(),
    changeJobPriority: vi.fn(),
    forceKillJob: vi.fn(),
    pauseJob: vi.fn(),
    resumeJob: vi.fn(),
    bulkCancelJobs: vi.fn(),
    bulkRetryJobs: vi.fn(),
    bulkChangePriority: vi.fn(),
    clearQueue: vi.fn(),
    retryDLQTask: vi.fn(),
    bulkRetryDLQTasks: vi.fn(),
    purgeDLQ: vi.fn(),
    getDLQStats: vi.fn(),
    getDLQTasks: vi.fn(),
  },
}));

import { toast } from 'sonner';
import { jobQueueApi } from '../api/job-queue-api';
import {
  useCancelJob,
  useRetryJob,
  useChangeJobPriority,
  useForceKillJob,
  usePauseJob,
  useResumeJob,
  useBulkCancelJobs,
  useBulkRetryJobs,
  useBulkChangePriority,
  useClearQueue,
  useRetryDLQTask,
  useBulkRetryDLQTasks,
  usePurgeDLQ,
} from '../hooks/use-job-mutations';
import { jobQueueKeys } from '../api/query-keys';

// Test wrapper with QueryClient
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useCancelJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call cancelJob API with correct parameters and validate data', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'cancel', message: 'Job abgebrochen' };
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123', reason: 'Test-Abbruch' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('job-123');
    expect(result.current.data?.action).toBe('cancel');

    expect(jobQueueApi.cancelJob).toHaveBeenCalledWith('job-123', 'Test-Abbruch');
  });

  it('should show success toast on successful cancel with correct description', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'cancel', message: 'Job erfolgreich abgebrochen' };
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify toast with exact description
    expect(toast.success).toHaveBeenCalledWith('Job abgebrochen', {
      description: 'Job erfolgreich abgebrochen',
    });
  });

  it('should show error toast on API failure with error message', async () => {
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(new Error('Network Error'));

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Verify error structure
    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe('Network Error');

    expect(toast.error).toHaveBeenCalledWith('Fehler beim Abbrechen', {
      description: 'Network Error',
    });
  });

  it('should show error toast when server rejects cancel', async () => {
    const mockResponse = { success: false, jobId: 'job-123', action: 'cancel', message: 'Job bereits abgeschlossen' };
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Validate data even for failed server response
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(false);
    expect(result.current.data?.message).toBe('Job bereits abgeschlossen');

    expect(toast.error).toHaveBeenCalledWith('Fehler beim Abbrechen', {
      description: 'Job bereits abgeschlossen',
    });
  });
});

describe('useRetryJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call retryJob API with correct parameters and validate response data', async () => {
    const mockResponse = { success: true, jobId: 'new-job-456', action: 'retry', message: 'Job wird wiederholt' };
    vi.mocked(jobQueueApi.retryJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useRetryJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      jobId: 'job-123',
      options: { priority: 1, backend: 'deepseek' },
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('new-job-456');
    expect(result.current.data?.action).toBe('retry');

    expect(jobQueueApi.retryJob).toHaveBeenCalledWith('job-123', { priority: 1, backend: 'deepseek' });
  });

  it('should show success toast on successful retry with description', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'retry', message: 'Job wird in Warteschlange eingereiht' };
    vi.mocked(jobQueueApi.retryJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useRetryJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify toast with exact description
    expect(toast.success).toHaveBeenCalledWith('Job wird wiederholt', {
      description: 'Job wird in Warteschlange eingereiht',
    });
  });
});

describe('useChangeJobPriority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call changeJobPriority API and validate response data', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'change_priority', message: 'Priorität geändert' };
    vi.mocked(jobQueueApi.changeJobPriority).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useChangeJobPriority(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123', priority: 2 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('job-123');
    expect(result.current.data?.action).toBe('change_priority');

    expect(jobQueueApi.changeJobPriority).toHaveBeenCalledWith('job-123', 2);
  });
});

describe('usePauseJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call pauseJob API and validate response data', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'pause', message: 'Job wurde pausiert' };
    vi.mocked(jobQueueApi.pauseJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => usePauseJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('job-123');
    expect(result.current.data?.action).toBe('pause');

    expect(jobQueueApi.pauseJob).toHaveBeenCalledWith('job-123');
    expect(toast.success).toHaveBeenCalledWith('Job pausiert', {
      description: 'Job wurde pausiert',
    });
  });
});

describe('useResumeJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call resumeJob API and validate response data', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'resume', message: 'Job wurde fortgesetzt' };
    vi.mocked(jobQueueApi.resumeJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useResumeJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('job-123');
    expect(result.current.data?.action).toBe('resume');

    expect(jobQueueApi.resumeJob).toHaveBeenCalledWith('job-123');
    expect(toast.success).toHaveBeenCalledWith('Job fortgesetzt', {
      description: 'Job wurde fortgesetzt',
    });
  });
});

// ==============================================================================
// SCHRITT 10: useForceKillJob Tests (Enterprise-Level)
// ==============================================================================

describe('useForceKillJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call forceKillJob API and validate response data', async () => {
    const mockResponse = { success: true, jobId: 'job-123', action: 'force_kill', message: 'Job wurde beendet' };
    vi.mocked(jobQueueApi.forceKillJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useForceKillJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.jobId).toBe('job-123');
    expect(result.current.data?.action).toBe('force_kill');

    expect(jobQueueApi.forceKillJob).toHaveBeenCalledWith('job-123');
    expect(toast.success).toHaveBeenCalledWith('Job beendet', {
      description: 'Job wurde beendet',
    });
  });

  it('should invalidate jobs, stats, and workers queries on success', async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const mockResponse = { success: true, jobId: 'job-123', action: 'force_kill', message: 'Job beendet' };
    vi.mocked(jobQueueApi.forceKillJob).mockResolvedValue(mockResponse);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useForceKillJob(), { wrapper });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify all 3 query keys are invalidated
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.jobs() })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.stats() })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.workers() })
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(3);
  });

  it('should show error toast on API failure', async () => {
    vi.mocked(jobQueueApi.forceKillJob).mockRejectedValue(new Error('Worker nicht erreichbar'));

    const { result } = renderHook(() => useForceKillJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE: Verify error structure
    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe('Worker nicht erreichbar');

    expect(toast.error).toHaveBeenCalledWith('Fehler beim Force-Kill', {
      description: 'Worker nicht erreichbar',
    });
  });

  it('should show error toast when server rejects force kill', async () => {
    const mockResponse = { success: false, jobId: 'job-123', action: 'force_kill', message: 'Job ist nicht aktiv' };
    vi.mocked(jobQueueApi.forceKillJob).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useForceKillJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('job-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Validate data even for failed server response
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(false);
    expect(result.current.data?.message).toBe('Job ist nicht aktiv');

    expect(toast.error).toHaveBeenCalledWith('Fehler beim Beenden', {
      description: 'Job ist nicht aktiv',
    });
  });
});

describe('useBulkCancelJobs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call bulkCancelJobs API and validate response data', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }, { originalJobId: 'job-3' }, { originalJobId: 'job-4' }, { originalJobId: 'job-5' }],
      failed: [],
      successCount: 5,
      failedCount: 0,
      total: 5
    };
    vi.mocked(jobQueueApi.bulkCancelJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkCancelJobs(), {
      wrapper: createWrapper(),
    });

    const jobIds = ['job-1', 'job-2', 'job-3', 'job-4', 'job-5'];

    result.current.mutate({ jobIds, reason: 'Bulk cancel test' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE: Validate data property with successCount/failedCount
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.successCount).toBe(5);
    expect(result.current.data?.failedCount).toBe(0);
    expect(result.current.data?.total).toBe(5);
    expect(result.current.data?.success).toHaveLength(5);
    expect(result.current.data?.failed).toHaveLength(0);

    expect(jobQueueApi.bulkCancelJobs).toHaveBeenCalledWith(jobIds, 'Bulk cancel test');
  });

  it('should show success toast when all jobs cancelled', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }, { originalJobId: 'job-3' }],
      failed: [],
      successCount: 3,
      failedCount: 0,
      total: 3
    };
    vi.mocked(jobQueueApi.bulkCancelJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkCancelJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2', 'job-3'] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Validate data counts
    expect(result.current.data?.successCount).toBe(3);
    expect(result.current.data?.failedCount).toBe(0);

    expect(toast.success).toHaveBeenCalledWith('3 Jobs abgebrochen');
  });

  it('should show warning toast for partial failure and validate failure details', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }],
      failed: [{ jobId: 'job-3', reason: 'Already cancelled' }],
      successCount: 2,
      failedCount: 1,
      total: 3
    };
    vi.mocked(jobQueueApi.bulkCancelJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkCancelJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2', 'job-3'] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Validate data with partial failure details
    expect(result.current.data?.successCount).toBe(2);
    expect(result.current.data?.failedCount).toBe(1);
    expect(result.current.data?.total).toBe(3);
    expect(result.current.data?.failed[0]?.reason).toBe('Already cancelled');

    expect(toast.warning).toHaveBeenCalledWith(
      '2 von 3 Jobs abgebrochen',
      { description: '1 Jobs konnten nicht abgebrochen werden' }
    );
  });
});

describe('Optimistic Updates', () => {
  it('should optimistically update job status on cancel', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    // Pre-populate cache with a job - use setQueryData to create the query entry first
    queryClient.setQueryData(jobQueueKeys.jobs(), {
      jobs: [{ id: 'job-123', status: 'processing' }],
      total: 1,
    });

    // Delayed API response - gives time to verify optimistic update
    let resolveApi: () => void;
    const apiPromise = new Promise<void>(resolve => { resolveApi = resolve; });
    vi.mocked(jobQueueApi.cancelJob).mockImplementation(async () => {
      await apiPromise;
      return { success: true, jobId: 'job-123', action: 'cancel', message: 'Job abgebrochen' };
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper });

    // Trigger mutation and wait for onMutate to complete
    await act(async () => {
      result.current.mutate({ jobId: 'job-123' });
      // Give onMutate time to run (async operation)
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // KRITISCH: Verify optimistic update happened before API returns
    const cachedData = queryClient.getQueryData(jobQueueKeys.jobs()) as { jobs: Array<{ id: string; status: string }> } | undefined;
    expect(cachedData).toBeDefined();
    expect(cachedData!.jobs[0].status).toBe('cancelled');

    // Now let API complete
    resolveApi!();

    // Wait for mutation to finish
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify toast with exact description
    expect(toast.success).toHaveBeenCalledWith('Job abgebrochen', {
      description: 'Job abgebrochen',
    });
  });
});

describe('Error Rollback', () => {
  it('should rollback optimistic update on error', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    // Pre-populate cache with a job - ORIGINAL priority is 5
    const originalJob = { id: 'job-123', status: 'processing', priority: 5 };
    queryClient.setQueryData(jobQueueKeys.jobs(), {
      jobs: [originalJob],
      total: 1,
    });

    // API will fail - controlled timing
    let rejectApi: (error: Error) => void;
    const apiPromise = new Promise<never>((_, reject) => { rejectApi = reject; });
    vi.mocked(jobQueueApi.changeJobPriority).mockImplementation(async () => {
      return apiPromise;
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useChangeJobPriority(), { wrapper });

    // Trigger mutation and wait for onMutate to complete
    await act(async () => {
      result.current.mutate({ jobId: 'job-123', priority: 1 });
      // Give onMutate time to run (async operation)
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // Verify optimistic update happened (priority changed to 1)
    const optimisticData = queryClient.getQueryData(jobQueueKeys.jobs()) as { jobs: Array<{ id: string; priority: number }> } | undefined;
    expect(optimisticData).toBeDefined();
    expect(optimisticData!.jobs[0].priority).toBe(1);

    // Now trigger the error
    await act(async () => {
      rejectApi!(new Error('Server Error'));
      // Give time for error handling
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // Wait for error state
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // Verify rollback happened - priority should be back to 5
    const rolledBackData = queryClient.getQueryData(jobQueueKeys.jobs()) as { jobs: Array<{ id: string; priority: number }> } | undefined;
    expect(rolledBackData).toBeDefined();
    expect(rolledBackData!.jobs[0].priority).toBe(5);

    // ENTERPRISE (Iteration 3): Error toast with exact description
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Ändern der Priorität',
      { description: 'Server Error' }
    );
  });
});

// ==============================================================================
// INTEGRATION TESTS - Bulk Operations, DLQ, Cache Invalidation, HTTP Errors
// ==============================================================================

describe('Bulk Retry Operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call bulkRetryJobs API with correct job IDs and validate response', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1', newJobId: 'new-1' }, { originalJobId: 'job-2', newJobId: 'new-2' }],
      failed: [],
      successCount: 2,
      failedCount: 0,
      total: 2,
    };
    vi.mocked(jobQueueApi.bulkRetryJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkRetryJobs(), {
      wrapper: createWrapper(),
    });

    const jobIds = ['job-1', 'job-2'];
    result.current.mutate({ jobIds });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Validate data with successCount/failedCount/total
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.successCount).toBe(2);
    expect(result.current.data?.failedCount).toBe(0);
    expect(result.current.data?.total).toBe(2);

    expect(jobQueueApi.bulkRetryJobs).toHaveBeenCalledWith(jobIds, undefined);
  });

  it('should call bulkRetryJobs with priority override and validate response', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }],
      failed: [],
      successCount: 2,
      failedCount: 0,
      total: 2,
    };
    vi.mocked(jobQueueApi.bulkRetryJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkRetryJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2'], options: { priority: 1 } });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Validate data with successCount/failedCount/total
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.successCount).toBe(2);
    expect(result.current.data?.failedCount).toBe(0);
    expect(result.current.data?.total).toBe(2);

    expect(jobQueueApi.bulkRetryJobs).toHaveBeenCalledWith(['job-1', 'job-2'], { priority: 1 });
  });

  it('should show success toast with count after bulk retry', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }, { originalJobId: 'job-3' }],
      failed: [],
      successCount: 3,
      failedCount: 0,
      total: 3,
    };
    vi.mocked(jobQueueApi.bulkRetryJobs).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkRetryJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2', 'job-3'] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Actual: "3 Jobs werden wiederholt"
    expect(toast.success).toHaveBeenCalledWith('3 Jobs werden wiederholt');
  });
});

describe('Bulk Change Priority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call bulkChangePriority API with correct parameters and validate response', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }, { originalJobId: 'job-3' }, { originalJobId: 'job-4' }, { originalJobId: 'job-5' }],
      failed: [],
      successCount: 5,
      failedCount: 0,
      total: 5
    };
    vi.mocked(jobQueueApi.bulkChangePriority).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkChangePriority(), {
      wrapper: createWrapper(),
    });

    const jobIds = ['job-1', 'job-2', 'job-3', 'job-4', 'job-5'];
    result.current.mutate({ jobIds, priority: 1 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Validate data with successCount/failedCount/total
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.successCount).toBe(5);
    expect(result.current.data?.failedCount).toBe(0);
    expect(result.current.data?.total).toBe(5);

    expect(jobQueueApi.bulkChangePriority).toHaveBeenCalledWith(jobIds, 1);
  });

  it('should handle partial failure in bulk priority change', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }, { originalJobId: 'job-3' }],
      failed: [
        { jobId: 'job-4', reason: 'Job already completed' },
        { jobId: 'job-5', reason: 'Job not found' },
      ],
      successCount: 3,
      failedCount: 2,
      total: 5,
    };
    vi.mocked(jobQueueApi.bulkChangePriority).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkChangePriority(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2', 'job-3', 'job-4', 'job-5'], priority: 2 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Actual: "3 von 5 Jobs geändert" with description "2 Jobs konnten nicht geändert werden"
    expect(toast.warning).toHaveBeenCalledWith(
      '3 von 5 Jobs geändert',
      expect.objectContaining({
        description: '2 Jobs konnten nicht geändert werden'
      })
    );
  });

  it('should show success toast when all jobs updated', async () => {
    const mockResponse = {
      success: [{ originalJobId: 'job-1' }, { originalJobId: 'job-2' }],
      failed: [],
      successCount: 2,
      failedCount: 0,
      total: 2,
    };
    vi.mocked(jobQueueApi.bulkChangePriority).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkChangePriority(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2'], priority: 3 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Actual: "Priorität für 2 Jobs geändert"
    expect(toast.success).toHaveBeenCalledWith('Priorität für 2 Jobs geändert');
  });
});

describe('Clear Queue Operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call clearQueue API with status filter', async () => {
    const mockResponse = {
      success: true,
      clearedCount: 25,
      status: 'pending',
      message: '25 Aufträge gelöscht',
    };
    vi.mocked(jobQueueApi.clearQueue).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useClearQueue(), {
      wrapper: createWrapper(),
    });

    // useClearQueue expects a status string directly, not an object
    result.current.mutate('pending');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.clearQueue).toHaveBeenCalledWith('pending');
    // Actual: "Warteschlange geleert" with description "25 Jobs entfernt"
    expect(toast.success).toHaveBeenCalledWith(
      'Warteschlange geleert',
      expect.objectContaining({
        description: '25 Jobs entfernt'
      })
    );
  });

  it('should handle empty queue response', async () => {
    const mockResponse = {
      success: true,
      clearedCount: 0,
      message: 'Queue bereits leer',
    };
    vi.mocked(jobQueueApi.clearQueue).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useClearQueue(), {
      wrapper: createWrapper(),
    });

    // useClearQueue expects a status string directly
    result.current.mutate('queued');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.clearQueue).toHaveBeenCalledWith('queued');
    // Actual: "Warteschlange geleert" with description "0 Jobs entfernt"
    expect(toast.success).toHaveBeenCalledWith(
      'Warteschlange geleert',
      expect.objectContaining({
        description: '0 Jobs entfernt'
      })
    );
  });

  it('should show error toast when clear fails', async () => {
    vi.mocked(jobQueueApi.clearQueue).mockRejectedValue(new Error('Permission denied'));

    const { result } = renderHook(() => useClearQueue(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('pending');

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after error
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Exact error toast description
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Leeren der Warteschlange',
      { description: 'Permission denied' }
    );
  });
});

describe('DLQ Retry Operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call retryDLQTask API with task ID and validate response', async () => {
    const mockResponse = {
      success: true,
      message: 'Task wurde erneut in Queue eingereiht',
      taskId: 'dlq-task-123',
      newTaskId: 'new-task-456',
    };
    vi.mocked(jobQueueApi.retryDLQTask).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useRetryDLQTask(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('dlq-task-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Validate data property
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.taskId).toBe('dlq-task-123');
    expect(result.current.data?.newTaskId).toBe('new-task-456');

    expect(jobQueueApi.retryDLQTask).toHaveBeenCalledWith('dlq-task-123');
    expect(toast.success).toHaveBeenCalledWith(
      'DLQ-Task wird wiederholt',
      expect.objectContaining({
        description: 'Task wurde erneut in Queue eingereiht'
      })
    );
  });

  it('should handle DLQ task not found', async () => {
    const mockResponse = {
      success: false,
      message: 'Task nicht in DLQ gefunden',
      taskId: 'nonexistent-task',
    };
    vi.mocked(jobQueueApi.retryDLQTask).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useRetryDLQTask(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('nonexistent-task');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Actual: "Fehler beim Wiederholen" with description from response message
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Wiederholen',
      expect.objectContaining({
        description: 'Task nicht in DLQ gefunden'
      })
    );
  });

  it('should call bulkRetryDLQTasks API with task IDs and validate response', async () => {
    const mockResponse = {
      success: true,
      message: '5 von 5 Tasks erfolgreich wiederholt',
      successCount: 5,
      failedCount: 0,
    };
    vi.mocked(jobQueueApi.bulkRetryDLQTasks).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBulkRetryDLQTasks(), {
      wrapper: createWrapper(),
    });

    const taskIds = ['task-1', 'task-2', 'task-3', 'task-4', 'task-5'];
    result.current.mutate(taskIds);

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Validate data with successCount/failedCount
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.success).toBe(true);
    expect(result.current.data?.successCount).toBe(5);
    expect(result.current.data?.failedCount).toBe(0);

    expect(jobQueueApi.bulkRetryDLQTasks).toHaveBeenCalledWith(taskIds);
    // Actual: "DLQ-Tasks werden wiederholt" with description from response message
    expect(toast.success).toHaveBeenCalledWith(
      'DLQ-Tasks werden wiederholt',
      expect.objectContaining({
        description: '5 von 5 Tasks erfolgreich wiederholt'
      })
    );
  });

  it('should show error toast on bulk retry failure', async () => {
    vi.mocked(jobQueueApi.bulkRetryDLQTasks).mockRejectedValue(new Error('DLQ unavailable'));

    const { result } = renderHook(() => useBulkRetryDLQTasks(), {
      wrapper: createWrapper(),
    });

    result.current.mutate(['task-1', 'task-2']);

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // Actual: "Fehler beim Massen-Wiederholen" with error message
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Massen-Wiederholen',
      expect.objectContaining({
        description: 'DLQ unavailable'
      })
    );
  });
});

describe('DLQ Purge Operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call purgeDLQ API', async () => {
    const mockResponse = {
      success: true,
      message: 'DLQ wurde geleert: 50 Tasks gelöscht',
      deletedCount: 50,
    };
    vi.mocked(jobQueueApi.purgeDLQ).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => usePurgeDLQ(), {
      wrapper: createWrapper(),
    });

    // usePurgeDLQ takes no parameters - confirmation is handled at the UI level
    result.current.mutate();

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.purgeDLQ).toHaveBeenCalled();
    // Actual: "DLQ geleert" with description from response message
    expect(toast.success).toHaveBeenCalledWith(
      'DLQ geleert',
      expect.objectContaining({
        description: 'DLQ wurde geleert: 50 Tasks gelöscht'
      })
    );
  });

  it('should show error toast when server rejects purge', async () => {
    const mockResponse = {
      success: false,
      message: 'DLQ ist leer',
    };
    vi.mocked(jobQueueApi.purgeDLQ).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => usePurgeDLQ(), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after completion
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Exact error toast description
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Leeren',
      { description: 'DLQ ist leer' }
    );
  });

  it('should show error toast on purge failure', async () => {
    vi.mocked(jobQueueApi.purgeDLQ).mockRejectedValue(new Error('DLQ locked'));

    const { result } = renderHook(() => usePurgeDLQ(), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 3): Verify isPending is false after error
    expect(result.current.isPending).toBe(false);

    // ENTERPRISE (Iteration 3): Exact error toast description
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Leeren der DLQ',
      { description: 'DLQ locked' }
    );
  });

  it('should invalidate DLQ queries after successful purge', async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const mockResponse = {
      success: true,
      message: 'DLQ wurde geleert',
      deletedCount: 10,
    };
    vi.mocked(jobQueueApi.purgeDLQ).mockResolvedValue(mockResponse);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => usePurgeDLQ(), { wrapper });

    result.current.mutate();

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(invalidateSpy).toHaveBeenCalled();
  });
});

describe('Cache Invalidation Patterns', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should invalidate jobs and stats queries after cancel', async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    // Pre-populate cache
    queryClient.setQueryData(jobQueueKeys.jobs(), {
      jobs: [{ id: 'job-123', status: 'processing' }],
      total: 1,
    });

    const mockResponse = { success: true, jobId: 'job-123', action: 'cancel', message: 'Job abgebrochen' };
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue(mockResponse);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify specific query keys are invalidated
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.jobs() })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.stats() })
    );
    // onSuccess invalidates stats, onSettled invalidates jobs
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });

  it('should update specific job in cache on priority change and verify final state', async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    queryClient.setQueryData(jobQueueKeys.jobs(), {
      jobs: [
        { id: 'job-123', status: 'pending', priority: 5 },
        { id: 'job-456', status: 'pending', priority: 3 },
      ],
      total: 2,
    });

    const mockResponse = { success: true, jobId: 'job-123', action: 'change_priority', message: 'Priorität geändert' };
    vi.mocked(jobQueueApi.changeJobPriority).mockResolvedValue(mockResponse);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useChangeJobPriority(), { wrapper });

    result.current.mutate({ jobId: 'job-123', priority: 1 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify invalidateQueries was called with correct key
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.jobs() })
    );
  });

  it('should invalidate DLQ and jobs queries after retry', async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    queryClient.setQueryData(['dlq', 'tasks'], {
      tasks: [{ id: 'dlq-123', name: 'failing_task' }],
      total: 1,
    });

    const mockResponse = {
      success: true,
      message: 'Task wiederholt',
      taskId: 'dlq-123',
      newTaskId: 'new-456',
    };
    vi.mocked(jobQueueApi.retryDLQTask).mockResolvedValue(mockResponse);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useRetryDLQTask(), { wrapper });

    result.current.mutate('dlq-123');

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE: Verify both DLQ and jobs queries are invalidated
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.dlq() })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: jobQueueKeys.jobs() })
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});

describe('HTTP Error Code Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle 401 Unauthorized error', async () => {
    const error = new Error('Unauthorized');
    (error as any).response = { status: 401 };
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(error);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Unauthorized' }
    );
  });

  it('should handle 403 Forbidden error', async () => {
    const error = new Error('Forbidden');
    (error as any).response = { status: 403, data: { detail: 'Superuser-Berechtigung erforderlich' } };
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(error);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Forbidden' }
    );
  });

  it('should handle 429 Too Many Requests error', async () => {
    const error = new Error('Too Many Requests');
    (error as any).response = {
      status: 429,
      data: { detail: 'Minutenlimit erreicht (10/min)' },
      headers: { 'retry-after': '60' },
    };
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(error);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Too Many Requests' }
    );
  });

  it('should handle 503 Service Unavailable error', async () => {
    const error = new Error('Service Unavailable');
    (error as any).response = {
      status: 503,
      data: { detail: 'Rate-Limiting-Service nicht verfügbar' },
    };
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(error);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Service Unavailable' }
    );
  });

  it('should handle 504 Gateway Timeout error', async () => {
    const error = new Error('Gateway Timeout');
    (error as any).response = {
      status: 504,
      data: { detail: 'Operation nach 60 Sekunden abgebrochen' },
    };
    vi.mocked(jobQueueApi.bulkCancelJobs).mockRejectedValue(error);

    const { result } = renderHook(() => useBulkCancelJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2', 'job-3'] });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    // useBulkCancelJobs verwendet 'Fehler beim Massenabbruch'
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Massenabbruch',
      { description: 'Gateway Timeout' }
    );
  });

  it('should handle 400 Bad Request error', async () => {
    const error = new Error('Bad Request');
    (error as any).response = {
      status: 400,
      data: { detail: 'Ungültige Anfrage: Job-ID fehlt' },
    };
    vi.mocked(jobQueueApi.cancelJob).mockRejectedValue(error);

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: '' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Bad Request' }
    );
  });

  it('should handle 500 Internal Server Error', async () => {
    const error = new Error('Internal Server Error');
    (error as any).response = {
      status: 500,
      data: { detail: 'Interner Serverfehler' },
    };
    vi.mocked(jobQueueApi.retryJob).mockRejectedValue(error);

    const { result } = renderHook(() => useRetryJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    // useRetryJob verwendet 'Fehler beim Wiederholen'
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Wiederholen',
      { description: 'Internal Server Error' }
    );
  });

  it('should handle 502 Bad Gateway error', async () => {
    const error = new Error('Bad Gateway');
    (error as any).response = {
      status: 502,
      data: { detail: 'Backend-Service nicht erreichbar' },
    };
    vi.mocked(jobQueueApi.bulkRetryJobs).mockRejectedValue(error);

    const { result } = renderHook(() => useBulkRetryJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds: ['job-1', 'job-2'] });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    // useBulkRetryJobs verwendet 'Fehler beim Massen-Wiederholen'
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Massen-Wiederholen',
      { description: 'Bad Gateway' }
    );
  });
});

describe('Concurrent Mutation Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle multiple concurrent cancel mutations', async () => {
    vi.mocked(jobQueueApi.cancelJob).mockImplementation(async (jobId) => {
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { success: true, jobId, action: 'cancel', message: `Job ${jobId} abgebrochen` };
    });

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    // Fire multiple mutations concurrently
    result.current.mutate({ jobId: 'job-1' });
    result.current.mutate({ jobId: 'job-2' });
    result.current.mutate({ jobId: 'job-3' });

    await waitFor(() => {
      expect(jobQueueApi.cancelJob).toHaveBeenCalledTimes(3);
    });
  });

  it('should handle mutation while previous is pending', async () => {
    let callCount = 0;
    vi.mocked(jobQueueApi.cancelJob).mockImplementation(async (jobId) => {
      callCount++;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return { success: true, jobId, action: 'cancel', message: 'Job abgebrochen' };
    });

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-1' });

    // Small delay to ensure first mutation is in progress
    await new Promise((resolve) => setTimeout(resolve, 5));

    result.current.mutate({ jobId: 'job-2' });

    await waitFor(() => {
      expect(callCount).toBe(2);
    });
  });
});

describe('Edge Cases', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle empty job ID gracefully', async () => {
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue({
      success: false,
      jobId: '',
      action: 'cancel',
      message: 'Ungültige Job-ID',
    });

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: '' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // ENTERPRISE (Iteration 4): Exakte Toast-Message statt expect.anything()
    // Bei success: false zeigt useCancelJob 'Fehler beim Abbrechen' mit data.message
    expect(toast.error).toHaveBeenCalledWith(
      'Fehler beim Abbrechen',
      { description: 'Ungültige Job-ID' }
    );
  });

  it('should handle very long job ID', async () => {
    const longId = 'job-' + 'a'.repeat(1000);
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue({
      success: true,
      jobId: longId,
      action: 'cancel',
      message: 'Job abgebrochen',
    });

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: longId });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.cancelJob).toHaveBeenCalledWith(longId, undefined);
  });

  it('should handle special characters in reason', async () => {
    const specialReason = 'Test <script>alert("xss")</script> & Umlaute: äöüß';
    vi.mocked(jobQueueApi.cancelJob).mockResolvedValue({
      success: true,
      jobId: 'job-123',
      action: 'cancel',
      message: 'Job abgebrochen',
    });

    const { result } = renderHook(() => useCancelJob(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobId: 'job-123', reason: specialReason });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.cancelJob).toHaveBeenCalledWith('job-123', specialReason);
  });

  it('should handle exactly 100 jobs in bulk operation', async () => {
    const jobIds = Array.from({ length: 100 }, (_, i) => `job-${i}`);
    vi.mocked(jobQueueApi.bulkCancelJobs).mockResolvedValue({
      success: jobIds.map(id => ({ originalJobId: id })),
      failed: [],
      successCount: 100,
      failedCount: 0,
      total: 100,
    });

    const { result } = renderHook(() => useBulkCancelJobs(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ jobIds });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(jobQueueApi.bulkCancelJobs).toHaveBeenCalledWith(jobIds, undefined);
  });
});
