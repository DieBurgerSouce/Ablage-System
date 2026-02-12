import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Loader2, Plus, Trash2 } from 'lucide-react';

export interface AmountTier {
  name: string;
  max_amount: string;
  approval_mode: string;
  min_trust_level: string;
}

export interface AmountTiersResponse {
  tiers: AmountTier[];
  is_default: boolean;
}

/**
 * AmountTierConfig - Konfigurationskomponente für betragsbasierte Freigabestufen.
 *
 * Ermöglicht die Verwaltung von bis zu 5 Betrags-Freigabestufen:
 * - Automatisch: Automatische Freigabe (Standard: < 500 EUR)
 * - Ein-Klick: Ein-Klick-Bestätigung (Standard: 500-5000 EUR)
 * - Explizit: Explizite Prüfung erforderlich (Standard: > 5000 EUR)
 */
export function AmountTierConfig() {
  const { toast } = useToast();
  const [tiers, setTiers] = useState<AmountTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isModified, setIsModified] = useState(false);

  // Load initial tiers
  useEffect(() => {
    loadTiers();
  }, []);

  const loadTiers = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/autonomous/amount-tiers');
      if (response.ok) {
        const data: AmountTiersResponse = await response.json();
        setTiers(data.tiers);
        setIsModified(false);
      } else {
        toast({
          title: 'Fehler',
          description: 'Betrags-Freigabestufen konnten nicht geladen werden',
          variant: 'destructive',
        });
      }
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Verbindungsfehler beim Laden der Einstellungen',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTierChange = (
    index: number,
    field: keyof AmountTier,
    value: string
  ) => {
    const newTiers = [...tiers];
    newTiers[index] = { ...newTiers[index], [field]: value };
    setTiers(newTiers);
    setIsModified(true);
  };

  const handleAddTier = () => {
    if (tiers.length >= 5) {
      toast({
        title: 'Maximale Anzahl erreicht',
        description: 'Es können maximal 5 Betrags-Freigabestufen erstellt werden',
      });
      return;
    }
    const newTier: AmountTier = {
      name: `Stufe ${tiers.length + 1}`,
      max_amount: '10000.00',
      approval_mode: 'explicit',
      min_trust_level: 'assistance',
    };
    setTiers([...tiers, newTier]);
    setIsModified(true);
  };

  const handleRemoveTier = (index: number) => {
    if (tiers.length <= 2) {
      toast({
        title: 'Mindestanzahl erforderlich',
        description: 'Es muss mindestens 2 Betrags-Freigabestufen geben',
      });
      return;
    }
    const newTiers = tiers.filter((_, i) => i !== index);
    setTiers(newTiers);
    setIsModified(true);
  };

  const handleSave = async () => {
    try {
      // Validate amounts are ascending
      for (let i = 0; i < tiers.length - 1; i++) {
        const current = parseFloat(tiers[i].max_amount);
        const next = parseFloat(tiers[i + 1].max_amount);
        if (current >= next) {
          toast({
            title: 'Validierungsfehler',
            description: 'Betrags-Obergrenzen müssen aufsteigend sortiert sein',
            variant: 'destructive',
          });
          return;
        }
      }

      // Validate last tier is explicit
      if (tiers[tiers.length - 1].approval_mode !== 'explicit') {
        toast({
          title: 'Validierungsfehler',
          description: 'Die letzte Betrags-Freigabestufe muss "Explizit" sein',
          variant: 'destructive',
        });
        return;
      }

      setSaving(true);
      const response = await fetch('/api/v1/autonomous/amount-tiers', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tiers }),
      });

      if (response.ok) {
        const data: AmountTiersResponse = await response.json();
        setTiers(data.tiers);
        setIsModified(false);
        toast({
          title: 'Erfolg',
          description: 'Betrags-Freigabestufen wurden gespeichert',
        });
      } else {
        const error = await response.json();
        toast({
          title: 'Fehler beim Speichern',
          description: error.detail || 'Ein Fehler ist aufgetreten',
          variant: 'destructive',
        });
      }
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Verbindungsfehler beim Speichern',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Betrags-Freigabestufen</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Betrags-Freigabestufen</CardTitle>
        <p className="text-sm text-muted-foreground mt-2">
          Konfigurieren Sie bis zu 5 Betrags-Freigabestufen für automatische
          und halb-automatische Genehmigungen.
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {tiers.map((tier, index) => (
            <div
              key={index}
              className="grid grid-cols-5 gap-3 items-end p-3 border rounded-lg bg-muted/30"
            >
              {/* Tier Name */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground">
                  Name
                </label>
                <Input
                  value={tier.name}
                  onChange={(e) => handleTierChange(index, 'name', e.target.value)}
                  placeholder="z.B. Automatisch"
                  className="mt-1"
                />
              </div>

              {/* Max Amount */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground">
                  Obergrenze (EUR)
                </label>
                <Input
                  value={tier.max_amount}
                  onChange={(e) =>
                    handleTierChange(index, 'max_amount', e.target.value)
                  }
                  placeholder="z.B. 500.00"
                  type="number"
                  step="0.01"
                  min="0"
                  className="mt-1"
                />
              </div>

              {/* Approval Mode */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground">
                  Freigabemodus
                </label>
                <Select
                  value={tier.approval_mode}
                  onValueChange={(value) =>
                    handleTierChange(index, 'approval_mode', value)
                  }
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Automatisch</SelectItem>
                    <SelectItem value="one_click">Ein-Klick</SelectItem>
                    <SelectItem value="explicit">Explizit</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Min Trust Level */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground">
                  Min. Trust-Level
                </label>
                <Select
                  value={tier.min_trust_level}
                  onValueChange={(value) =>
                    handleTierChange(index, 'min_trust_level', value)
                  }
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="assistance">Assistenz</SelectItem>
                    <SelectItem value="auto_accept">Auto-Accept</SelectItem>
                    <SelectItem value="confidence">Vertrauen</SelectItem>
                    <SelectItem value="autonomous">Autonom</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Delete Button */}
              <div className="pt-6">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemoveTier(index)}
                  disabled={tiers.length <= 2}
                  className="w-full"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}

          {/* Add Tier Button */}
          {tiers.length < 5 && (
            <Button
              variant="outline"
              onClick={handleAddTier}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              Stufe hinzufügen
            </Button>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 pt-4 border-t">
            <Button
              onClick={handleSave}
              disabled={!isModified || saving}
              className="flex-1"
            >
              {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {saving ? 'Speichern...' : 'Speichern'}
            </Button>
            <Button
              variant="outline"
              onClick={loadTiers}
              disabled={!isModified || saving}
              className="flex-1"
            >
              Zur&uuml;cksetzen
            </Button>
          </div>

          {/* Info Text */}
          <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-900">
            <p className="font-semibold mb-1">Informationen:</p>
            <ul className="list-disc list-inside space-y-1 text-xs">
              <li>
                <strong>Automatisch:</strong> Beträge werden sofort freigegeben,
                wenn das Trust-Level ausreicht
              </li>
              <li>
                <strong>Ein-Klick:</strong> Ein-Klick-Bestätigung durch den User
              </li>
              <li>
                <strong>Explizit:</strong> Explizite manuelle Prüfung erforderlich
              </li>
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
