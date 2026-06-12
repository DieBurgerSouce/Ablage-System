/**
 * PowerOfAttorneyManager Component
 *
 * Verwaltet Vorsorgevollmachten, Generalvollmachten und Betreuungsverfügungen.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
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
import { Badge } from '@/components/ui/badge';
import { FileText, Plus, AlertTriangle, CheckCircle2, Upload } from 'lucide-react';
import { usePowersOfAttorney, useCreatePowerOfAttorney } from './hooks';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface PowerOfAttorneyManagerProps {
  spaceId: string;
}

const POA_TYPES = {
  vorsorgevollmacht: {
    label: 'Vorsorgevollmacht',
    description: 'Für Gesundheits- und Vermögensangelegenheiten bei Handlungsunfähigkeit',
    essential: true,
  },
  generalvollmacht: {
    label: 'Generalvollmacht',
    description: 'Umfassende Vollmacht für alle Rechtsgeschäfte',
    essential: false,
  },
  betreuungsverfuegung: {
    label: 'Betreuungsverfügung',
    description: 'Wünsche für gerichtlich bestellte Betreuung',
    essential: true,
  },
  patientenverfuegung: {
    label: 'Patientenverfügung',
    description: 'Wünsche für medizinische Behandlung am Lebensende',
    essential: true,
  },
  bankvollmacht: {
    label: 'Bankvollmacht',
    description: 'Vollmacht für Bankgeschäfte',
    essential: false,
  },
};

export function PowerOfAttorneyManager({ spaceId }: PowerOfAttorneyManagerProps) {
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [formData, setFormData] = useState({
    type: 'vorsorgevollmacht',
    authorizedPerson: '',
    issueDate: '',
    notes: '',
  });

  const { data: poas, isLoading } = usePowersOfAttorney(spaceId);
  const createMutation = useCreatePowerOfAttorney();

  const handleAdd = () => {
    createMutation.mutate(
      { spaceId, data: formData },
      {
        onSuccess: () => {
          setShowAddDialog(false);
          setFormData({
            type: 'vorsorgevollmacht',
            authorizedPerson: '',
            issueDate: '',
            notes: '',
          });
        },
      }
    );
  };

  // Fehlende essenzielle Vollmachten ermitteln
  const existingTypes = new Set(poas?.map((p) => p.type) ?? []);
  const missingEssential = Object.entries(POA_TYPES)
    .filter(([type, info]) => info.essential && !existingTypes.has(type))
    .map(([_type, info]) => info.label);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Warnung für fehlende Vollmachten */}
      {missingEssential.length > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehlende wichtige Vollmachten</AlertTitle>
          <AlertDescription>
            Folgende essenzielle Dokumente fehlen noch: {missingEssential.join(', ')}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Vollmachten
              </CardTitle>
              <CardDescription>
                Vorsorgevollmachten, Patientenverfügungen und mehr
              </CardDescription>
            </div>
            <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4 mr-2" />
                  Vollmacht hinzufügen
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Vollmacht hinzufügen</DialogTitle>
                  <DialogDescription>
                    Erfassen Sie eine neue Vollmacht oder Verfügung.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label>Art der Vollmacht</Label>
                    <Select
                      value={formData.type}
                      onValueChange={(v) => setFormData({ ...formData, type: v })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(POA_TYPES).map(([type, info]) => (
                          <SelectItem key={type} value={type}>
                            {info.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-sm text-muted-foreground">
                      {POA_TYPES[formData.type as keyof typeof POA_TYPES]?.description}
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="authorizedPerson">Bevollmächtigte Person</Label>
                    <Input
                      id="authorizedPerson"
                      value={formData.authorizedPerson}
                      onChange={(e) =>
                        setFormData({ ...formData, authorizedPerson: e.target.value })
                      }
                      placeholder="Name der bevollmächtigten Person"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="issueDate">Ausstellungsdatum</Label>
                    <Input
                      id="issueDate"
                      type="date"
                      value={formData.issueDate}
                      onChange={(e) =>
                        setFormData({ ...formData, issueDate: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="notes">Notizen (optional)</Label>
                    <Textarea
                      id="notes"
                      value={formData.notes}
                      onChange={(e) =>
                        setFormData({ ...formData, notes: e.target.value })
                      }
                      placeholder="Zusätzliche Informationen"
                      rows={3}
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
          {!poas || poas.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Noch keine Vollmachten hinterlegt</p>
              <p className="text-sm mt-1">
                Fügen Sie wichtige Dokumente wie Vorsorgevollmacht hinzu.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {poas.map((poa) => {
                const typeInfo = POA_TYPES[poa.type as keyof typeof POA_TYPES];
                return (
                  <div
                    key={poa.id}
                    className="flex items-start justify-between p-4 border rounded-lg"
                  >
                    <div className="flex items-start gap-4">
                      <div className="p-2 bg-primary/10 rounded-lg">
                        <FileText className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium">
                            {typeInfo?.label ?? poa.type}
                          </h4>
                          {typeInfo?.essential && (
                            <Badge variant="outline" className="text-xs">
                              Essenziell
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Bevollmächtigt: {poa.authorizedPerson}
                        </p>
                        {poa.issueDate && (
                          <p className="text-xs text-muted-foreground">
                            Ausgestellt: {new Date(poa.issueDate).toLocaleDateString('de-DE')}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {poa.documentId ? (
                        <Badge variant="secondary" className="flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Dokument hinterlegt
                        </Badge>
                      ) : (
                        <Button variant="outline" size="sm">
                          <Upload className="h-4 w-4 mr-1" />
                          Hochladen
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default PowerOfAttorneyManager;
