/**
 * NodePalette Component
 *
 * Draggable node palette for the WorkflowBuilder.
 * Supports drag-and-drop onto the ReactFlow canvas.
 *
 * Phase 3.2 der Feature-Roadmap (Januar 2026)
 */

import { type DragEvent } from 'react';
import {
  Zap,
  FileText,
  Clock,
  Webhook,
  Play,
  Filter,
  GitBranch,
  GitFork,
  Repeat,
  FolderOpen,
  Tag,
  Bell,
  Mail,
  ScanLine,
  Brain,
  Globe,
  Timer,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// ==================== Types ====================

export interface NodeTemplate {
  /** Unique identifier for this template (used as React key) */
  id: string;
  type: string;
  label: string;
  description: string;
  icon: string;
  category: 'trigger' | 'logic' | 'action';
  color: string;
  defaultData: Record<string, unknown>;
}

interface NodePaletteProps {
  onDragStart?: (event: DragEvent, template: NodeTemplate) => void;
  disabled?: boolean;
  className?: string;
}

// ==================== Node Templates ====================

export const nodeTemplates: NodeTemplate[] = [
  // === Triggers ===
  {
    id: 'trigger-document-event',
    type: 'trigger',
    label: 'Dokument-Event',
    description: 'Startet bei Dokument-Erstellung, -Änderung oder -Löschung',
    icon: 'file-text',
    category: 'trigger',
    color: 'bg-blue-500',
    defaultData: {
      triggerType: 'document_event',
      config: { events: ['created'] },
      isActive: true,
    },
  },
  {
    id: 'trigger-schedule',
    type: 'trigger',
    label: 'Zeitplan',
    description: 'Startet nach festem Zeitplan (Cron)',
    icon: 'clock',
    category: 'trigger',
    color: 'bg-blue-500',
    defaultData: {
      triggerType: 'schedule',
      config: { cron: '0 9 * * *' },
      isActive: true,
    },
  },
  {
    id: 'trigger-webhook',
    type: 'trigger',
    label: 'Webhook',
    description: 'Startet durch externe HTTP-Anfrage',
    icon: 'webhook',
    category: 'trigger',
    color: 'bg-blue-500',
    defaultData: {
      triggerType: 'webhook',
      config: { webhook_path: '/trigger' },
      isActive: true,
    },
  },
  {
    id: 'trigger-manual',
    type: 'trigger',
    label: 'Manuell',
    description: 'Startet durch manuellen Klick',
    icon: 'play',
    category: 'trigger',
    color: 'bg-blue-500',
    defaultData: {
      triggerType: 'manual',
      config: {},
      isActive: true,
    },
  },
  // === Logic ===
  {
    id: 'logic-condition',
    type: 'condition',
    label: 'Bedingung',
    description: 'Prüft Bedingungen und verzweigt entsprechend',
    icon: 'filter',
    category: 'logic',
    color: 'bg-amber-500',
    defaultData: {
      config: { conditions: { operator: 'AND', rules: [] } },
    },
  },
  {
    id: 'logic-branch',
    type: 'branch',
    label: 'Verzweigung',
    description: 'Mehrere Pfade basierend auf Werten',
    icon: 'git-branch',
    category: 'logic',
    color: 'bg-amber-500',
    defaultData: {
      config: { branches: [], default_branch: 'default' },
    },
  },
  {
    id: 'logic-delay',
    type: 'delay',
    label: 'Verzögerung',
    description: 'Wartet eine bestimmte Zeit',
    icon: 'timer',
    category: 'logic',
    color: 'bg-amber-500',
    defaultData: {
      config: { delay_seconds: 60 },
    },
  },
  {
    id: 'logic-parallel',
    type: 'parallel',
    label: 'Parallel',
    description: 'Führt mehrere Schritte gleichzeitig aus',
    icon: 'git-fork',
    category: 'logic',
    color: 'bg-amber-500',
    defaultData: {
      config: { steps: [] },
    },
  },
  {
    id: 'logic-loop',
    type: 'loop',
    label: 'Schleife',
    description: 'Wiederholt Schritte mehrfach',
    icon: 'repeat',
    category: 'logic',
    color: 'bg-amber-500',
    defaultData: {
      config: { loop_type: 'count', count: 3 },
    },
  },
  // === Actions ===
  {
    id: 'action-move-folder',
    type: 'action',
    label: 'Ordner verschieben',
    description: 'Verschiebt Dokument in einen Ordner',
    icon: 'folder',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'move_folder' },
    },
  },
  {
    id: 'action-assign-tags',
    type: 'action',
    label: 'Tags zuweisen',
    description: 'Weist Tags dem Dokument zu',
    icon: 'tag',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'assign_tags', tag_names: [] },
    },
  },
  {
    id: 'action-notification',
    type: 'action',
    label: 'Benachrichtigung',
    description: 'Sendet In-App Benachrichtigung',
    icon: 'bell',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'send_notification' },
    },
  },
  {
    id: 'action-send-email',
    type: 'action',
    label: 'E-Mail senden',
    description: 'Sendet E-Mail an Empfänger',
    icon: 'mail',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'send_email' },
    },
  },
  {
    id: 'action-start-ocr',
    type: 'action',
    label: 'OCR starten',
    description: 'Startet OCR-Verarbeitung',
    icon: 'scan',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'start_ocr', backend: 'auto' },
    },
  },
  {
    id: 'action-ai-categorization',
    type: 'action',
    label: 'KI-Kategorisierung',
    description: 'Kategorisiert mit KI automatisch',
    icon: 'brain',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'ai_categorization' },
    },
  },
  {
    id: 'action-call-webhook',
    type: 'action',
    label: 'Webhook aufrufen',
    description: 'Ruft externen Webhook auf',
    icon: 'webhook',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'call_webhook' },
    },
  },
  {
    id: 'action-http-request',
    type: 'action',
    label: 'HTTP-Request',
    description: 'Sendet HTTP-Anfrage an URL',
    icon: 'globe',
    category: 'action',
    color: 'bg-green-500',
    defaultData: {
      config: { action_type: 'http_request', method: 'POST' },
    },
  },
];

