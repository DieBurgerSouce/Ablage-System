import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { useCurrentCompanyId } from '@/context/CompanyContext';

// ==================== Types ====================

export interface KanbanItem {
  id: string;
  document_id: string;
  document_name: string | null;
  entity_name: string | null;
  amount: number | null;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  assigned_to: string | null;
  assigned_to_name: string | null;
  entered_stage_at: string;
  notes: string | null;
}

export interface KanbanStage {
  id: string;
  stage_key: string;
  stage_name: string;
  stage_order: number;
  color: string;
  icon: string | null;
  is_final: boolean;
  item_count: number;
  items: KanbanItem[];
}

export interface KanbanBoard {
  workflow_type: string;
  stages: KanbanStage[];
  total_items: number;
}

export interface StageStatistic {
  stage_key: string;
  stage_name: string;
  item_count: number;
  avg_time_in_stage_hours: number | null;
}

// ==================== Queries ====================

export function useKanbanBoard(workflowType: string) {
  // B10: Der Backend-Endpoint verlangt company_id als PFLICHT-Query-Parameter
  // (app/api/v1/kanban.py: `company_id: UUID = Query(...)`). Ohne ihn antwortet
  // FastAPI mit 422 und das Board laedt nie. company_id kommt - wie bei allen
  // company-scoped Calls im Frontend - aus dem aktiven Company-Context.
  const companyId = useCurrentCompanyId();
  return useQuery({
    queryKey: ['kanban', 'board', workflowType, companyId],
    queryFn: async (): Promise<KanbanBoard> => {
      const res = await apiClient.get(`/kanban/${workflowType}/board`, {
        params: { company_id: companyId },
      });
      return res.data;
    },
    enabled: !!companyId,
    refetchInterval: 30000, // Refresh every 30s
  });
}

export function useKanbanStatistics(workflowType: string) {
  const companyId = useCurrentCompanyId();
  return useQuery({
    queryKey: ['kanban', 'statistics', workflowType, companyId],
    queryFn: async (): Promise<StageStatistic[]> => {
      const res = await apiClient.get(`/kanban/${workflowType}/statistics`, {
        params: { company_id: companyId },
      });
      return res.data;
    },
    enabled: !!companyId,
  });
}

// ==================== Mutations ====================

export function useMoveItem() {
  const queryClient = useQueryClient();
  const companyId = useCurrentCompanyId();
  return useMutation({
    mutationFn: async ({ itemId, targetStageId }: { itemId: string; targetStageId: string }) => {
      const res = await apiClient.patch(
        `/kanban/items/${itemId}/move`,
        { target_stage_id: targetStageId },
        { params: { company_id: companyId } },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kanban'] });
    },
  });
}

export function useAddItem(workflowType: string) {
  const queryClient = useQueryClient();
  const companyId = useCurrentCompanyId();
  return useMutation({
    mutationFn: async (data: { document_id: string; priority?: string; assigned_to?: string }) => {
      const res = await apiClient.post(`/kanban/${workflowType}/items`, data, {
        params: { company_id: companyId },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kanban'] });
    },
  });
}
