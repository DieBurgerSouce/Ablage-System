/**
 * BPMN Process Definition Detail
 *
 * Detailansicht einer Prozess-Definition.
 */

import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import {
  useDefinition,
  useInstances,
  useActivateDefinition,
  useDeactivateDefinition,
  useStartInstance,
  BpmnEditor,
} from '@/features/bpmn';
import type { ProcessStatus } from '@/features/bpmn';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Play,
  Pause,
  MoreVertical,
  Download,
  Edit,
  Trash2,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Eye,
} from 'lucide-react';

export const Route = createFileRoute('/prozesse/$definitionId')({
  component: ProcessDefinitionDetailPage,
});

function ProcessDefinitionDetailPage() {
  const { definitionId } = Route.useParams();
  const navigate = useNavigate();

  const { data: definition, isLoading } = useDefinition(definitionId);
  const { data: instances } = useInstances({ definition_id: definitionId });
  const activateMutation = useActivateDefinition();
  const deactivateMutation = useDeactivateDefinition();
  const startMutation = useStartInstance();

  const handleActivate = async () => {
    try {
      await activateMutation.mutateAsync(definitionId);
      toast.success('Prozess aktiviert');
    } catch (error) {
      toast.error('Aktivierung fehlgeschlagen');
    }
  };

  const handleDeactivate = async () => {
    try {
      await deactivateMutation.mutateAsync(definitionId);
      toast.success('Prozess deaktiviert');
    } catch (error) {
      toast.error('Deaktivierung fehlgeschlagen');
    }
  };

  const handleStartInstance = async () => {
    try {
      const instance = await startMutation.mutateAsync({
        definition_id: definitionId,
      });
      toast.success('Prozess-Instanz gestartet', {
        description: `ID: ${instance.id.slice(0, 8)}...`,
      });
    } catch (error) {
      toast.error('Start fehlgeschlagen');
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!definition) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-gray-500">
        <AlertCircle className="mb-4 h-12 w-12" />
        <p>Prozess nicht gefunden</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="mb-4 flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate({ to: '/prozesse' })}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück
          </Button>
        </div>

        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {definition.name}
              </h1>
              <Badge variant={definition.is_active ? 'default' : 'secondary'}>
                {definition.is_active ? 'Aktiv' : 'Inaktiv'}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              {definition.process_key} | Version {definition.version}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {definition.is_active ? (
              <Button onClick={handleStartInstance} disabled={startMutation.isPending}>
                {startMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Starten
              </Button>
            ) : (
              <Button onClick={handleActivate} disabled={activateMutation.isPending}>
                {activateMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Aktivieren
              </Button>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>
                  <Edit className="mr-2 h-4 w-4" />
                  Bearbeiten
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Download className="mr-2 h-4 w-4" />
                  BPMN exportieren
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {definition.is_active ? (
                  <DropdownMenuItem onClick={handleDeactivate}>
                    <Pause className="mr-2 h-4 w-4" />
                    Deaktivieren
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onClick={handleActivate}>
                    <Play className="mr-2 h-4 w-4" />
                    Aktivieren
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-red-600">
                  <Trash2 className="mr-2 h-4 w-4" />
                  Löschen
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {definition.description && (
          <p className="mt-3 text-gray-600">{definition.description}</p>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="diagram">
        <TabsList>
          <TabsTrigger value="diagram">Diagramm</TabsTrigger>
          <TabsTrigger value="instances">
            Instanzen
            {instances && instances.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {instances.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="versions">Versionen</TabsTrigger>
        </TabsList>

        <TabsContent value="diagram" className="mt-4">
          <Card>
            <CardContent className="h-[600px] p-0">
              <BpmnEditor
                initialData={definition.process_data}
                readOnly
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="instances" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Prozess-Instanzen</CardTitle>
            </CardHeader>
            <CardContent>
              {instances && instances.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Business Key</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Gestartet</TableHead>
                      <TableHead>Beendet</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {instances.map((instance) => (
                      <TableRow key={instance.id}>
                        <TableCell className="font-mono text-xs">
                          {instance.id.slice(0, 8)}...
                        </TableCell>
                        <TableCell>{instance.business_key || '-'}</TableCell>
                        <TableCell>
                          <StatusBadge status={instance.status} />
                        </TableCell>
                        <TableCell className="text-sm">
                          {instance.started_at
                            ? new Date(instance.started_at).toLocaleString('de-DE')
                            : '-'}
                        </TableCell>
                        <TableCell className="text-sm">
                          {instance.ended_at
                            ? new Date(instance.ended_at).toLocaleString('de-DE')
                            : '-'}
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm">
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="py-8 text-center text-gray-500">
                  Keine Instanzen vorhanden
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Versionshistorie</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="py-8 text-center text-gray-500">
                Version {definition.version} (aktuell)
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatusBadge({ status }: { status: ProcessStatus }) {
  const config: Record<
    ProcessStatus,
    { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ComponentType<{ className?: string }> }
  > = {
    created: { label: 'Erstellt', variant: 'secondary', icon: Clock },
    running: { label: 'Laufend', variant: 'default', icon: Play },
    suspended: { label: 'Pausiert', variant: 'outline', icon: Pause },
    completed: { label: 'Abgeschlossen', variant: 'secondary', icon: CheckCircle2 },
    terminated: { label: 'Abgebrochen', variant: 'destructive', icon: XCircle },
    failed: { label: 'Fehlgeschlagen', variant: 'destructive', icon: AlertCircle },
  };

  const { label, variant, icon: Icon } = config[status] || config.created;

  return (
    <Badge variant={variant}>
      <Icon className="mr-1 h-3 w-3" />
      {label}
    </Badge>
  );
}