// ==================== Icon Map ====================

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  'file-text': FileText,
  'clock': Clock,
  'webhook': Webhook,
  'play': Play,
  'filter': Filter,
  'git-branch': GitBranch,
  'timer': Timer,
  'git-fork': GitFork,
  'repeat': Repeat,
  'folder': FolderOpen,
  'tag': Tag,
  'bell': Bell,
  'mail': Mail,
  'scan': ScanLine,
  'brain': Brain,
  'globe': Globe,
  'zap': Zap,
};

// ==================== Draggable Node ====================

interface DraggableNodeProps {
  template: NodeTemplate;
  onDragStart?: (event: DragEvent, template: NodeTemplate) => void;
  disabled?: boolean;
}

function DraggableNode({ template, onDragStart, disabled }: DraggableNodeProps) {
  const Icon = iconMap[template.icon] || Zap;

  const handleDragStart = (event: DragEvent) => {
    if (disabled) return;

    // Set drag data for ReactFlow
    event.dataTransfer.setData('application/reactflow', JSON.stringify(template));
    event.dataTransfer.effectAllowed = 'move';

    onDragStart?.(event, template);
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            draggable={!disabled}
            onDragStart={handleDragStart}
            className={cn(
              'flex items-center gap-3 rounded-lg border bg-card p-3',
              'transition-all duration-200',
              disabled
                ? 'cursor-not-allowed opacity-50'
                : 'cursor-grab hover:bg-accent hover:shadow-md active:cursor-grabbing active:shadow-lg',
              'select-none'
            )}
            role="button"
            tabIndex={disabled ? -1 : 0}
            aria-label={`${template.label} - ${template.description}. Ziehen zum Hinzufügen.`}
            aria-disabled={disabled}
          >
            <div
              className={cn(
                'flex h-9 w-9 shrink-0 items-center justify-center rounded-md',
                template.color
              )}
            >
              <Icon className="h-5 w-5 text-white" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{template.label}</p>
              <p className="truncate text-xs text-muted-foreground">
                {template.description}
              </p>
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-xs">
          <p className="font-medium">{template.label}</p>
          <p className="text-xs text-muted-foreground">{template.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== NodePalette ====================

export function NodePalette({ onDragStart, disabled, className }: NodePaletteProps) {
  const triggers = nodeTemplates.filter((t) => t.category === 'trigger');
  const logic = nodeTemplates.filter((t) => t.category === 'logic');
  const actions = nodeTemplates.filter((t) => t.category === 'action');

  return (
    <aside
      className={cn(
        'flex h-full w-64 flex-col border-r bg-background',
        className
      )}
      role="complementary"
      aria-label="Knoten-Palette - Ziehen Sie Elemente auf die Zeichenflaeche"
    >
      <div className="border-b p-4">
        <h2 className="text-sm font-semibold">Knoten-Palette</h2>
        <p className="text-xs text-muted-foreground">
          Ziehen Sie Elemente auf die Zeichenflaeche
        </p>
      </div>

      <ScrollArea className="flex-1">
        <Accordion
          type="multiple"
          defaultValue={['trigger', 'logic', 'action']}
          className="p-2"
        >
          {/* Triggers */}
          <AccordionItem value="trigger" className="border-none">
            <AccordionTrigger className="rounded-md px-2 py-2 hover:bg-accent hover:no-underline">
              <span className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-blue-500" aria-hidden="true" />
                <span className="text-sm font-medium">Trigger</span>
                <span className="text-xs text-muted-foreground">({triggers.length})</span>
              </span>
            </AccordionTrigger>
            <AccordionContent className="space-y-2 pb-2 pt-1">
              {triggers.map((template) => (
                <DraggableNode
                  key={template.id}
                  template={template}
                  onDragStart={onDragStart}
                  disabled={disabled}
                />
              ))}
            </AccordionContent>
          </AccordionItem>

          {/* Logic */}
          <AccordionItem value="logic" className="border-none">
            <AccordionTrigger className="rounded-md px-2 py-2 hover:bg-accent hover:no-underline">
              <span className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
                <span className="text-sm font-medium">Logik</span>
                <span className="text-xs text-muted-foreground">({logic.length})</span>
              </span>
            </AccordionTrigger>
            <AccordionContent className="space-y-2 pb-2 pt-1">
              {logic.map((template) => (
                <DraggableNode
                  key={template.id}
                  template={template}
                  onDragStart={onDragStart}
                  disabled={disabled}
                />
              ))}
            </AccordionContent>
          </AccordionItem>

          {/* Actions */}
          <AccordionItem value="action" className="border-none">
            <AccordionTrigger className="rounded-md px-2 py-2 hover:bg-accent hover:no-underline">
              <span className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
                <span className="text-sm font-medium">Aktionen</span>
                <span className="text-xs text-muted-foreground">({actions.length})</span>
              </span>
            </AccordionTrigger>
            <AccordionContent className="space-y-2 pb-2 pt-1">
              {actions.map((template) => (
                <DraggableNode
                  key={template.id}
                  template={template}
                  onDragStart={onDragStart}
                  disabled={disabled}
                />
              ))}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </ScrollArea>

      <div className="border-t p-4">
        <p className="text-xs text-muted-foreground">
          Tipp: Verbinden Sie Knoten durch Ziehen von einem Handle zum anderen
        </p>
      </div>
    </aside>
  );
}

export default NodePalette;
