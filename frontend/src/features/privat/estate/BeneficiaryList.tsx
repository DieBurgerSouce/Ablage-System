/**
 * BeneficiaryList Component
 *
 * Verwaltet die Liste der Begünstigten mit CRUD-Operationen.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { Badge } from '@/components/ui/badge';
import { Users, Plus, Edit2, Trash2, AlertCircle } from 'lucide-react';
import { useBeneficiaries, useCreateBeneficiary, useUpdateBeneficiary, useDeleteBeneficiary } from './hooks';
import type { Beneficiary, RelationshipType } from '@/lib/api/services/estate-planning';
import { Skeleton } from '@/components/ui/skeleton';

interface BeneficiaryListProps {
  spaceId: string;
}

// Backend-Vertrag: RelationshipType/TaxClass sind deutsche Enum-Strings
// (app/services/privat/estate_planning_service.py)
const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  ehepartner: 'Ehepartner',
  lebenspartner: 'Lebenspartner',
  kind: 'Kind',
  stiefkind: 'Stiefkind',
  enkelkind: 'Enkel',
  enkelkind_eltern_leben: 'Enkel (Eltern leben)',
  elternteil: 'Elternteil',
  geschwister: 'Geschwister',
  neffe_nichte: 'Neffe/Nichte',
  sonstige_verwandte: 'Sonstige Verwandte',
  nicht_verwandt: 'Nicht verwandt',
};

const TAX_CLASS_LABELS: Record<string, string> = {
  klasse_i: 'Klasse I',
  klasse_ii: 'Klasse II',
  klasse_iii: 'Klasse III',
};

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

export function BeneficiaryList({ spaceId }: BeneficiaryListProps) {
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [editingBeneficiary, setEditingBeneficiary] = useState<string | null>(null);
  const [formData, setFormData] = useState<{
    name: string;
    relationship: RelationshipType;
    sharePercent: number;
    notes: string;
  }>({
    name: '',
    relationship: 'kind',
    sharePercent: 0,
    notes: '',
  });

  const { data: beneficiaries, isLoading } = useBeneficiaries(spaceId);
  const createMutation = useCreateBeneficiary();
  const updateMutation = useUpdateBeneficiary();
  const deleteMutation = useDeleteBeneficiary();

  const handleAdd = () => {
    createMutation.mutate(
      { spaceId, data: formData },
      {
        onSuccess: () => {
          setShowAddDialog(false);
          resetForm();
        },
      }
    );
  };

  const handleUpdate = () => {
    if (!editingBeneficiary) return;
    updateMutation.mutate(
      { spaceId, beneficiaryId: editingBeneficiary, data: formData },
      {
        onSuccess: () => {
          setEditingBeneficiary(null);
          resetForm();
        },
      }
    );
  };

  const handleDelete = (beneficiaryId: string) => {
    if (confirm('Möchten Sie diesen Begünstigten wirklich entfernen?')) {
      deleteMutation.mutate({ spaceId, beneficiaryId });
    }
  };

  const resetForm = () => {
    setFormData({ name: '', relationship: 'kind', sharePercent: 0, notes: '' });
  };

  const startEdit = (beneficiary: Beneficiary) => {
    setFormData({
      name: beneficiary.name,
      relationship: beneficiary.relationship,
      sharePercent: beneficiary.sharePercent,
      notes: beneficiary.notes ?? '',
    });
    setEditingBeneficiary(beneficiary.id);
  };

  // Gesamtanteil berechnen
  const totalShare = beneficiaries?.reduce((sum, b) => sum + b.sharePercent, 0) ?? 0;
  const shareWarning = totalShare !== 100 && (beneficiaries?.length ?? 0) > 0;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Begünstigte
            </CardTitle>
            <CardDescription>
              Verwalten Sie Erben und Vermächtnisnehmer
            </CardDescription>
          </div>
          <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Hinzufügen
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Begünstigten hinzufügen</DialogTitle>
                <DialogDescription>
                  Fügen Sie einen neuen Erben oder Vermächtnisnehmer hinzu.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Vor- und Nachname"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="relationship">Verwandtschaftsgrad</Label>
                  <Select
                    value={formData.relationship}
                    onValueChange={(v) => setFormData({ ...formData, relationship: v as RelationshipType })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(RELATIONSHIP_LABELS) as RelationshipType[]).map((rel) => (
                        <SelectItem key={rel} value={rel}>
                          {RELATIONSHIP_LABELS[rel]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="share">Anteil (%)</Label>
                  <Input
                    id="share"
                    type="number"
                    min={0}
                    max={100}
                    value={formData.sharePercent}
                    onChange={(e) =>
                      setFormData({ ...formData, sharePercent: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="notes">Notizen (optional)</Label>
                  <Input
                    id="notes"
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                    placeholder="Für Benachrichtigungen"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                  Abbrechen
                </Button>
                <Button onClick={handleAdd} disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Speichern...' : 'Speichern'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {shareWarning && (
          <div className="flex items-center gap-2 p-3 mb-4 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 rounded-lg">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">
              Die Gesamtanteile ergeben {totalShare}% (sollten 100% sein)
            </span>
          </div>
        )}

        {!beneficiaries || beneficiaries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Users className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Noch keine Begünstigten definiert</p>
            <p className="text-sm mt-1">
              Fügen Sie Erben und Vermächtnisnehmer hinzu.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Verwandtschaft</TableHead>
                <TableHead>Steuerklasse</TableHead>
                <TableHead className="text-right">Anteil</TableHead>
                <TableHead className="text-right">Freibetrag</TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {beneficiaries.map((ben) => (
                <TableRow key={ben.id}>
                  <TableCell className="font-medium">{ben.name}</TableCell>
                  <TableCell>
                    {RELATIONSHIP_LABELS[ben.relationship] ?? ben.relationship}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {TAX_CLASS_LABELS[ben.taxClass] ?? `Klasse ${ben.taxClass}`}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {ben.sharePercent}%
                  </TableCell>
                  <TableCell className="text-right text-green-600">
                    {formatCurrency(ben.personalAllowance)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => startEdit(ben)}
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(ben.id)}
                        disabled={deleteMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Edit Dialog */}
        <Dialog open={!!editingBeneficiary} onOpenChange={(open) => !open && setEditingBeneficiary(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Begünstigten bearbeiten</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Name</Label>
                <Input
                  id="edit-name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-share">Anteil (%)</Label>
                <Input
                  id="edit-share"
                  type="number"
                  min={0}
                  max={100}
                  value={formData.sharePercent}
                  onChange={(e) =>
                    setFormData({ ...formData, sharePercent: Number(e.target.value) })
                  }
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingBeneficiary(null)}>
                Abbrechen
              </Button>
              <Button onClick={handleUpdate} disabled={updateMutation.isPending}>
                {updateMutation.isPending ? 'Speichern...' : 'Speichern'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

export default BeneficiaryList;
