/**
 * Streckengeschäft Classification Dashboard
 *
 * Main dashboard component for viewing and managing drop shipment classifications.
 * Follows established patterns from Mahnwesen dashboard.
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLanguage } from '@/lib/i18n/useLanguage';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  getSortedRowModel,
  type SortingState,
  getFilteredRowModel,
  type ColumnFiltersState,
} from '@tanstack/react-table';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { toast } from '@/components/ui/use-toast';
import {
  ArrowUpDown,
  CheckCircle2,
  AlertTriangle,
  FileText,
  MoreHorizontal,
  Search,
  Filter,
  Download,
  Eye,
  Edit,
  RefreshCw,
  TrendingUp,
  Building2,
  Globe,
  FileCheck,
} from 'lucide-react';

import type {
  DropShipmentClassification,
  TransactionType,
  ConfidenceLevel,
  ClassificationStatistics,
} from '@/types/streckengeschaeft';
import { apiClient } from '@/lib/api/client';

// =============================================================================
// KPI CARDS
// =============================================================================

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ReactNode;
  trend?: { value: number; label: string };
}

function StatsCard({ title, value, description, icon, trend }: StatsCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
        {trend && (
          <div className="flex items-center text-xs text-muted-foreground mt-1">
            <TrendingUp className="h-3 w-3 mr-1" aria-hidden="true" />
            {trend.value > 0 ? '+' : ''}{trend.value}% {trend.label}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StatisticsOverview({
  stats,
  t,
}: {
  stats?: ClassificationStatistics;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  // Check for stats AND nested properties to prevent undefined access errors
  if (!stats || !stats.byTransactionType || !stats.byConfidenceLevel) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  // Safe access with defaults
  const dropShipmentCount = stats.byTransactionType.drop_shipment ?? 0;
  const triangularCount = stats.byTransactionType.triangular_eu ?? 0;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatsCard
        title={t('streckengeschaeft.dashboard.totalClassified')}
        value={stats.totalDocuments ?? 0}
        description={t('streckengeschaeft.dashboard.documentsTotal')}
        icon={<FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
      />
      <StatsCard
        title={t('streckengeschaeft.dashboard.dropShipments')}
        value={dropShipmentCount + triangularCount}
        description={t('streckengeschaeft.dashboard.triangularCount', {
          count: triangularCount,
        })}
        icon={<Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
      />
      <StatsCard
        title={t('streckengeschaeft.dashboard.manualReview')}
        value={stats.pendingValidation ?? 0}
        description={t('streckengeschaeft.dashboard.pendingValidation')}
        icon={<AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />}
      />
      <StatsCard
        title={t('streckengeschaeft.dashboard.zmRelevant')}
        value={stats.zmRelevantCount ?? 0}
        description={t('streckengeschaeft.dashboard.forZm')}
        icon={<Globe className="h-4 w-4 text-primary" aria-hidden="true" />}
      />
    </div>
  );
}

// =============================================================================
// BADGES
// =============================================================================

function ConfidenceBadge({
  level,
  score,
  t,
}: {
  level: ConfidenceLevel;
  score: number;
  t: (key: string) => string;
}) {
  const variants: Record<ConfidenceLevel, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    definitive: 'default',
    high: 'default',
    medium: 'secondary',
    low: 'outline',
    manual_required: 'destructive',
  };

  return (
    <Badge variant={variants[level]} className="gap-1">
      {level === 'definitive' || level === 'high' ? (
        <CheckCircle2 className="h-3 w-3" />
      ) : level === 'manual_required' ? (
        <AlertTriangle className="h-3 w-3" />
      ) : null}
      {t(`streckengeschaeft.confidenceLevel.${level}`)} ({score}%)
    </Badge>
  );
}

function TransactionTypeBadge({
  type,
  t,
}: {
  type: TransactionType;
  t: (key: string) => string;
}) {
  const variants: Record<TransactionType, 'default' | 'secondary' | 'outline'> = {
    standard: 'outline',
    drop_shipment: 'default',
    triangular_eu: 'secondary',
    chain_transaction: 'secondary',
    unknown: 'outline',
  };

  return (
    <Badge variant={variants[type]}>
      {t(`streckengeschaeft.transactionType.${type}`)}
    </Badge>
  );
}

// =============================================================================
// TABLE COLUMNS FACTORY
// =============================================================================

function createColumns(
  t: (key: string) => string,
  language: 'de' | 'en'
): ColumnDef<DropShipmentClassification>[] {
  return [
    {
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label={t('common.select')}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label={t('common.select')}
        />
      ),
      enableSorting: false,
    },
    {
      accessorKey: 'documentId',
      header: t('navigation.documents'),
      cell: ({ row }) => (
        <div className="font-medium">
          <FileText className="h-4 w-4 inline mr-2 text-muted-foreground" />
          {row.getValue<string>('documentId').slice(0, 8)}...
        </div>
      ),
    },
    {
      accessorKey: 'transactionType',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          aria-sort={
            column.getIsSorted()
              ? column.getIsSorted() === 'asc'
                ? 'ascending'
                : 'descending'
              : 'none'
          }
        >
          {t('streckengeschaeft.validation.transactionType')}
          <ArrowUpDown className="ml-2 h-4 w-4" aria-hidden="true" />
        </Button>
      ),
      cell: ({ row }) => (
        <TransactionTypeBadge type={row.getValue('transactionType')} t={t} />
      ),
    },
    {
      accessorKey: 'confidenceLevel',
      header: t('ocr.results.confidence'),
      cell: ({ row }) => (
        <ConfidenceBadge
          level={row.getValue('confidenceLevel')}
          score={row.original.confidenceScore}
          t={t}
        />
      ),
    },
    {
      accessorKey: 'euCountriesInvolved',
      header: t('streckengeschaeft.detail.euCountries'),
      cell: ({ row }) => {
        const countries = row.getValue<string[]>('euCountriesInvolved') || [];
        return (
          <div className="flex gap-1">
            {countries.map((code) => (
              <Badge key={code} variant="outline" className="text-xs">
                {code}
              </Badge>
            ))}
          </div>
        );
      },
    },
    {
      accessorKey: 'zmRelevant',
      header: 'ZM',
      cell: ({ row }) =>
        row.getValue('zmRelevant') ? (
          <Badge variant="secondary">
            <Globe className="h-3 w-3 mr-1" />
            ZM {row.original.zmMarker === '1' ? '(Kz.1)' : ''}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: 'isValidated',
      header: t('common.status'),
      cell: ({ row }) =>
        row.getValue('isValidated') ? (
          <Badge variant="default" className="bg-success">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            {t('streckengeschaeft.proofStatus.complete')}
          </Badge>
        ) : (
          <Badge variant="outline">{t('documents.status.pending')}</Badge>
        ),
    },
    {
      accessorKey: 'createdAt',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          aria-sort={
            column.getIsSorted()
              ? column.getIsSorted() === 'asc'
                ? 'ascending'
                : 'descending'
              : 'none'
          }
        >
          {t('common.date')}
          <ArrowUpDown className="ml-2 h-4 w-4" aria-hidden="true" />
        </Button>
      ),
      cell: ({ row }) => {
        const date = new Date(row.getValue('createdAt'));
        return date.toLocaleDateString(language === 'de' ? 'de-DE' : 'en-US');
      },
    },
    {
      id: 'actions',
      cell: () => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0" aria-label={t('common.actions')}>
              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t('common.actions')}</DropdownMenuLabel>
            <DropdownMenuItem>
              <Eye className="h-4 w-4 mr-2" aria-hidden="true" />
              {t('documents.actions.view')}
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Edit className="h-4 w-4 mr-2" aria-hidden="true" />
              {t('streckengeschaeft.actions.validate')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <FileCheck className="h-4 w-4 mr-2" aria-hidden="true" />
              {t('streckengeschaeft.classification.proofDocuments')}
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Download className="h-4 w-4 mr-2" aria-hidden="true" />
              {t('streckengeschaeft.datev.export')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function StreckengeschaeftDashboard() {
  const { t, language } = useLanguage();
  const queryClient = useQueryClient();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [rowSelection, setRowSelection] = useState({});
  const [transactionTypeFilter, setTransactionTypeFilter] = useState<string>('all');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all');

  // Memoize columns to prevent recreation on every render
  const columns = useMemo(() => createColumns(t, language), [t, language]);

  const { data: stats } = useQuery({
    queryKey: ['streckengeschaeft', 'statistics'],
    queryFn: async () => {
      const response = await apiClient.get<ClassificationStatistics>('/streckengeschäft/statistics');
      return response.data; // Return actual data, not AxiosResponse
    },
  });

  const {
    data: classificationsData,
    isLoading,
    error: classificationsError,
    refetch,
  } = useQuery({
    queryKey: ['streckengeschaeft', 'classifications', transactionTypeFilter, confidenceFilter],
    queryFn: async () => {
      const response = await apiClient.get('/streckengeschäft/classifications', {
        params: {
          transaction_type: transactionTypeFilter !== 'all' ? transactionTypeFilter : undefined,
          confidence_level: confidenceFilter !== 'all' ? confidenceFilter : undefined,
          page_size: 50,
        },
      });
      return response.data; // Return actual data, not AxiosResponse
    },
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });

  const datevExportMutation = useMutation({
    mutationFn: async (classificationIds: string[]) => {
      const response = await apiClient.post('/streckengeschäft/datev/export', {
        classification_ids: classificationIds,
        kontenrahmen: 'SKR03',
        include_zm_data: true,
      });
      return response.data; // Return actual data, not AxiosResponse
    },
    onSuccess: (data) => {
      toast({
        title: t('streckengeschaeft.datev.exportSuccess').replace('{{filename}}', data.filename),
        variant: 'success',
      });
      window.open(data.download_url, '_blank');
    },
    onError: () => {
      toast({
        title: t('streckengeschaeft.datev.exportError'),
        variant: 'destructive',
      });
    },
  });

  const classifications = classificationsData?.items || [];

  const table = useReactTable({
    data: classifications,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onRowSelectionChange: setRowSelection,
    state: { sorting, columnFilters, rowSelection },
  });

  const selectedIds = Object.keys(rowSelection)
    .filter((key) => rowSelection[key as keyof typeof rowSelection])
    .map((key) => classifications[parseInt(key)]?.id)
    .filter(Boolean);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t('streckengeschaeft.title')}
          </h1>
          <p className="text-muted-foreground">{t('streckengeschaeft.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['streckengeschaeft'] })}
          >
            <RefreshCw className="h-4 w-4 mr-2" aria-hidden="true" />
            {t('common.refresh')}
          </Button>
          <Button
            disabled={selectedIds.length === 0}
            onClick={() => datevExportMutation.mutate(selectedIds)}
          >
            <Download className="h-4 w-4 mr-2" aria-hidden="true" />
            {t('streckengeschaeft.datev.export')} ({selectedIds.length})
          </Button>
        </div>
      </div>

      {stats && <StatisticsOverview stats={stats} t={t} />}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {t('streckengeschaeft.classification.title')}
          </CardTitle>
          <CardDescription>{t('streckengeschaeft.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <Select value={transactionTypeFilter} onValueChange={setTransactionTypeFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder={t('streckengeschaeft.validation.transactionType')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('common.all')}</SelectItem>
                  <SelectItem value="drop_shipment">
                    {t('streckengeschaeft.transactionType.drop_shipment')}
                  </SelectItem>
                  <SelectItem value="triangular_eu">
                    {t('streckengeschaeft.transactionType.triangular_eu')}
                  </SelectItem>
                  <SelectItem value="chain_transaction">
                    {t('streckengeschaeft.transactionType.chain_transaction')}
                  </SelectItem>
                  <SelectItem value="unknown">
                    {t('streckengeschaeft.transactionType.standard')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Select value={confidenceFilter} onValueChange={setConfidenceFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder={t('ocr.results.confidence')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('common.all')}</SelectItem>
                <SelectItem value="definitive">
                  {t('streckengeschaeft.confidenceLevel.definitive')} (100%)
                </SelectItem>
                <SelectItem value="high">
                  {t('streckengeschaeft.confidenceLevel.high')} (90-99%)
                </SelectItem>
                <SelectItem value="medium">
                  {t('streckengeschaeft.confidenceLevel.medium')} (70-89%)
                </SelectItem>
                <SelectItem value="low">
                  {t('streckengeschaeft.confidenceLevel.low')} (50-69%)
                </SelectItem>
                <SelectItem value="manual_required">
                  {t('streckengeschaeft.confidenceLevel.manual_required')}
                </SelectItem>
              </SelectContent>
            </Select>
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <Input
                  placeholder={`${t('common.search')}...`}
                  className="pl-8"
                  onChange={(e) => table.getColumn('documentId')?.setFilterValue(e.target.value)}
                />
              </div>
            </div>
          </div>

          {classificationsError ? (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('common.error')}</AlertTitle>
              <AlertDescription className="flex items-center justify-between">
                <span>
                  {t('streckengeschaeft.dashboardError.loadError')}
                </span>
                <Button variant="outline" size="sm" onClick={() => refetch()}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  {t('common.retry')}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      {columns.map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : classificationsError ? (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                      <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      {t('streckengeschaeft.dashboardError.dataLoadError')}
                    </TableCell>
                  </TableRow>
                ) : table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow key={row.id} data-state={row.getIsSelected() && 'selected'}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      {t('documents.list.empty')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between mt-4">
            <div className="text-sm text-muted-foreground">
              {selectedIds.length} {t('common.selected')}
            </div>
            <div className="text-sm text-muted-foreground">
              {t('common.all')}: {classificationsData?.total || 0}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default StreckengeschaeftDashboard;
