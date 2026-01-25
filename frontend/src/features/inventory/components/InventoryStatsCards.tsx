/**
 * Inventory Stats Cards - Uebersicht Lagerkennzahlen
 */

import { Card, CardContent } from '@/components/ui/card';
import { Package, Warehouse, AlertTriangle, TrendingUp } from 'lucide-react';
import { useWarehouses, useStockValue, useLowStockItems, useGoodsReceiptStatistics } from '../hooks/useInventory';
import { Skeleton } from '@/components/ui/skeleton';

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

export function InventoryStatsCards() {
  const { data: warehouses, isLoading: loadingWarehouses } = useWarehouses();
  const { data: stockValue, isLoading: loadingValue } = useStockValue();
  const { data: lowStock, isLoading: loadingLowStock } = useLowStockItems();
  const { data: receiptStats, isLoading: loadingReceipts } = useGoodsReceiptStatistics();

  const isLoading = loadingWarehouses || loadingValue || loadingLowStock || loadingReceipts;

  const stats = [
    {
      title: 'Lager',
      value: warehouses?.filter((w) => w.is_active).length ?? 0,
      description: 'Aktive Lagerorte',
      icon: Warehouse,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      title: 'Lagerwert',
      value: stockValue ? formatCurrency(stockValue.total_value) : '...',
      description: `${stockValue?.total_items ?? 0} Artikel`,
      icon: TrendingUp,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
    },
    {
      title: 'Niedriger Bestand',
      value: lowStock?.length ?? 0,
      description: 'Unter Meldebestand',
      icon: AlertTriangle,
      color: lowStock && lowStock.length > 0 ? 'text-orange-500' : 'text-muted-foreground',
      bgColor: lowStock && lowStock.length > 0 ? 'bg-orange-500/10' : 'bg-muted/10',
    },
    {
      title: 'Wareneingaenge',
      value: receiptStats?.pending ?? 0,
      description: 'Offen zur Verarbeitung',
      icon: Package,
      color: receiptStats && receiptStats.pending > 0 ? 'text-purple-500' : 'text-muted-foreground',
      bgColor: receiptStats && receiptStats.pending > 0 ? 'bg-purple-500/10' : 'bg-muted/10',
    },
  ];

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <Skeleton className="h-4 w-24 mb-2" />
              <Skeleton className="h-8 w-16 mb-1" />
              <Skeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.title}>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted-foreground">{stat.title}</p>
              <div className={`p-2 rounded-lg ${stat.bgColor}`}>
                <stat.icon className={`h-4 w-4 ${stat.color}`} />
              </div>
            </div>
            <div className="mt-2">
              <p className="text-2xl font-bold">{stat.value}</p>
              <p className="text-xs text-muted-foreground">{stat.description}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
