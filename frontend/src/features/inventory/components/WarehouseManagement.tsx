/**
 * Warehouse Management - Lagerverwaltung
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
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
import { Plus, Pencil, Trash2, MapPin, Star } from 'lucide-react';
import { useWarehouses, useCreateWarehouse, useUpdateWarehouse, useDeleteWarehouse, Warehouse, WarehouseCreate } from '../hooks/useInventory';
import { toast } from 'sonner';

export function WarehouseManagement() {
  const { data: warehouses, isLoading } = useWarehouses(true);
  const createWarehouse = useCreateWarehouse();
  const updateWarehouse = useUpdateWarehouse();
  const deleteWarehouse = useDeleteWarehouse();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingWarehouse, setEditingWarehouse] = useState<Warehouse | null>(null);
  const [formData, setFormData] = useState<WarehouseCreate>({
    code: '',
    name: '',
    description: '',
    address_line1: '',
    postal_code: '',
    city: '',
    country: 'DE',
    is_default: false,
  });

  const resetForm = () => {
    setFormData({
      code: '',
      name: '',
      description: '',
      address_line1: '',
      postal_code: '',
      city: '',
      country: 'DE',
      is_default: false,
    });
    setEditingWarehouse(null);
  };

  const handleCreate = async () => {
    try {
      await createWarehouse.mutateAsync(formData);
      toast.success('Lager erfolgreich erstellt');
      setIsCreateOpen(false);
      resetForm();
    } catch (error) {
      toast.error('Fehler beim Erstellen des Lagers');
    }
  };

  const handleUpdate = async () => {
    if (!editingWarehouse) return;
    try {
      await updateWarehouse.mutateAsync({ id: editingWarehouse.id, ...formData });
      toast.success('Lager erfolgreich aktualisiert');
      setEditingWarehouse(null);
      resetForm();
    } catch (error) {
      toast.error('Fehler beim Aktualisieren des Lagers');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Lager wirklich deaktivieren?')) return;
    try {
      await deleteWarehouse.mutateAsync(id);
      toast.success('Lager deaktiviert');
    } catch (error) {
      toast.error('Fehler beim Deaktivieren des Lagers');
    }
  };

  const openEdit = (warehouse: Warehouse) => {
    setEditingWarehouse(warehouse);
    setFormData({
      code: warehouse.code,
      name: warehouse.name,
      description: warehouse.description || '',
      address_line1: warehouse.address_line1 || '',
      postal_code: warehouse.postal_code || '',
      city: warehouse.city || '',
      country: warehouse.country,
      is_default: warehouse.is_default,
    });
  };

  const WarehouseForm = ({ isEdit = false }: { isEdit?: boolean }) => (
    <div className="grid gap-4 py-4">
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="code" className="text-right">
          Code*
        </Label>
        <Input
          id="code"
          value={formData.code}
          onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
          className="col-span-3"
          placeholder="HAUPT"
          maxLength={20}
        />
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="name" className="text-right">
          Name*
        </Label>
        <Input
          id="name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="col-span-3"
          placeholder="Hauptlager"
        />
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="description" className="text-right">
          Beschreibung
        </Label>
        <Textarea
          id="description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          className="col-span-3"
          placeholder="Optionale Beschreibung..."
        />
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="address" className="text-right">
          Adresse
        </Label>
        <Input
          id="address"
          value={formData.address_line1}
          onChange={(e) => setFormData({ ...formData, address_line1: e.target.value })}
          className="col-span-3"
          placeholder="Strasse und Hausnummer"
        />
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="postal" className="text-right">
          PLZ / Ort
        </Label>
        <div className="col-span-3 flex gap-2">
          <Input
            id="postal"
            value={formData.postal_code}
            onChange={(e) => setFormData({ ...formData, postal_code: e.target.value })}
            className="w-24"
            placeholder="12345"
          />
          <Input
            value={formData.city}
            onChange={(e) => setFormData({ ...formData, city: e.target.value })}
            className="flex-1"
            placeholder="Stadt"
          />
        </div>
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="default" className="text-right">
          Standardlager
        </Label>
        <div className="col-span-3 flex items-center gap-2">
          <Switch
            id="default"
            checked={formData.is_default}
            onCheckedChange={(checked) => setFormData({ ...formData, is_default: checked })}
          />
          <span className="text-sm text-muted-foreground">
            Als Standard fuer neue Wareneingaenge verwenden
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Lager</CardTitle>
            <CardDescription>Verwalten Sie Ihre Lagerorte</CardDescription>
          </div>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button onClick={resetForm}>
                <Plus className="h-4 w-4 mr-2" />
                Neues Lager
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Neues Lager erstellen</DialogTitle>
                <DialogDescription>
                  Erstellen Sie einen neuen Lagerort fuer Ihre Bestandsfuehrung.
                </DialogDescription>
              </DialogHeader>
              <WarehouseForm />
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Abbrechen
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!formData.code || !formData.name || createWarehouse.isPending}
                >
                  Erstellen
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">Lade Lager...</div>
        ) : warehouses?.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Noch keine Lager angelegt. Erstellen Sie Ihr erstes Lager.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Adresse</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {warehouses?.map((warehouse) => (
                <TableRow key={warehouse.id}>
                  <TableCell className="font-mono font-medium">{warehouse.code}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {warehouse.name}
                      {warehouse.is_default && (
                        <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {warehouse.city ? (
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <MapPin className="h-3 w-3" />
                        {warehouse.postal_code} {warehouse.city}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={warehouse.is_active ? 'default' : 'secondary'}>
                      {warehouse.is_active ? 'Aktiv' : 'Inaktiv'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(warehouse)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      {warehouse.is_active && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(warehouse.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Edit Dialog */}
        <Dialog open={!!editingWarehouse} onOpenChange={(open) => !open && setEditingWarehouse(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Lager bearbeiten</DialogTitle>
              <DialogDescription>Aendern Sie die Daten des Lagers.</DialogDescription>
            </DialogHeader>
            <WarehouseForm isEdit />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingWarehouse(null)}>
                Abbrechen
              </Button>
              <Button
                onClick={handleUpdate}
                disabled={!formData.code || !formData.name || updateWarehouse.isPending}
              >
                Speichern
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
