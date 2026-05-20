/**
 * ContractCostBreakdown - Kostenaufschlüsselung nach Kategorie/Lieferant
 *
 * Features:
 * - Umschalten zwischen Kategorie- und Lieferanten-Ansicht
 * - Sortierbare Tabelle mit Balkenvisualisierung
 * - Gesamtzeile am Ende
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowUpDown, Building2, Tags } from 'lucide-react';
import type { ContractCostSummary } from '../api/contract-lifecycle-api';

interface ContractCostBreakdownProps {
  costSummary?: ContractCostSummary;
  isLoading: boolean;
}

type ViewMode = 'category' | 'supplier';
type SortField = 'name' | 'annual_cost' | 'contract_count';
type SortDir = 'asc' | 'desc';

interface CostRow {
  name: string;
  annual_cost: number;
  contract_count: number;
}

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

export function ContractCostBreakdown({ costSummary, isLoading }: ContractCostBreakdownProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('category');
  const [sortField, setSortField] = useState<SortField>('annual_cost');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const rows: CostRow[] = useMemo(() => {
    if (!costSummary) return [];

    const sourceData = viewMode === 'category'
      ? costSummary.by_category.map((c) => ({
          name: c.category,
          annual_cost: c.annual_cost,
          contract_count: c.contract_count,
        }))
      : costSummary.by_supplier.map((s) => ({
          name: s.supplier_name,
          annual_cost: s.annual_cost,
          contract_count: s.contract_count,
        }));

    return [...sourceData].sort((a, b) => {
      const aVal = sortField === 'name' ? a.name.toLowerCase() : a[sortField];
      const bVal = sortField === 'name' ? b.name.toLowerCase() : b[sortField];
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [costSummary, viewMode, sortField, sortDir]);

  const maxCost = useMemo(() => {
    if (rows.length === 0) return 1;
    return Math.max(...rows.map((r) => r.annual_cost), 1);
  }, [rows]);

  const totals = useMemo(() => ({
    annual_cost: rows.reduce((sum, r) => sum + r.annual_cost, 0),
    contract_count: rows.reduce((sum, r) => sum + r.contract_count, 0),
  }), [rows]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Kostenaufschlüsselung</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Kostenaufschlüsselung</CardTitle>
          <div className="flex gap-1">
            <Button
              variant={viewMode === 'category' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setViewMode('category')}
            >
              <Tags className="h-4 w-4 mr-1" />
              Nach Kategorie
            </Button>
            <Button
              variant={viewMode === 'supplier' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setViewMode('supplier')}
            >
              <Building2 className="h-4 w-4 mr-1" />
              Nach Lieferant
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Kostendaten verfügbar
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 pr-4">
                    <button
                      onClick={() => handleSort('name')}
                      className="flex items-center gap-1 font-medium hover:text-foreground"
                    >
                      {viewMode === 'category' ? 'Kategorie' : 'Lieferant'}
                      <ArrowUpDown className="h-3 w-3" />
                    </button>
                  </th>
                  <th className="text-right py-2 px-4">
                    <button
                      onClick={() => handleSort('annual_cost')}
                      className="flex items-center gap-1 font-medium hover:text-foreground ml-auto"
                    >
                      Jahreskosten
                      <ArrowUpDown className="h-3 w-3" />
                    </button>
                  </th>
                  <th className="py-2 px-4 w-48">
                    <span className="sr-only">Balken</span>
                  </th>
                  <th className="text-right py-2 px-4">Monatlich</th>
                  <th className="text-right py-2 pl-4">
                    <button
                      onClick={() => handleSort('contract_count')}
                      className="flex items-center gap-1 font-medium hover:text-foreground ml-auto"
                    >
                      Verträge
                      <ArrowUpDown className="h-3 w-3" />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const barWidth = (row.annual_cost / maxCost) * 100;
                  return (
                    <tr key={row.name} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-2.5 pr-4 font-medium">{row.name}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums">
                        {formatCurrency(row.annual_cost)}
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="w-full bg-muted rounded-full h-2">
                          <div
                            className="bg-primary rounded-full h-2 transition-all"
                            style={{ width: `${barWidth}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-muted-foreground">
                        {formatCurrency(row.annual_cost / 12)}
                      </td>
                      <td className="py-2.5 pl-4 text-right tabular-nums">{row.contract_count}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 font-semibold">
                  <td className="py-2.5 pr-4">Gesamt</td>
                  <td className="py-2.5 px-4 text-right tabular-nums">
                    {formatCurrency(totals.annual_cost)}
                  </td>
                  <td className="py-2.5 px-4" />
                  <td className="py-2.5 px-4 text-right tabular-nums">
                    {formatCurrency(totals.annual_cost / 12)}
                  </td>
                  <td className="py-2.5 pl-4 text-right tabular-nums">{totals.contract_count}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
