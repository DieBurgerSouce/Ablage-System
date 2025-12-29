/**
 * CategoryDocumentList - Hauptkomponente für Kategorie-Dokumente
 *
 * Orchestriert die Unterkomponenten:
 * - CategoryHeader (Breadcrumb, Titel)
 * - CategoryAggregations (Summen-Karten)
 * - DocumentFilterBar (Filter)
 * - DocumentsTable (Tabelle)
 * - BulkActionsToolbar (Bulk-Aktionen)
 */

import { useState, useMemo, useCallback } from 'react';
import { useParams } from '@tanstack/react-router';
import { type SortingState, type RowSelectionState } from '@tanstack/react-table';
import { Card, CardContent } from '@/components/ui/card';
import {
  CUSTOMER_CATEGORIES,
  SUPPLIER_CATEGORIES,
  CATEGORIES_WITH_PAYMENT_STATUS,
  DEFAULT_CATEGORY_FILTER,
  type CategoryDocumentFilter,
} from '../types';
import { useCategoryPage } from '../hooks/use-ablage-queries';
import { CategoryHeader } from './CategoryHeader';
import { CategoryAggregations } from './CategoryAggregations';
import { DocumentFilterBar } from './DocumentFilterBar';
import {
  DocumentsTable,
  DocumentsEmptyState,
  DocumentsPagination,
} from './DocumentsTable';
import { BulkActionsToolbar } from './BulkActionsToolbar';

// ==================== Types ====================

interface CategoryDocumentListProps {
  entityType: 'customer' | 'supplier';
}

// ==================== Main Component ====================

export function CategoryDocumentList({ entityType }: CategoryDocumentListProps) {
  const params = useParams({ strict: false });
  const isCustomer = entityType === 'customer';

  // Extract route params
  const entityId = isCustomer ? params.customerId : params.supplierId;
  const folderId = params.folderId;
  const category = params.category;

  // Category metadata
  const categories = isCustomer ? CUSTOMER_CATEGORIES : SUPPLIER_CATEGORIES;
  const categoryInfo = categories.find((c) => c.id === category);
  const showPaymentStatus = CATEGORIES_WITH_PAYMENT_STATUS.includes(category || '');

  // ==================== State ====================

  const [filter, setFilter] = useState<Partial<CategoryDocumentFilter>>(() => ({
    ...DEFAULT_CATEGORY_FILTER,
    businessEntityId: entityId || '',
    folderId: folderId || '',
    category: category || '',
    entityType,
  }));

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'documentDate', desc: true },
  ]);

  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // ==================== Data Query ====================

  const {
    documents,
    aggregations,
    isLoading,
    isLoadingAggregations,
    isError,
    error,
  } = useCategoryPage(
    {
      businessEntityId: entityId || '',
      folderId: folderId || '',
      category: category || '',
      entityType,
      search: filter.search,
      dateFrom: filter.dateFrom,
      dateTo: filter.dateTo,
      amountMin: filter.amountMin,
      amountMax: filter.amountMax,
      processingStatus: filter.processingStatus,
      paymentStatus: filter.paymentStatus,
      tags: filter.tags,
      sortBy: filter.sortBy,
      sortOrder: filter.sortOrder,
      page: filter.page,
      pageSize: filter.pageSize,
    },
    { enabled: !!entityId && !!folderId && !!category }
  );

  const documentList = documents?.items || [];
  const totalCount = documents?.total || 0;
  const totalPages = documents?.totalPages || 0;
  const currentPage = filter.page || 0;

  // Get selected document IDs
  const selectedIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);

  // Check if any filters are active
  const hasActiveFilters = useMemo(
    () =>
      !!(
        filter.search ||
        filter.dateFrom ||
        filter.dateTo ||
        filter.processingStatus?.length ||
        filter.paymentStatus?.length
      ),
    [filter]
  );

  // ==================== Handlers ====================

  const handlePageChange = useCallback((newPage: number) => {
    setFilter((prev) => ({ ...prev, page: newPage }));
    setRowSelection({}); // Clear selection on page change
  }, []);

  const handleFilterChange = useCallback(
    (newFilter: Partial<CategoryDocumentFilter>) => {
      setFilter((prev) => ({ ...prev, ...newFilter, page: 0 })); // Reset page on filter change
      setRowSelection({}); // Clear selection on filter change
    },
    []
  );

  const handleClearSelection = useCallback(() => {
    setRowSelection({});
  }, []);

  const handleUploadClick = useCallback(() => {
    // TODO: Implement upload modal/drawer
    console.log('Upload clicked');
  }, []);

  // ==================== Render ====================

  // Missing required params
  if (!entityId || !folderId || !category) {
    return (
      <div className="p-8">
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-muted-foreground">
              Ungültige Parameter. Bitte wählen Sie eine Kategorie aus.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 pb-24">
      {/* Header with Breadcrumb */}
      <CategoryHeader
        entityType={entityType}
        entityId={entityId}
        entityName={entityId} // TODO: Load entity name from API
        folderId={folderId}
        folderName={folderId} // TODO: Load folder name from API
        categoryInfo={categoryInfo}
        onUploadClick={handleUploadClick}
      />

      {/* Aggregations */}
      <CategoryAggregations
        aggregations={aggregations}
        isLoading={isLoadingAggregations}
        showPaymentInfo={showPaymentStatus}
      />

      {/* Filter Bar */}
      <DocumentFilterBar
        category={category}
        filter={filter}
        onChange={handleFilterChange}
        totalCount={totalCount}
      />

      {/* Error State */}
      {isError && (
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-destructive" role="alert">
              Fehler beim Laden der Dokumente: {(error as Error)?.message ?? 'Unbekannter Fehler'}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Content */}
      {!isError && (
        <>
          {/* Empty State */}
          {!isLoading && documentList.length === 0 && (
            <DocumentsEmptyState
              hasFilters={hasActiveFilters}
              onUploadClick={handleUploadClick}
            />
          )}

          {/* Document Table */}
          {(isLoading || documentList.length > 0) && (
            <DocumentsTable
              documents={documentList}
              showPaymentStatus={showPaymentStatus}
              isLoading={isLoading}
              sorting={sorting}
              onSortingChange={setSorting}
              rowSelection={rowSelection}
              onRowSelectionChange={setRowSelection}
            />
          )}

          {/* Pagination */}
          {!isLoading && documentList.length > 0 && (
            <DocumentsPagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={totalCount}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}

      {/* Bulk Actions Toolbar */}
      <BulkActionsToolbar
        selectedIds={selectedIds}
        category={category}
        onClearSelection={handleClearSelection}
      />
    </div>
  );
}

export default CategoryDocumentList;
