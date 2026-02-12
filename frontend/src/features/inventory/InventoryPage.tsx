/**
 * Inventory Page - Lagerverwaltung und Wareneingang
 *
 * Hauptseite für:
 * - Übersicht Lagerkennzahlen
 * - Lagerverwaltung
 * - Artikelstamm
 * - Wareneingang aus Lieferscheinen
 * - Bewegungshistorie
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Package, Warehouse, PackagePlus, History } from 'lucide-react';
import {
  InventoryStatsCards,
  WarehouseManagement,
  ItemsTable,
  GoodsReceiptPanel,
  MovementHistory,
} from './components';

export function InventoryPage() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-primary/10 rounded-lg">
          <Package className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Lagerverwaltung</h1>
          <p className="text-muted-foreground">
            Bestandsführung, Wareneingang und Bewegungshistorie
          </p>
        </div>
      </div>

      {/* Stats */}
      <InventoryStatsCards />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" className="gap-2">
            <Package className="h-4 w-4" />
            Artikel
          </TabsTrigger>
          <TabsTrigger value="warehouses" className="gap-2">
            <Warehouse className="h-4 w-4" />
            Lager
          </TabsTrigger>
          <TabsTrigger value="receipts" className="gap-2">
            <PackagePlus className="h-4 w-4" />
            Wareneingang
          </TabsTrigger>
          <TabsTrigger value="movements" className="gap-2">
            <History className="h-4 w-4" />
            Bewegungen
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6">
          <ItemsTable />
        </TabsContent>

        <TabsContent value="warehouses" className="mt-6">
          <WarehouseManagement />
        </TabsContent>

        <TabsContent value="receipts" className="mt-6">
          <GoodsReceiptPanel />
        </TabsContent>

        <TabsContent value="movements" className="mt-6">
          <MovementHistory />
        </TabsContent>
      </Tabs>
    </div>
  );
}
