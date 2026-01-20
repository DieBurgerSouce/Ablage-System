/**
 * BPMN Palette Component
 *
 * Drag & drop palette for adding BPMN elements to the process.
 */

import { cn } from '@/lib/utils';
import {
  Play,
  Square,
  User,
  Cog,
  Code,
  Hand,
  Send,
  Inbox,
  BookOpen,
  X,
  Plus,
  Circle,
  Zap,
  Clock,
  Mail,
} from 'lucide-react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';

interface PaletteItem {
  type: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

interface PaletteCategory {
  title: string;
  items: PaletteItem[];
}

const paletteCategories: PaletteCategory[] = [
  {
    title: 'Ereignisse',
    items: [
      {
        type: 'startEvent',
        label: 'Start-Ereignis',
        icon: Play,
        description: 'Startet den Prozess',
      },
      {
        type: 'endEvent',
        label: 'End-Ereignis',
        icon: Square,
        description: 'Beendet den Prozess',
      },
    ],
  },
  {
    title: 'Aufgaben',
    items: [
      {
        type: 'userTask',
        label: 'Benutzer-Aufgabe',
        icon: User,
        description: 'Manuelle Aufgabe fuer Benutzer',
      },
      {
        type: 'serviceTask',
        label: 'Service-Aufgabe',
        icon: Cog,
        description: 'Automatische Service-Ausfuehrung',
      },
      {
        type: 'scriptTask',
        label: 'Script-Aufgabe',
        icon: Code,
        description: 'Fuehrt ein Script aus',
      },
      {
        type: 'manualTask',
        label: 'Manuelle Aufgabe',
        icon: Hand,
        description: 'Offline-Aufgabe ohne System',
      },
      {
        type: 'sendTask',
        label: 'Sende-Aufgabe',
        icon: Send,
        description: 'Sendet eine Nachricht',
      },
      {
        type: 'receiveTask',
        label: 'Empfangs-Aufgabe',
        icon: Inbox,
        description: 'Wartet auf Nachricht',
      },
      {
        type: 'businessRuleTask',
        label: 'Geschaeftsregel',
        icon: BookOpen,
        description: 'Wertet Geschaeftsregeln aus',
      },
    ],
  },
  {
    title: 'Gateways',
    items: [
      {
        type: 'exclusiveGateway',
        label: 'Exklusiv (XOR)',
        icon: X,
        description: 'Genau ein Pfad wird gewaehlt',
      },
      {
        type: 'parallelGateway',
        label: 'Parallel (AND)',
        icon: Plus,
        description: 'Alle Pfade parallel',
      },
      {
        type: 'inclusiveGateway',
        label: 'Inklusiv (OR)',
        icon: Circle,
        description: 'Ein oder mehrere Pfade',
      },
      {
        type: 'eventBasedGateway',
        label: 'Ereignis-basiert',
        icon: Zap,
        description: 'Wartet auf Ereignis',
      },
    ],
  },
];

interface BpmnPaletteProps {
  className?: string;
}

export function BpmnPalette({ className }: BpmnPaletteProps) {
  const onDragStart = (
    event: React.DragEvent,
    nodeType: string
  ) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className={cn('bg-white p-4 overflow-y-auto', className)}>
      <h3 className="mb-4 text-sm font-semibold text-gray-700">
        BPMN Elemente
      </h3>
      <Accordion type="multiple" defaultValue={['Ereignisse', 'Aufgaben', 'Gateways']}>
        {paletteCategories.map((category) => (
          <AccordionItem key={category.title} value={category.title}>
            <AccordionTrigger className="text-sm">
              {category.title}
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-2">
                {category.items.map((item) => (
                  <div
                    key={item.type}
                    draggable
                    onDragStart={(e) => onDragStart(e, item.type)}
                    className={cn(
                      'flex cursor-grab items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-2 transition-all',
                      'hover:border-blue-300 hover:bg-blue-50 hover:shadow-sm',
                      'active:cursor-grabbing'
                    )}
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded bg-white shadow-sm">
                      <item.icon className="h-4 w-4 text-gray-600" />
                    </div>
                    <div className="flex-1 overflow-hidden">
                      <p className="truncate text-sm font-medium text-gray-800">
                        {item.label}
                      </p>
                      <p className="truncate text-xs text-gray-500">
                        {item.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      <div className="mt-6 rounded-lg bg-blue-50 p-3 text-xs text-blue-700">
        <p className="font-medium">Tipp:</p>
        <p className="mt-1">
          Ziehen Sie Elemente auf die Zeichenflaeche und verbinden Sie sie
          durch Klicken und Ziehen zwischen den Ankerpunkten.
        </p>
      </div>
    </div>
  );
}

export default BpmnPalette;
