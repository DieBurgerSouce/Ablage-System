/**
 * NodeConfigPanel Component
 *
 * Configuration panel for selected workflow nodes.
 * Shows relevant settings based on node type.
 *
 * Phase 3.2 der Feature-Roadmap (Januar 2026)
 */

import { type Node } from 'reactflow';
import { Settings, Zap, Filter, GitBranch, GitFork, Repeat, Timer, X, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface NodeConfigPanelProps {
  selectedNode: Node | null;
  onNodeUpdate: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  disabled?: boolean;
  className?: string;
}

// ==================== Type Helpers ====================

/**
 * Type-safe getter for string properties with fallback
 */
function getString(data: Record<string, unknown>, key: string, fallback: string): string {
  const value = data[key];
  return typeof value === 'string' ? value : fallback;
}

/**
 * Type-safe getter for number properties with fallback
 */
function getNumber(data: Record<string, unknown>, key: string, fallback: number): number {
  const value = data[key];
  return typeof value === 'number' && !Number.isNaN(value) ? value : fallback;
}

/**
 * Type-safe getter for boolean properties with fallback
 */
function getBoolean(data: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const value = data[key];
  return typeof value === 'boolean' ? value : fallback;
}

/**
 * Type-safe getter for object/config properties with fallback
 */
function getConfig(data: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = data[key];
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * Type-safe getter for string array properties
 */
function getStringArray(data: Record<string, unknown>, key: string): string[] {
  const value = data[key];
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  return [];
}

// ==================== Icon Map ====================

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  trigger: Zap,
  condition: Filter,
  branch: GitBranch,
  delay: Timer,
  parallel: GitFork,
  loop: Repeat,
  action: Settings,
};

// ==================== Config Forms ====================

interface TriggerConfigProps {
  data: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
  disabled?: boolean;
}

function TriggerConfig({ data, onChange, disabled }: TriggerConfigProps) {
  const triggerType = getString(data, 'triggerType', 'manual');
  const config = getConfig(data, 'config');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="trigger-type">Trigger-Typ</Label>
        <Select
          value={triggerType}
          onValueChange={(value) => onChange({ ...data, triggerType: value })}
          disabled={disabled}
        >
          <SelectTrigger id="trigger-type">
            <SelectValue placeholder="Typ wählen" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="document_event">Dokument-Event</SelectItem>
            <SelectItem value="schedule">Zeitplan</SelectItem>
            <SelectItem value="webhook">Webhook</SelectItem>
            <SelectItem value="manual">Manuell</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {triggerType === 'document_event' && (
        <div className="space-y-2">
          <Label htmlFor="events">Events</Label>
          <Select
            value={getStringArray(config, 'events')[0] || 'created'}
            onValueChange={(value) =>
              onChange({
                ...data,
                config: { ...config, events: [value] },
              })
            }
            disabled={disabled}
          >
            <SelectTrigger id="events">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created">Erstellt</SelectItem>
              <SelectItem value="updated">Aktualisiert</SelectItem>
              <SelectItem value="deleted">Gelöscht</SelectItem>
              <SelectItem value="ocr_completed">OCR abgeschlossen</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {triggerType === 'schedule' && (
        <div className="space-y-2">
          <Label htmlFor="cron">Cron-Ausdruck</Label>
          <Input
            id="cron"
            value={getString(config, 'cron', '0 9 * * *')}
            onChange={(e) =>
              onChange({
                ...data,
                config: { ...config, cron: e.target.value },
              })
            }
            placeholder="0 9 * * *"
            disabled={disabled}
          />
          <p className="text-xs text-muted-foreground">
            Beispiel: 0 9 * * * = Täglich um 9 Uhr
          </p>
        </div>
      )}

      {triggerType === 'webhook' && (
        <div className="space-y-2">
          <Label htmlFor="webhook-path">Webhook-Pfad</Label>
          <Input
            id="webhook-path"
            value={getString(config, 'webhook_path', '')}
            onChange={(e) =>
              onChange({
                ...data,
                config: { ...config, webhook_path: e.target.value },
              })
            }
            placeholder="/api/trigger/my-workflow"
            disabled={disabled}
          />
        </div>
      )}

      <div className="flex items-center justify-between">
        <Label htmlFor="is-active">Aktiv</Label>
        <Switch
          id="is-active"
          checked={getBoolean(data, 'isActive', true)}
          onCheckedChange={(checked) => onChange({ ...data, isActive: checked })}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

function ConditionConfig({ data, onChange, disabled }: TriggerConfigProps) {
  const config = getConfig(data, 'config');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Bedingungslogik</Label>
        <Select
          value={getString(getConfig(config, 'conditions'), 'operator', 'AND')}
          onValueChange={(value) =>
            onChange({
              ...data,
              config: {
                ...config,
                conditions: {
                  ...getConfig(config, 'conditions'),
                  operator: value,
                },
              },
            })
          }
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="AND">Alle Bedingungen (UND)</SelectItem>
            <SelectItem value="OR">Eine Bedingung (ODER)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border border-dashed p-4 text-center">
        <Info className="mx-auto h-8 w-8 text-muted-foreground" />
        <p className="mt-2 text-sm text-muted-foreground">
          Erweiterte Bedingungsregeln können im Detail-Editor konfiguriert werden.
        </p>
      </div>
    </div>
  );
}

function DelayConfig({ data, onChange, disabled }: TriggerConfigProps) {
  const config = getConfig(data, 'config');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="delay-seconds">Verzögerung (Sekunden)</Label>
        <Input
          id="delay-seconds"
          type="number"
          min="1"
          value={getNumber(config, 'delay_seconds', 60)}
          onChange={(e) =>
            onChange({
              ...data,
              config: { ...config, delay_seconds: parseInt(e.target.value, 10) },
            })
          }
          disabled={disabled}
        />
        <p className="text-xs text-muted-foreground">
          Workflow pausiert für diese Zeit
        </p>
      </div>
    </div>
  );
}

function LoopConfig({ data, onChange, disabled }: TriggerConfigProps) {
  const config = getConfig(data, 'config');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Schleifen-Typ</Label>
        <Select
          value={getString(config, 'loop_type', 'count')}
          onValueChange={(value) =>
            onChange({
              ...data,
              config: { ...config, loop_type: value },
            })
          }
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="count">Anzahl Durchläufe</SelectItem>
            <SelectItem value="while">Solange (While)</SelectItem>
            <SelectItem value="for_each">Für jeden (For Each)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {getString(config, 'loop_type', 'count') === 'count' && (
        <div className="space-y-2">
          <Label htmlFor="count">Anzahl</Label>
          <Input
            id="count"
            type="number"
            min="1"
            max="100"
            value={getNumber(config, 'count', 3)}
            onChange={(e) =>
              onChange({
                ...data,
                config: { ...config, count: parseInt(e.target.value, 10) },
              })
            }
            disabled={disabled}
          />
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor="max-iterations">Max. Iterationen</Label>
        <Input
          id="max-iterations"
          type="number"
          min="1"
          max="1000"
          value={getNumber(config, 'max_iterations', 100)}
          onChange={(e) =>
            onChange({
              ...data,
              config: { ...config, max_iterations: parseInt(e.target.value, 10) },
            })
          }
          disabled={disabled}
        />
      </div>
    </div>
  );
}

function ActionConfig({ data, onChange, disabled }: TriggerConfigProps) {
  const config = getConfig(data, 'config');
  const actionType = getString(config, 'action_type', 'move_folder');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Aktionstyp</Label>
        <Select
          value={actionType}
          onValueChange={(value) =>
            onChange({
              ...data,
              config: { ...config, action_type: value },
            })
          }
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="move_folder">Ordner verschieben</SelectItem>
            <SelectItem value="assign_tags">Tags zuweisen</SelectItem>
            <SelectItem value="send_notification">Benachrichtigung</SelectItem>
            <SelectItem value="send_email">E-Mail senden</SelectItem>
            <SelectItem value="start_ocr">OCR starten</SelectItem>
            <SelectItem value="ai_categorization">KI-Kategorisierung</SelectItem>
            <SelectItem value="call_webhook">Webhook aufrufen</SelectItem>
            <SelectItem value="http_request">HTTP-Request</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {actionType === 'send_email' && (
        <>
          <div className="space-y-2">
            <Label htmlFor="email-to">Empfänger</Label>
            <Input
              id="email-to"
              type="email"
              value={getStringArray(config, 'to')[0] || ''}
              onChange={(e) =>
                onChange({
                  ...data,
                  config: { ...config, to: [e.target.value] },
                })
              }
              placeholder="empfänger@beispiel.de"
              disabled={disabled}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email-subject">Betreff</Label>
            <Input
              id="email-subject"
              value={getString(config, 'subject', '')}
              onChange={(e) =>
                onChange({
                  ...data,
                  config: { ...config, subject: e.target.value },
                })
              }
              placeholder="Workflow-Benachrichtigung"
              disabled={disabled}
            />
          </div>
        </>
      )}

      {actionType === 'http_request' && (
        <>
          <div className="space-y-2">
            <Label>HTTP-Methode</Label>
            <Select
              value={getString(config, 'method', 'POST')}
              onValueChange={(value) =>
                onChange({
                  ...data,
                  config: { ...config, method: value },
                })
              }
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="GET">GET</SelectItem>
                <SelectItem value="POST">POST</SelectItem>
                <SelectItem value="PUT">PUT</SelectItem>
                <SelectItem value="PATCH">PATCH</SelectItem>
                <SelectItem value="DELETE">DELETE</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="http-url">URL</Label>
            <Input
              id="http-url"
              value={getString(config, 'url', '')}
              onChange={(e) =>
                onChange({
                  ...data,
                  config: { ...config, url: e.target.value },
                })
              }
              placeholder="https://api.example.com/webhook"
              disabled={disabled}
            />
          </div>
        </>
      )}

      {actionType === 'start_ocr' && (
        <div className="space-y-2">
          <Label>OCR-Backend</Label>
          <Select
            value={getString(config, 'backend', 'auto')}
            onValueChange={(value) =>
              onChange({
                ...data,
                config: { ...config, backend: value },
              })
            }
            disabled={disabled}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Automatisch</SelectItem>
              <SelectItem value="deepseek">DeepSeek-Janus</SelectItem>
              <SelectItem value="got-ocr">GOT-OCR 2.0</SelectItem>
              <SelectItem value="surya">Surya + Docling</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}

// ==================== NodeConfigPanel ====================

export function NodeConfigPanel({
  selectedNode,
  onNodeUpdate,
  onClose,
  disabled,
  className,
}: NodeConfigPanelProps) {
  if (!selectedNode) {
    return (
      <aside
        className={cn(
          'flex h-full w-80 flex-col border-l bg-background',
          className
        )}
      >
        <div className="flex h-full items-center justify-center p-4 text-center">
          <div>
            <Settings className="mx-auto h-12 w-12 text-muted-foreground/50" />
            <p className="mt-4 text-sm text-muted-foreground">
              Wählen Sie einen Knoten aus, um ihn zu konfigurieren
            </p>
          </div>
        </div>
      </aside>
    );
  }

  const nodeType = selectedNode.type || 'action';
  // Safely extract nodeData with type validation
  const nodeData: Record<string, unknown> =
    selectedNode.data !== null && typeof selectedNode.data === 'object' && !Array.isArray(selectedNode.data)
      ? (selectedNode.data as Record<string, unknown>)
      : {};
  const Icon = iconMap[nodeType] || Settings;

  const handleDataChange = (newData: Record<string, unknown>) => {
    onNodeUpdate(selectedNode.id, newData);
  };

  return (
    <aside
      className={cn(
        'flex h-full w-80 flex-col border-l bg-background',
        className
      )}
      role="complementary"
      aria-label="Knoten-Konfiguration"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">
              {getString(nodeData, 'label', 'Knoten')}
            </h2>
            <p className="text-xs text-muted-foreground capitalize">
              {nodeType}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="Konfiguration schließen"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <Tabs defaultValue="config" className="p-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="config">Konfiguration</TabsTrigger>
            <TabsTrigger value="advanced">Erweitert</TabsTrigger>
          </TabsList>

          <TabsContent value="config" className="mt-4 space-y-4">
            {/* Label */}
            <div className="space-y-2">
              <Label htmlFor="node-label">Bezeichnung</Label>
              <Input
                id="node-label"
                value={getString(nodeData, 'label', '')}
                onChange={(e) =>
                  handleDataChange({ ...nodeData, label: e.target.value })
                }
                placeholder="Knoten-Bezeichnung"
                disabled={disabled}
              />
            </div>

            <Separator />

            {/* Type-specific config */}
            {nodeType === 'trigger' && (
              <TriggerConfig
                data={nodeData}
                onChange={handleDataChange}
                disabled={disabled}
              />
            )}

            {nodeType === 'condition' && (
              <ConditionConfig
                data={nodeData}
                onChange={handleDataChange}
                disabled={disabled}
              />
            )}

            {nodeType === 'delay' && (
              <DelayConfig
                data={nodeData}
                onChange={handleDataChange}
                disabled={disabled}
              />
            )}

            {nodeType === 'loop' && (
              <LoopConfig
                data={nodeData}
                onChange={handleDataChange}
                disabled={disabled}
              />
            )}

            {nodeType === 'action' && (
              <ActionConfig
                data={nodeData}
                onChange={handleDataChange}
                disabled={disabled}
              />
            )}

            {(nodeType === 'branch' || nodeType === 'parallel') && (
              <div className="rounded-lg border border-dashed p-4 text-center">
                <Info className="mx-auto h-8 w-8 text-muted-foreground" />
                <p className="mt-2 text-sm text-muted-foreground">
                  Konfiguration im Detail-Editor verfügbar
                </p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="advanced" className="mt-4 space-y-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Fehlerbehandlung</CardTitle>
                <CardDescription>
                  Verhalten bei Fehlern
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label htmlFor="retry-on-failure">Bei Fehler wiederholen</Label>
                  <Switch
                    id="retry-on-failure"
                    checked={getBoolean(nodeData, 'retryOnFailure', false)}
                    onCheckedChange={(checked) =>
                      handleDataChange({ ...nodeData, retryOnFailure: checked })
                    }
                    disabled={disabled}
                  />
                </div>

                {getBoolean(nodeData, 'retryOnFailure', false) && (
                  <div className="space-y-2">
                    <Label htmlFor="max-retries">Max. Versuche</Label>
                    <Input
                      id="max-retries"
                      type="number"
                      min="1"
                      max="10"
                      value={getNumber(nodeData, 'maxRetries', 3)}
                      onChange={(e) =>
                        handleDataChange({
                          ...nodeData,
                          maxRetries: parseInt(e.target.value, 10),
                        })
                      }
                      disabled={disabled}
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Timeout</CardTitle>
                <CardDescription>
                  Maximale Ausführungszeit
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Label htmlFor="timeout">Timeout (Sekunden)</Label>
                  <Input
                    id="timeout"
                    type="number"
                    min="1"
                    max="3600"
                    value={getNumber(nodeData, 'timeout', 300)}
                    onChange={(e) =>
                      handleDataChange({
                        ...nodeData,
                        timeout: parseInt(e.target.value, 10),
                      })
                    }
                    disabled={disabled}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Notizen</CardTitle>
                <CardDescription>
                  Interne Dokumentation
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={getString(nodeData, 'notes', '')}
                  onChange={(e) =>
                    handleDataChange({ ...nodeData, notes: e.target.value })
                  }
                  placeholder="Notizen zum Knoten..."
                  rows={3}
                  disabled={disabled}
                />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-mono text-[10px]">
            {selectedNode.id.slice(0, 12)}...
          </Badge>
          <span>Position: {Math.round(selectedNode.position.x)}, {Math.round(selectedNode.position.y)}</span>
        </div>
      </div>
    </aside>
  );
}

export default NodeConfigPanel;
