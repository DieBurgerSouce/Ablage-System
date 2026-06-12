/**
 * CategoryDocumentList - Hauptkomponente für Kategorie-Dokumente
 *
 * Orchestriert die Unterkomponenten:
 * - ProactiveInsightsBanner (KI-Insights, ganz oben)
 * - CategoryHeader (Breadcrumb, Titel)
 * - QuickActionsBar (NUR: Upload + Export)
 * - InvoiceTrackingBanner (Zahlungsstatus, nur bei Rechnungen)
 * - CategoryAggregations (Summen-Karten, NUR wenn documents > 0)
 * - DocumentFilterBar (Filter, NUR wenn documents > 0)
 * - DocumentsTable ODER DocumentsEmptyState (grosser Upload-CTA)
 * - BulkActionsToolbar (EINZIGE Quelle für Bulk-Aktionen)
 * - DocumentUploadDialog (Modaler Upload)
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
  type PaymentStatus,
} from '../types';
import {
  useCategoryPage,
  useBulkExportCsv,
  useBulkDownloadZip,
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
import { DocumentUploadDialog } from './DocumentUploadDialog';

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

  // Upload Dialog State
  const [showUploadDialog, setShowUploadDialog] = useState(false);

  // ==================== Mutations ====================

  const exportCsv = useBulkExportCsv();
  const downloadZip = useBulkDownloadZip();

  // ==================== Data Query ====================

  const {
    documents,
    aggregations,
    isLoading,
    isLoadingAggregations,
    isError,
    error,
    refetch,
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

  // Check if we have documents (for conditional rendering of stats/filters)
  const hasDocuments = !isLoading && documentList.length > 0;

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

  // Upload handler - opens the dialog
  const handleUploadClick = useCallback(() => {
    setShowUploadDialog(true);
  }, []);

  // Export handlers for QuickActionsBar
  // Export-Hooks arbeiten dokumentbasiert (documentIds) — die aktuell
  // gefilterte Liste wird exportiert (Hook-Vertrag use-ablage-queries).
  const handleExportCsv = useCallback(async () => {
    await exportCsv.mutateAsync({
      documentIds: documentList.map((d) => d.id),
    });
  }, [documentList, exportCsv]);

  const handleDownloadZip = useCallback(async () => {
    await downloadZip.mutateAsync({
      documentIds: documentList.map((d) => d.id),
    });
  }, [documentList, downloadZip]);

  // Filter handlers for banners
  const handleFilterOverdue = useCallback(() => {
    handleFilterChange({ paymentStatus: ['überfällig'] });
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

      {/* KI-Insights Banner - Nur bei Rechnungen und wenn Dokumente vorhanden */}
      {showPaymentStatus && hasDocuments && (
        <ProactiveInsightsBanner
          aggregations={aggregations}
          documents={documentList}
          category={category}
          isLoading={isLoadingAggregations}
          onFilterDocuments={(f) => handleFilterChange({ paymentStatus: f.paymentStatus as PaymentStatus[] | undefined })}
        />
      )}

      {/* Seitentitel mit Back-Button (OHNE Upload-Button) */}
      <CategoryTitle
        entityType={entityType}
        entityId={entityId}
        folderId={folderId}
        categoryInfo={categoryInfo}
      />

      {/* Quick Actions Bar - NUR Upload + Export */}
      <QuickActionsBar
        category={category}
        entityType={entityType}
        totalCount={totalCount}
        isLoading={isLoading}
        onUploadClick={handleUploadClick}
        onExportCsv={handleExportCsv}
        onDownloadZip={handleDownloadZip}
      />

      {/* Invoice Tracking Banner - Nur bei Rechnungen und wenn Dokumente vorhanden */}
      {showPaymentStatus && hasDocuments && (
        <InvoiceTrackingBanner
          aggregations={aggregations}
          documents={documentList}
          isLoading={isLoadingAggregations}
          onFilterOverdue={handleFilterOverdue}
          onFilterDueSoon={handleFilterDueSoon}
          onFilterOpen={handleFilterOpen}
        />
      )}

      {/* Aggregations - NUR wenn Dokumente vorhanden */}
      {hasDocuments && (
        <CategoryAggregations
          aggregations={aggregations}
          isLoading={isLoadingAggregations}
          showPaymentInfo={showPaymentStatus}
        />
      )}

      {/* Filter Bar - NUR wenn Dokumente vorhanden */}
      {hasDocuments && (
        <DocumentFilterBar
          category={category}
          filter={filter}
          onChange={handleFilterChange}
          totalCount={totalCount}
        />
      )}

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
          {/* Empty State - Grosser Upload-CTA */}
          {!isLoading && documentList.length === 0 && (
            <DocumentsEmptyState
              hasFilters={hasActiveFilters}
              onUploadClick={handleUploadClick}
              categoryLabel={categoryInfo?.label}
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

      {/* Bulk Actions Toolbar - EINZIGE Quelle für Bulk-Aktionen */}
      <BulkActionsToolbar
        selectedIds={selectedIds}
        category={category}
        entityType={entityType}
        folderId={folderId}
        onClearSelection={handleClearSelection}
      />

      {/* Document Upload Dialog */}
      <DocumentUploadDialog
        open={showUploadDialog}
        onOpenChange={setShowUploadDialog}
        entityId={entityId || ''}
        entityName={entityInfo?.name || ''}
        entityType={entityType}
        folderId={folderId || ''}
        folderName={folderDisplayName}
        category={category || ''}
        categoryName={categoryInfo?.label}
        onUploadComplete={() => refetch()}
      />
    </div>
  );
}

export default CategoryDocumentList;
