/**
 * BPMN Process Designer - New Process
 *
 * Seite zum Erstellen eines neuen BPMN-Prozesses.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useState } from 'react';
import { BpmnEditor, useDeployDefinition } from '@/features/bpmn';
import type { BPMNProcessData } from '@/features/bpmn';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { ArrowLeft, Loader2 } from 'lucide-react';

export const Route = createFileRoute('/prozesse/neu')({
  component: NewProcessPage,
});

function NewProcessPage() {
  const navigate = useNavigate();
  const deployMutation = useDeployDefinition();

  const [processData, setProcessData] = useState<BPMNProcessData | null>(null);
  const [showDeployDialog, setShowDeployDialog] = useState(false);
  const [processKey, setProcessKey] = useState('');
  const [processName, setProcessName] = useState('');
  const [processDescription, setProcessDescription] = useState('');

  const handleSave = (data: BPMNProcessData) => {
    setProcessData(data);
    toast.success('Prozess gespeichert', {
      description: 'Die Änderungen wurden lokal gespeichert.',
    });
  };

  const handleDeploy = (data: BPMNProcessData) => {
    setProcessData(data);
    setProcessName(data.name || '');
    setShowDeployDialog(true);
  };

  const handleDeployConfirm = async () => {
    if (!processData || !processKey || !processName) {
      toast.error('Bitte alle Pflichtfelder ausfüllen');
      return;
    }

    try {
      const result = await deployMutation.mutateAsync({
        process_key: processKey,
        name: processName,
        description: processDescription || undefined,
        process_data: processData,
        activate: true,
      });

      toast.success('Prozess bereitgestellt', {
        description: `${result.name} wurde erfolgreich deployed.`,
      });

      navigate({ to: '/prozesse/$definitionId', params: { definitionId: result.id } });
    } catch (error) {
      toast.error('Deployment fehlgeschlagen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    }
  };

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 border-b bg-white px-4 py-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate({ to: '/prozesse' })}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurück
        </Button>
        <div className="h-6 w-px bg-gray-200" />
        <h1 className="text-lg font-semibold text-gray-900">
          Neuen Prozess erstellen
        </h1>
      </div>

      {/* Editor */}
      <div className="flex-1">
        <BpmnEditor onSave={handleSave} onDeploy={handleDeploy} />
      </div>

      {/* Deploy Dialog */}
      <Dialog open={showDeployDialog} onOpenChange={setShowDeployDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Prozess bereitstellen</DialogTitle>
            <DialogDescription>
              Geben Sie die Details für den neuen Prozess ein.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="processKey">
                Prozess-Schlüssel <span className="text-red-500">*</span>
              </Label>
              <Input
                id="processKey"
                value={processKey}
                onChange={(e) =>
                  setProcessKey(
                    e.target.value.toLowerCase().replace(/[^a-z0-9-_]/g, '')
                  )
                }
                placeholder="rechnungsfreigabe"
              />
              <p className="text-xs text-gray-500">
                Eindeutiger Schlüssel (nur Kleinbuchstaben, Zahlen, Bindestriche)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="processName">
                Name <span className="text-red-500">*</span>
              </Label>
              <Input
                id="processName"
                value={processName}
                onChange={(e) => setProcessName(e.target.value)}
                placeholder="Rechnungsfreigabe-Workflow"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="processDescription">Beschreibung</Label>
              <Textarea
                id="processDescription"
                value={processDescription}
                onChange={(e) => setProcessDescription(e.target.value)}
                placeholder="Optionale Beschreibung des Prozesses..."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeployDialog(false)}
            >
              Abbrechen
            </Button>
            <Button
              onClick={handleDeployConfirm}
              disabled={
                deployMutation.isPending || !processKey || !processName
              }
            >
              {deployMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Bereitstellen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
