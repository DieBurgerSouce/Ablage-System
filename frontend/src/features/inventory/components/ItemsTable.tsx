/**
 * Items Table - Artikelliste mit Suche
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Search, Package, AlertTriangle } from 'lucide-react';
import { useInventoryItems, useItemCategories, useCreateItem, useLowStockItems, type ItemCreate } from '../hooks/useInventory';
import { toast } from 'sonner';

function formatCurrency(value: number | undefined): string {
  if (value === undefined || value === null) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

export function ItemsTable() {
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [formData, setFormData] = useState<ItemCreate>({
    item_number: '',
    name: '',
    unit: 'Stück',
    category: '',
    ean: '',
    purchase_price: undefined,
    sales_price: undefined,
    reorder_point: undefined,
  });

  const { data: itemsData, isLoading } = useInventoryItems({
    q: searchQuery || undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    limit: 50,
  });

  const { data: categories } = useItemCategories();
  const { data: lowStockItems } = useLowStockItems();
  const createItem = useCreateItem();

  // IDs der Artikel mit niedrigem Bestand
  const lowStockIds = new Set(lowStockItems?.map((ls) => ls.item.id) ?? []);

  const resetForm = () => {
    setFormData({
      item_number: '',
      name: '',
      unit: 'Stück',
      category: '',
      ean: '',
      purchase_price: undefined,
      sales_price: undefined,
      reorder_point: undefined,
    });
  };

  const handleCreate = async () => {
    try {
      await createItem.mutateAsync(formData);
      toast.success('Artikel erfolgreich erstellt');
      setIsCreateOpen(false);
      resetForm();
    } catch (error) {
      toast.error('Fehler beim Erstellen des Artikels');
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Artikel</CardTitle>
            <CardDescription>
              {itemsData?.total ?? 0} Artikel im Bestand
            </CardDescription>
          </div>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button onClick={resetForm}>
                <Plus className="h-4 w-4 mr-2" />
                Neuer Artikel
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Neuen Artikel anlegen</DialogTitle>
                <DialogDescription>
                  Erstellen Sie einen neuen Artikel für die Bestandsführung.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="item_number" className="text-right">
                    Artikelnr.*
                  </Label>
                  <Input
                    id="item_number"
                    value={formData.item_number}
                    onChange={(e) => setFormData({ ...formData, item_number: e.target.value })}
                    className="col-span-3"
                    placeholder="ART-001"
                  />
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="name" className="text-right">
                    Bezeichnung*
                  </Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="col-span-3"
                    placeholder="Artikelbezeichnung"
                  />
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="unit" className="text-right">
                    Einheit
                  </Label>
                  <Select
                    value={formData.unit}
                    onValueChange={(value) => setFormData({ ...formData, unit: value })}
                  >
                    <SelectTrigger className="col-span-3">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Stück">Stück</SelectItem>
                      <SelectItem value="kg">Kilogramm</SelectItem>
                      <SelectItem value="m">Meter</SelectItem>
                      <SelectItem value="l">Liter</SelectItem>
                      <SelectItem value="Packung">Packung</SelectItem>
                      <SelectItem value="Karton">Karton</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="category" className="text-right">
                    Kategorie
                  </Label>
                  <Input
                    id="category"
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="col-span-3"
                    placeholder="Warengruppe"
                  />
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="ean" className="text-right">
                    EAN
                  </Label>
                  <Input
                    id="ean"
                    value={formData.ean}
                    onChange={(e) => setFormData({ ...formData, ean: e.target.value })}
                    className="col-span-3"
                    placeholder="4001234567890"
                    maxLength={13}
                  />
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="purchase_price" className="text-right">
                    EK-Preis
                  </Label>
                  <Input
                    id="purchase_price"
                    type="number"
                    step="0.01"
                    value={formData.purchase_price ?? ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        purchase_price: e.target.value ? parseFloat(e.target.value) : undefined,
                      })
                    }
                    className="col-span-3"
                    placeholder="0,00"
                  />
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="reorder_point" className="text-right">
                    Meldebestand
                  </Label>
                  <Input
                    id="reorder_point"
                    type="number"
                    step="1"
                    value={formData.reorder_point ?? ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        reorder_point: e.target.value ? parseFloat(e.target.value) : undefined,
                      })
                    }
                    className="col-span-3"
                    placeholder="10"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Abbrechen
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!formData.item_number || !formData.name || createItem.isPending}
                >
                  Erstellen
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {/* Filters */}
        <div className="flex gap-4 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Suchen nach Artikelnr., Name, EAN..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Alle Kategorien" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Kategorien</SelectItem>
              {categories?.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">Lade Artikel...</div>
        ) : itemsData?.items.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Package className="h-12 w-12 mx-auto mb-2 opacity-50" />
            {searchQuery || categoryFilter !== 'all'
              ? 'Keine Artikel gefunden'
              : 'Noch keine Artikel angelegt'}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Artikelnr.</TableHead>
                <TableHead>Bezeichnung</TableHead>
                <TableHead>Kategorie</TableHead>
                <TableHead>Einheit</TableHead>
                <TableHead className="text-right">EK-Preis</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {itemsData?.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono font-medium">{item.item_number}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {item.name}
                      {lowStockIds.has(item.id) && (
                        <span title="Niedriger Bestand">
                          <AlertTriangle className="h-4 w-4 text-orange-500" />
                        </span>
                      )}
                    </div>
                    {item.ean && (
                      <span className="text-xs text-muted-foreground">EAN: {item.ean}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {item.category ? (
                      <Badge variant="outline">{item.category}</Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>{item.unit}</TableCell>
                  <TableCell className="text-right">{formatCurrency(item.purchase_price)}</TableCell>
                  <TableCell>
                    <Badge variant={item.is_active ? 'default' : 'secondary'}>
                      {item.is_active ? 'Aktiv' : 'Inaktiv'}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
