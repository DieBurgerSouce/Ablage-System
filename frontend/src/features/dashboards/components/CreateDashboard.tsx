/**
 * Create Dashboard Component
 *
 * Formular zum Erstellen eines neuen Dashboards
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ArrowLeft, Plus, LayoutTemplate } from 'lucide-react';
import { useCreateDashboard, usePresets, useCreateFromPreset } from '../hooks/useDashboards';
import { useToast } from '@/components/ui/use-toast';
import type { DashboardPreset } from '../types';

export function CreateDashboard() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [mode, setMode] = useState<'blank' | 'preset'>('blank');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);

  const { data: presets = [] } = usePresets();
  const createMutation = useCreateDashboard();
  const createFromPresetMutation = useCreateFromPreset();

  const handleCreate = async () => {
    if (!name.trim() && mode === 'blank') {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Namen ein',
        variant: 'destructive',
      });
      return;
    }

    try {
      let dashboard;

      if (mode === 'preset' && selectedPreset) {
        dashboard = await createFromPresetMutation.mutateAsync(selectedPreset);
        // Optionally update name/description if provided
        if (name.trim() || description.trim()) {
          // Would need to call update mutation here
        }
      } else {
        dashboard = await createMutation.mutateAsync({
          name: name.trim(),
          description: description.trim(),
          widgets: [],
        });
      }

      toast({
        title: 'Dashboard erstellt',
        description: 'Ihr neues Dashboard wurde erfolgreich erstellt',
      });

      navigate({ to: `/dashboards/${dashboard.id}` });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Dashboard konnte nicht erstellt werden',
        variant: 'destructive',
      });
    }
  };

  const renderPresetCard = (preset: DashboardPreset) => (
    <Card
      key={preset.id}
      className={`cursor-pointer transition-all ${
        selectedPreset === preset.id
          ? 'ring-2 ring-primary'
          : 'hover:border-primary'
      }`}
      onClick={() => setSelectedPreset(preset.id)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <CardTitle className="text-base">{preset.name}</CardTitle>
          <RadioGroupItem value={preset.id} />
        </div>
        <CardDescription className="text-xs">
          {preset.description}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {preset.widgets.length} Widgets
          </span>
          <span className="text-xs bg-muted px-2 py-1 rounded">
            {preset.role}
          </span>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <Button
        variant="ghost"
        className="mb-6"
        onClick={() => navigate({ to: '/dashboards' })}
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Zurück
      </Button>

      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Neues Dashboard erstellen</h1>
          <p className="text-muted-foreground mt-1">
            Erstellen Sie ein leeres Dashboard oder nutzen Sie eine Vorlage
          </p>
        </div>

        {/* Mode Selection */}
        <Card>
          <CardHeader>
            <CardTitle>Startpunkt wählen</CardTitle>
          </CardHeader>
          <CardContent>
            <RadioGroup value={mode} onValueChange={(v) => setMode(v as any)}>
              <div className="space-y-3">
                <div
                  className={`flex items-start p-4 rounded-lg border cursor-pointer transition-colors ${
                    mode === 'blank'
                      ? 'border-primary bg-primary/5'
                      : 'hover:border-primary/50'
                  }`}
                  onClick={() => setMode('blank')}
                >
                  <RadioGroupItem value="blank" className="mt-1" />
                  <div className="ml-3">
                    <div className="flex items-center gap-2">
                      <Plus className="h-4 w-4" />
                      <span className="font-medium">Leeres Dashboard</span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      Beginnen Sie mit einem leeren Dashboard und fügen Sie
                      Widgets nach Bedarf hinzu
                    </p>
                  </div>
                </div>

                <div
                  className={`flex items-start p-4 rounded-lg border cursor-pointer transition-colors ${
                    mode === 'preset'
                      ? 'border-primary bg-primary/5'
                      : 'hover:border-primary/50'
                  }`}
                  onClick={() => setMode('preset')}
                >
                  <RadioGroupItem value="preset" className="mt-1" />
                  <div className="ml-3">
                    <div className="flex items-center gap-2">
                      <LayoutTemplate className="h-4 w-4" />
                      <span className="font-medium">Aus Vorlage</span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      Nutzen Sie eine vorkonfigurierte Vorlage passend zu Ihrer
                      Rolle
                    </p>
                  </div>
                </div>
              </div>
            </RadioGroup>
          </CardContent>
        </Card>

        {/* Blank Dashboard Form */}
        {mode === 'blank' && (
          <Card>
            <CardHeader>
              <CardTitle>Dashboard-Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="z.B. Mein Finanz-Dashboard"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Beschreibung</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optionale Beschreibung des Dashboards"
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Preset Selection */}
        {mode === 'preset' && (
          <Card>
            <CardHeader>
              <CardTitle>Vorlage auswählen</CardTitle>
              <CardDescription>
                Wählen Sie eine Vorlage, die am besten zu Ihren Anforderungen
                passt
              </CardDescription>
            </CardHeader>
            <CardContent>
              {presets.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Vorlagen verfügbar
                </div>
              ) : (
                <RadioGroup
                  value={selectedPreset || ''}
                  onValueChange={setSelectedPreset}
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {presets.map((preset) => renderPresetCard(preset))}
                  </div>
                </RadioGroup>
              )}
            </CardContent>
          </Card>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            onClick={() => navigate({ to: '/dashboards' })}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleCreate}
            disabled={
              (mode === 'blank' && !name.trim()) ||
              (mode === 'preset' && !selectedPreset) ||
              createMutation.isPending ||
              createFromPresetMutation.isPending
            }
          >
            <Plus className="h-4 w-4 mr-2" />
            Dashboard erstellen
          </Button>
        </div>
      </div>
    </div>
  );
}
