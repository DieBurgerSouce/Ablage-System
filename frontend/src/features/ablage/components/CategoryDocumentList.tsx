/**
 * CategoryDocumentList - Hauptkomponente für Kategorie-Dokumente
 *
 * Orchestriert die Unterkomponenten:
 * - ProactiveInsightsBanner (KI-Insights, ganz oben)
 * - CategoryHeader (Breadcrumb, Titel)
 * - QuickActionsBar (Primaere + Kontext-Aktionen)
 * - InvoiceTrackingBanner (Zahlungsstatus, nur bei Rechnungen)
 * - CategoryAggregations (Summen-Karten)
 * - DocumentFilterBar (Filter)
 * - DocumentsTable (Tabelle)
 * - BulkActionsToolbar (Bulk-Aktionen, fixiert unten)
 */

import { useState, useMemo, useCallback } from 'react';
import { useParams } from '@tanstack/react-router';
import { type SortingState, type RowSelectionState } from '@tanstack/react-table';
import { Card, CardContent } from '@/components/ui/card';
import {
  SUPPLIER_CATEGORIES,
  getCustomerCategoriesForFolder,
  CATEGORIES_WITH_PAYMENT_STATUS,
  DEFAULT_CATEGORY_FILTER,
  type CategoryDocumentFilter,
} from '../types';
import {
  useCategoryPage,
  useBulkMarkAsPaid,
  useBulkDelete,
} from '../hooks/use-ablage-queries';
import { useEntityName } from '../hooks/useAblage';
import { CategoryBreadcrumb, CategoryTitle } from './CategoryHeader';
import { CategoryAggregations } from './CategoryAggregations';
import { DocumentFilterBar } from './DocumentFilterBar';
import {
  DocumentsTable,
  DocumentsEmptyState,
  DocumentsPagination,
} from './DocumentsTable';
import { BulkActionsToolbar } from './BulkActionsToolbar';
import { InvoiceTrackingBanner } from './InvoiceTrackingBanner';
import { ProactiveInsightsBanner } from './ProactiveInsightsBanner';
import { QuickActionsBar } from './QuickActionsBar';
import { MoveFolderDialog } from './MoveFolderDialog';
import { TagsEditDialog } from './TagsEditDialog';

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

  // Category metadata - Kunden-Kategorien sind ordner-spezifisch (Messer hat "Druckdaten")
  const categories = isCustomer
    ? getCustomerCategoriesForFolder(folderId || '')
    : SUPPLIER_CATEGORIES;
  const categoryInfo = categories.find((c) => c.id === category);
  const showPaymentStatus = CATEGORIES_WITH_PAYMENT_STATUS.includes(category || '');

  // Entity-Name via API laden (statt UUID anzeigen)
  const { data: entityInfo } = useEntityName(entityId);

  // Folder-Namen mappen (folie → Folie, messer → Spargelmesser)
  const FOLDER_NAMES: Record<string, string> = {
    folie: 'Folie',
    messer: 'Spargelmesser',
  };
  const folderDisplayName = FOLDER_NAMES[folderId || ''] || folderId || '';

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

  // Dialog states
  const [showMoveDialog, setShowMoveDialog] = useState(false);
  const [showTagsDialog, setShowTagsDialog] = useState(false);

  // ==================== Mutations ====================

  const markAsPaidMutation = useBulkMarkAsPaid();
  const deleteMutation = useBulkDelete();

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

  // Bulk action handlers
  const handleMarkAsPaid = useCallback(async () => {
    if (selectedIds.length === 0) return;
    await markAsPaidMutation.mutateAsync({ documentIds: selectedIds });
    setRowSelection({});
  }, [selectedIds, markAsPaidMutation]);

  const handleMoveCategory = useCallback(() => {
    if (selectedIds.length === 0) return;
    setShowMoveDialog(true);
  }, [selectedIds]);

  const handleSetTags = useCallback(() => {
    if (selectedIds.length === 0) return;
    setShowTagsDialog(true);
  }, [selectedIds]);

  const handleDelete = useCallback(async () => {
    if (selectedIds.length === 0) return;
    if (!confirm(`Moechten Sie ${selectedIds.length} Dokument(e) wirklich loeschen?`)) return;
    await deleteMutation.mutateAsync({ documentIds: selectedIds });
    setRowSelection({});
  }, [selectedIds, deleteMutation]);

  // Filter handlers for banners
  const handleFilterOverdue = useCallback(() => {
    handleFilterChange({ paymentStatus: ['ueberfaellig'] });
  }, [handleFilterChange]);

  const handleFilterDueSoon = useCallback(() => {
    handleFilterChange({ paymentStatus: ['offen'] });
  }, [handleFilterChange]);

  const handleFilterOpen = useCallback(() => {
    handleFilterChange({ paymentStatus: ['offen'] });
  }, [handleFilterChange]);

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
      {/* Breadcrumb - Ganz oben wie bei allen anderen Seiten */}
      <CategoryBreadcrumb
        entityType={entityType}
        entityId={entityId}
        entityName={entityInfo?.name || entityId}
        folderId={folderId}
        folderName={folderDisplayName}
        categoryInfo={categoryInfo}
      />

      {/* KI-Insights Banner */}
      {showPaymentStatus && (
        <ProactiveInsightsBanner
          aggregations={aggregations}
          documents={documentList}
          category={category}
          isLoading={isLoadingAggregations}
          onMarkAsPaid={handleMarkAsPaid}
          onFilterDocuments={(f) => handleFilterChange({ paymentStatus: f.paymentStatus as string[] | undefined })}
        />
      )}

      {/* Seitentitel mit Back-Button und Upload */}
      <CategoryTitle
        entityType={entityType}
        entityId={entityId}
        folderId={folderId}
        categoryInfo={categoryInfo}
        onUploadClick={handleUploadClick}
      />

      {/* Quick Actions Bar - Unter Header */}
      <QuickActionsBar
        category={category}
        entityType={entityType}
        selectedIds={selectedIds}
        totalCount={totalCount}
        onUploadClick={handleUploadClick}
        onMoveCategory={handleMoveCategory}
        onSetTags={handleSetTags}
        onMarkAsPaid={showPaymentStatus ? handleMarkAsPaid : undefined}
        onDelete={handleDelete}
        onClearSelection={handleClearSelection}
      />

      {/* Invoice Tracking Banner - Nur bei Rechnungen */}
      {showPaymentStatus && (
        <InvoiceTrackingBanner
          aggregations={aggregations}
          documents={documentList}
          isLoading={isLoadingAggregations}
          onFilterOverdue={handleFilterOverdue}
          onFilterDueSoon={handleFilterDueSoon}
          onFilterOpen={handleFilterOpen}
        />
      )}

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

      {/* Bulk Actions Toolbar - Fixiert unten */}
      <BulkActionsToolbar
        selectedIds={selectedIds}
        category={category}
        entityType={entityType}
        onClearSelection={handleClearSelection}
      />

      {/* Dialogs */}
      <MoveFolderDialog
        open={showMoveDialog}
        onOpenChange={setShowMoveDialog}
        entityType={entityType}
        folderId={folderId}
        currentCategory={category}
        selectedIds={selectedIds}
        onSuccess={() => setRowSelection({})}
      />

      <TagsEditDialog
        open={showTagsDialog}
        onOpenChange={setShowTagsDialog}
        selectedIds={selectedIds}
        onSuccess={() => setRowSelection({})}
      />
    </div>
  );
}

export default CategoryDocumentList;
