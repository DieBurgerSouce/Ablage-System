/**
 * Inventory Hooks - Lagerverwaltung und Wareneingang
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  description?: string;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  city?: string;
  country: string;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
}

export interface WarehouseCreate {
  code: string;
  name: string;
  description?: string;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  is_default?: boolean;
}

export interface InventoryItem {
  id: string;
  item_number: string;
  name: string;
  unit: string;
  description?: string;
  category?: string;
  ean?: string;
  manufacturer_part_number?: string;
  purchase_price?: number;
  sales_price?: number;
  min_stock_level?: number;
  reorder_point?: number;
  reorder_quantity?: number;
  default_supplier_id?: string;
  is_active: boolean;
  created_at: string;
}

export interface ItemCreate {
  item_number: string;
  name: string;
  unit?: string;
  description?: string;
  category?: string;
  ean?: string;
  manufacturer_part_number?: string;
  purchase_price?: number;
  sales_price?: number;
  min_stock_level?: number;
  reorder_point?: number;
  reorder_quantity?: number;
  default_supplier_id?: string;
}

export interface StockLevel {
  warehouse_id: string;
  warehouse_name: string;
  warehouse_code: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  quantity_on_order: number;
}

export interface WarehouseInventory {
  item_id: string;
  item_number: string;
  item_name: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
}

export interface StockValue {
  total_value: number;
  total_items: number;
  by_category: Record<string, number>;
}

export type MovementType =
  | 'goods_receipt'
  | 'goods_issue'
  | 'transfer'
  | 'adjustment_plus'
  | 'adjustment_minus'
  | 'return_inbound'
  | 'return_outbound'
  | 'scrapping';

export interface InventoryMovement {
  id: string;
  item_id: string;
  warehouse_id: string;
  target_warehouse_id?: string;
  movement_type: MovementType;
  status: string;
  quantity: number;
  unit_price?: number;
  total_value?: number;
  document_id?: string;
  reference_number?: string;
  entity_id?: string;
  notes?: string;
  movement_date: string;
  created_at: string;
}

export interface MovementCreate {
  item_id: string;
  warehouse_id: string;
  movement_type: MovementType;
  quantity: number;
  target_warehouse_id?: string;
  reference_number?: string;
  entity_id?: string;
  unit_price?: number;
  notes?: string;
}

export interface GoodsReceiptLine {
  id: string;
  line_number: number;
  item_id?: string;
  item_number_extracted?: string;
  description?: string;
  quantity_expected?: number;
  quantity_received: number;
  unit: string;
  is_matched: boolean;
  match_confidence?: number;
}

export interface GoodsReceipt {
  id: string;
  delivery_note_id: string;
  warehouse_id: string;
  supplier_id?: string;
  delivery_note_number?: string;
  purchase_order_number?: string;
  receipt_date: string;
  is_processed: boolean;
  processed_at?: string;
  notes?: string;
  lines: GoodsReceiptLine[];
  created_at: string;
}

export interface GoodsReceiptCreate {
  document_id: string;
  warehouse_id: string;
  receipt_date?: string;
  notes?: string;
}

export interface UnprocessedDeliveryNote {
  id: string;
  filename: string;
  document_type?: string;
  entity_id?: string;
  created_at: string;
  extracted_data?: Record<string, unknown>;
}

export interface LowStockItem {
  item: InventoryItem;
  quantity_on_hand: number;
  reorder_point: number;
  shortage: number;
  warehouse_id: string;
}

// ============================================================================
// Query Keys
// ============================================================================

export const inventoryKeys = {
  all: ['inventory'] as const,
  warehouses: () => [...inventoryKeys.all, 'warehouses'] as const,
  warehouse: (id: string) => [...inventoryKeys.warehouses(), id] as const,
  items: () => [...inventoryKeys.all, 'items'] as const,
  item: (id: string) => [...inventoryKeys.items(), id] as const,
  itemSearch: (params: Record<string, unknown>) => [...inventoryKeys.items(), 'search', params] as const,
  categories: () => [...inventoryKeys.items(), 'categories'] as const,
  lowStock: (warehouseId?: string) => [...inventoryKeys.items(), 'low-stock', warehouseId] as const,
  stock: (itemId: string) => [...inventoryKeys.all, 'stock', itemId] as const,
  warehouseStock: (warehouseId: string) => [...inventoryKeys.all, 'warehouse-stock', warehouseId] as const,
  stockValue: (warehouseId?: string) => [...inventoryKeys.all, 'stock-value', warehouseId] as const,
  movements: (params: Record<string, unknown>) => [...inventoryKeys.all, 'movements', params] as const,
  goodsReceipts: () => [...inventoryKeys.all, 'goods-receipts'] as const,
  goodsReceipt: (id: string) => [...inventoryKeys.goodsReceipts(), id] as const,
  unprocessedDeliveryNotes: () => [...inventoryKeys.all, 'unprocessed-delivery-notes'] as const,
  statistics: () => [...inventoryKeys.all, 'statistics'] as const,
};

// ============================================================================
// Warehouse Hooks
// ============================================================================

export function useWarehouses(includeInactive = false) {
  return useQuery({
    queryKey: inventoryKeys.warehouses(),
    queryFn: async () => {
      const { data } = await api.get<Warehouse[]>('/inventory/warehouses', {
        params: { include_inactive: includeInactive },
      });
      return data;
    },
  });
}

export function useWarehouse(warehouseId: string) {
  return useQuery({
    queryKey: inventoryKeys.warehouse(warehouseId),
    queryFn: async () => {
      const { data } = await api.get<Warehouse>(`/inventory/warehouses/${warehouseId}`);
      return data;
    },
    enabled: !!warehouseId,
  });
}

export function useDefaultWarehouse() {
  return useQuery({
    queryKey: [...inventoryKeys.warehouses(), 'default'],
    queryFn: async () => {
      const { data } = await api.get<Warehouse | null>('/inventory/warehouses/default');
      return data;
    },
  });
}

export function useCreateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (warehouse: WarehouseCreate) => {
      const { data } = await api.post<Warehouse>('/inventory/warehouses', warehouse);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouses() });
    },
  });
}

export function useUpdateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<WarehouseCreate> & { id: string }) => {
      const { data: warehouse } = await api.patch<Warehouse>(`/inventory/warehouses/${id}`, data);
      return warehouse;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouses() });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouse(variables.id) });
    },
  });
}

export function useDeleteWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/inventory/warehouses/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouses() });
    },
  });
}

// ============================================================================
// Item Hooks
// ============================================================================

export function useInventoryItems(params: {
  q?: string;
  category?: string;
  include_inactive?: boolean;
  limit?: number;
  offset?: number;
} = {}) {
  return useQuery({
    queryKey: inventoryKeys.itemSearch(params),
    queryFn: async () => {
      const { data } = await api.get<{ items: InventoryItem[]; total: number }>('/inventory/items', {
        params,
      });
      return data;
    },
  });
}

export function useInventoryItem(itemId: string) {
  return useQuery({
    queryKey: inventoryKeys.item(itemId),
    queryFn: async () => {
      const { data } = await api.get<InventoryItem>(`/inventory/items/${itemId}`);
      return data;
    },
    enabled: !!itemId,
  });
}

export function useItemCategories() {
  return useQuery({
    queryKey: inventoryKeys.categories(),
    queryFn: async () => {
      const { data } = await api.get<string[]>('/inventory/items/categories');
      return data;
    },
  });
}

export function useLowStockItems(warehouseId?: string) {
  return useQuery({
    queryKey: inventoryKeys.lowStock(warehouseId),
    queryFn: async () => {
      const { data } = await api.get<LowStockItem[]>('/inventory/items/low-stock', {
        params: warehouseId ? { warehouse_id: warehouseId } : {},
      });
      return data;
    },
  });
}

export function useCreateItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (item: ItemCreate) => {
      const { data } = await api.post<InventoryItem>('/inventory/items', item);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.items() });
    },
  });
}

export function useUpdateItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<ItemCreate> & { id: string }) => {
      const { data: item } = await api.patch<InventoryItem>(`/inventory/items/${id}`, data);
      return item;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.items() });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.item(variables.id) });
    },
  });
}

export function useDeleteItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/inventory/items/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.items() });
    },
  });
}

// ============================================================================
// Stock Hooks
// ============================================================================

export function useItemStock(itemId: string) {
  return useQuery({
    queryKey: inventoryKeys.stock(itemId),
    queryFn: async () => {
      const { data } = await api.get<StockLevel[]>(`/inventory/stock/${itemId}`);
      return data;
    },
    enabled: !!itemId,
  });
}

export function useWarehouseInventory(warehouseId: string, includeZero = false) {
  return useQuery({
    queryKey: inventoryKeys.warehouseStock(warehouseId),
    queryFn: async () => {
      const { data } = await api.get<WarehouseInventory[]>(`/inventory/stock/warehouse/${warehouseId}`, {
        params: { include_zero: includeZero },
      });
      return data;
    },
    enabled: !!warehouseId,
  });
}

export function useStockValue(warehouseId?: string) {
  return useQuery({
    queryKey: inventoryKeys.stockValue(warehouseId),
    queryFn: async () => {
      const { data } = await api.get<StockValue>('/inventory/stock/value', {
        params: warehouseId ? { warehouse_id: warehouseId } : {},
      });
      return data;
    },
  });
}

export function useCreateMovement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (movement: MovementCreate) => {
      const { data } = await api.post<InventoryMovement>('/inventory/movements', movement);
      return data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.stock(variables.item_id) });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouseStock(variables.warehouse_id) });
      if (variables.target_warehouse_id) {
        queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouseStock(variables.target_warehouse_id) });
      }
      queryClient.invalidateQueries({ queryKey: inventoryKeys.stockValue() });
    },
  });
}

export function useMovementHistory(params: {
  item_id?: string;
  warehouse_id?: string;
  movement_type?: MovementType;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
} = {}) {
  return useQuery({
    queryKey: inventoryKeys.movements(params),
    queryFn: async () => {
      const { data } = await api.get<{ movements: InventoryMovement[]; total: number }>('/inventory/movements', {
        params,
      });
      return data;
    },
  });
}

export function useInventoryCount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { item_id: string; warehouse_id: string; counted_quantity: number }) => {
      const { data: result } = await api.post<{
        stock_level: { quantity_on_hand: number; last_count_date: string; last_count_quantity: number };
        adjustment_created: boolean;
        adjustment_id?: string;
      }>('/inventory/inventory-count', data);
      return result;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.stock(variables.item_id) });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.warehouseStock(variables.warehouse_id) });
    },
  });
}

// ============================================================================
// Goods Receipt Hooks
// ============================================================================

export function useGoodsReceipts(params: {
  warehouse_id?: string;
  pending_only?: boolean;
  limit?: number;
  offset?: number;
} = { pending_only: true }) {
  return useQuery({
    queryKey: inventoryKeys.goodsReceipts(),
    queryFn: async () => {
      const { data } = await api.get<GoodsReceipt[]>('/inventory/goods-receipts', { params });
      return data;
    },
  });
}

export function useGoodsReceipt(receiptId: string) {
  return useQuery({
    queryKey: inventoryKeys.goodsReceipt(receiptId),
    queryFn: async () => {
      const { data } = await api.get<GoodsReceipt>(`/inventory/goods-receipts/${receiptId}`);
      return data;
    },
    enabled: !!receiptId,
  });
}

export function useUnprocessedDeliveryNotes() {
  return useQuery({
    queryKey: inventoryKeys.unprocessedDeliveryNotes(),
    queryFn: async () => {
      const { data } = await api.get<UnprocessedDeliveryNote[]>('/inventory/goods-receipts/unprocessed-delivery-notes');
      return data;
    },
  });
}

export function useGoodsReceiptStatistics(warehouseId?: string) {
  return useQuery({
    queryKey: inventoryKeys.statistics(),
    queryFn: async () => {
      const { data } = await api.get<{ total: number; pending: number; processed: number }>(
        '/inventory/goods-receipts/statistics',
        { params: warehouseId ? { warehouse_id: warehouseId } : {} }
      );
      return data;
    },
  });
}

export function useCreateGoodsReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (receipt: GoodsReceiptCreate) => {
      const { data } = await api.post<GoodsReceipt>('/inventory/goods-receipts', receipt);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.goodsReceipts() });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.unprocessedDeliveryNotes() });
    },
  });
}

export function useAutoMatchGoodsReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ receiptId, minConfidence = 0.8 }: { receiptId: string; minConfidence?: number }) => {
      const { data } = await api.post<{ matched: number; unmatched: number; total: number }>(
        `/inventory/goods-receipts/${receiptId}/auto-match`,
        null,
        { params: { min_confidence: minConfidence } }
      );
      return data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.goodsReceipt(variables.receiptId) });
    },
  });
}

export function useMatchGoodsReceiptLine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ receiptId, lineId, itemId }: { receiptId: string; lineId: string; itemId: string }) => {
      const { data } = await api.post<GoodsReceiptLine>(`/inventory/goods-receipts/${receiptId}/match-line`, {
        line_id: lineId,
        item_id: itemId,
      });
      return data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.goodsReceipt(variables.receiptId) });
    },
  });
}

export function useUpdateGoodsReceiptLineQuantity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      receiptId,
      lineId,
      quantity,
    }: {
      receiptId: string;
      lineId: string;
      quantity: number;
    }) => {
      const { data } = await api.patch<GoodsReceiptLine>(`/inventory/goods-receipts/${receiptId}/line-quantity`, {
        line_id: lineId,
        quantity_received: quantity,
      });
      return data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.goodsReceipt(variables.receiptId) });
    },
  });
}

export function useProcessGoodsReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (receiptId: string) => {
      const { data } = await api.post<{ booked: number; skipped: number; movements: string[] }>(
        `/inventory/goods-receipts/${receiptId}/process`
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.goodsReceipts() });
      queryClient.invalidateQueries({ queryKey: inventoryKeys.stockValue() });
    },
  });
}

// ============================================================================
// Movement Type Labels (German)
// ============================================================================

export const MOVEMENT_TYPE_LABELS: Record<MovementType, string> = {
  goods_receipt: 'Wareneingang',
  goods_issue: 'Warenausgang',
  transfer: 'Umlagerung',
  adjustment_plus: 'Inventurkorrektur (+)',
  adjustment_minus: 'Inventurkorrektur (-)',
  return_inbound: 'Retoure Eingang',
  return_outbound: 'Retoure Ausgang',
  scrapping: 'Verschrottung',
};
