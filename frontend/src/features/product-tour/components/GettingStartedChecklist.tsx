/**
 * Getting Started Checklist - Standalone Onboarding-Checkliste
 *
 * Trackt Erstbenutzer-Aktionen via localStorage.
 * Zeigt Fortschritt und verlinkt zu den jeweiligen Bereichen.
 * Verschwindet automatisch nach Abschluss aller Schritte.
 */

import { useCallback, useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import { useLocalStorage } from '@/hooks/use-local-storage';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import {
  CheckCircle2,
  Circle,
  ChevronRight,
  X,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChecklistListener } from '../hooks/use-checklist-events';

const CHECKLIST_STORAGE_KEY = 'ablage-getting-started';
const CHECKLIST_DISMISSED_KEY = 'ablage-getting-started-dismissed';

interface ChecklistItem {
  id: string;
  label: string;
  description: string;
  route: string;
}

const CHECKLIST_ITEMS: ChecklistItem[] = [
  {
    id: 'view_dashboard',
    label: 'Dashboard ansehen',
    description: 'Verschaffen Sie sich einen Ueberblick',
    route: '/',
  },
  {
    id: 'upload_document',
    label: 'Dokument hochladen',
    description: 'Laden Sie Ihr erstes Dokument hoch',
    route: '/upload',
  },
  {
    id: 'search_document',
    label: 'Suche ausprobieren',
    description: 'Finden Sie ein Dokument per Suche',
    route: '/smart-search',
  },
  {
    id: 'view_invoices',
    label: 'Rechnungen pruefen',
    description: 'Sehen Sie Ihre Rechnungsuebersicht',
    route: '/invoice-workflow',
  },
  {
    id: 'configure_settings',
    label: 'Einstellungen anpassen',
    description: 'Passen Sie das System an Ihre Beduerfnisse an',
    route: '/settings',
  },
  {
    id: 'create_workflow',
    label: 'Workflow erstellen',
    description: 'Erstellen Sie Ihren ersten Workflow',
    route: '/workflow-builder',
  },
  {
    id: 'explore_knowledge_graph',
    label: 'Wissens-Graph erkunden',
    description: 'Visualisieren Sie Dokumenten-Beziehungen',
    route: '/knowledge-graph',
  },
  {
    id: 'create_annotation',
    label: 'Annotation erstellen',
    description: 'Kommentieren Sie ein Dokument',
    route: '/documents',
  },
];

interface CompletedState {
  [itemId: string]: boolean;
}

export function useGettingStartedChecklist() {
  const [completed, setCompleted] = useLocalStorage<CompletedState>(
    CHECKLIST_STORAGE_KEY,
    {},
  );
  const [isDismissed, setIsDismissed] = useLocalStorage<boolean>(
    CHECKLIST_DISMISSED_KEY,
    false,
  );

  const completedCount = useMemo(
    () => CHECKLIST_ITEMS.filter((item) => completed[item.id]).length,
    [completed],
  );

  const isAllDone = completedCount === CHECKLIST_ITEMS.length;

  const markCompleted = useCallback(
    (itemId: string) => {
      setCompleted((prev) => ({ ...prev, [itemId]: true }));
    },
    [setCompleted],
  );

  // Event-driven completion: lauscht auf 'ablage:checklist-complete' Events
  useChecklistListener(markCompleted);

  const dismiss = useCallback(() => {
    setIsDismissed(true);
  }, [setIsDismissed]);

  const reset = useCallback(() => {
    setCompleted({});
    setIsDismissed(false);
  }, [setCompleted, setIsDismissed]);

  return {
    items: CHECKLIST_ITEMS,
    completed,
    completedCount,
    totalCount: CHECKLIST_ITEMS.length,
    isAllDone,
    isDismissed,
    markCompleted,
    dismiss,
    reset,
  };
}

/**
 * Compact checklist for sidebar integration
 */
export function GettingStartedChecklist() {
  const {
    items,
    completed,
    completedCount,
    totalCount,
    isAllDone,
    isDismissed,
    markCompleted,
    dismiss,
  } = useGettingStartedChecklist();

  if (isDismissed || isAllDone) {
    return null;
  }

  const progressPercent = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold">Erste Schritte</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">
            {completedCount}/{totalCount}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-5 w-5 p-0"
            onClick={dismiss}
            aria-label="Checkliste ausblenden"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      <Progress value={progressPercent} className="h-1.5" />

      <div className="space-y-0.5">
        {items.map((item) => {
          const isDone = completed[item.id];
          return (
            <Link
              key={item.id}
              to={item.route}
              onClick={() => markCompleted(item.id)}
              className={cn(
                'flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors',
                'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                isDone && 'opacity-50',
              )}
            >
              {isDone ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
              ) : (
                <Circle className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
              )}
              <span className={cn(isDone && 'line-through')}>{item.label}</span>
              {!isDone && (
                <ChevronRight className="h-3 w-3 ml-auto text-muted-foreground" />
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Minimal progress indicator (single line)
 */
export function GettingStartedMini() {
  const { completedCount, totalCount, isAllDone, isDismissed } =
    useGettingStartedChecklist();

  if (isDismissed || isAllDone) {
    return null;
  }

  const progressPercent = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="flex items-center gap-2 px-3 py-1">
      <Sparkles className="h-3 w-3 text-primary flex-shrink-0" />
      <Progress value={progressPercent} className="h-1 flex-1" />
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {completedCount}/{totalCount}
      </span>
    </div>
  );
}
