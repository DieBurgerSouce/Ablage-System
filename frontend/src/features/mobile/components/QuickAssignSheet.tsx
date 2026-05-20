/**
 * QuickAssignSheet Component
 *
 * BottomSheet for quick document-to-entity assignment.
 *
 * Features:
 * - Search field for customer/supplier name
 * - Recent entities list (last 5 used)
 * - Suggested match from OCR detection
 * - Entity cards with assign button
 * - Touch-optimized for mobile (min 44px targets)
 *
 * All user-facing text is in German.
 * Phase 3.2 der Feature-Roadmap (Februar 2026)
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Search,
  Building2,
  Users,
  Loader2,
  UserCheck,
  Star,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { BottomSheet } from '@/components/mobile/BottomSheet';
import type { EntitySuggestion, OCRResultSummary } from '../hooks/use-scan-flow';

// ==================== Types ====================

interface QuickAssignSheetProps {
  /** Whether the sheet is open */
  open: boolean;
  /** Close handler */
  onOpenChange: (open: boolean) => void;
  /** Called when an entity is selected for assignment */
  onAssign: (entityId: string) => void;
  /** Search results from parent */
  suggestions: EntitySuggestion[];
  /** Load suggestions callback */
  onSearch: (query: string) => void;
  /** OCR result for showing suggested match */
  ocrResult: OCRResultSummary | null;
  /** Assignment in progress */
  isAssigning: boolean;
}

// ==================== Constants ====================

const RECENT_ENTITIES_KEY = 'ablage_recent_entities';
const MAX_RECENT = 5;

interface RecentEntity {
  id: string;
  name: string;
  type: 'customer' | 'supplier';
  usedAt: number;
}

// ==================== Helpers ====================

function loadRecentEntities(): RecentEntity[] {
  try {
    const stored = localStorage.getItem(RECENT_ENTITIES_KEY);
    if (!stored) return [];
    const parsed: RecentEntity[] = JSON.parse(stored);
    return parsed.sort((a, b) => b.usedAt - a.usedAt).slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function saveRecentEntity(entity: RecentEntity): void {
  try {
    const existing = loadRecentEntities().filter((e) => e.id !== entity.id);
    const updated = [{ ...entity, usedAt: Date.now() }, ...existing].slice(
      0,
      MAX_RECENT
    );
    localStorage.setItem(RECENT_ENTITIES_KEY, JSON.stringify(updated));
  } catch {
    // localStorage not available
  }
}

function getEntityTypeLabel(type: 'customer' | 'supplier'): string {
  return type === 'customer' ? 'Kunde' : 'Lieferant';
}

function getEntityTypeIcon(type: 'customer' | 'supplier') {
  return type === 'customer' ? Users : Building2;
}

// ==================== Component ====================

export function QuickAssignSheet({
  open,
  onOpenChange,
  onAssign,
  suggestions,
  onSearch,
  ocrResult,
  isAssigning,
}: QuickAssignSheetProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [recentEntities, setRecentEntities] = useState<RecentEntity[]>([]);
  const [assigningEntityId, setAssigningEntityId] = useState<string | null>(null);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load recent entities on mount
  const [prevOpen, setPrevOpen] = useState(false);
  if (open && !prevOpen) {
    setPrevOpen(true);
    setRecentEntities(loadRecentEntities());
    setSearchQuery('');
  }
  if (!open && prevOpen) {
    setPrevOpen(false);
  }

  useEffect(() => {
    if (open) {
      // Focus search input after sheet opens
      setTimeout(() => {
        inputRef.current?.focus();
      }, 300);
    }
  }, [open]);

  // Debounced search
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchQuery(value);

      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }

      if (value.trim().length >= 2) {
        searchTimeoutRef.current = setTimeout(() => {
          onSearch(value.trim());
        }, 300);
      }
    },
    [onSearch]
  );

  // Handle entity selection
  const handleAssign = useCallback(
    (entity: { id: string; name: string; type: 'customer' | 'supplier' }) => {
      setAssigningEntityId(entity.id);
      saveRecentEntity({
        id: entity.id,
        name: entity.name,
        type: entity.type,
        usedAt: Date.now(),
      });
      onAssign(entity.id);
    },
    [onAssign]
  );

  // Suggested entity from OCR
  const ocrSuggestion =
    ocrResult?.matchedEntityId && ocrResult?.matchedEntityName
      ? {
          id: ocrResult.matchedEntityId,
          name: ocrResult.matchedEntityName,
        }
      : null;

  const showRecentEntities =
    searchQuery.trim().length < 2 && recentEntities.length > 0;
  const showSearchResults =
    searchQuery.trim().length >= 2 && suggestions.length > 0;
  const showNoResults =
    searchQuery.trim().length >= 2 && suggestions.length === 0;

  return (
    <BottomSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Dokument zuordnen"
      description="Wählen Sie einen Kunden oder Lieferanten"
      defaultSnapPoint="max"
      snapPoints={['mid', 'max']}
    >
      <div className="space-y-4 pb-4">
        {/* Search Input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            ref={inputRef}
            placeholder="Kunde oder Lieferant suchen..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="pl-9 min-h-[44px]"
          />
        </div>

        {/* OCR Suggested Match */}
        {ocrSuggestion && !searchQuery && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              <Star className="h-3 w-3" />
              Vorgeschlagen (OCR-Erkennung)
            </p>
            <button
              onClick={() =>
                handleAssign({
                  id: ocrSuggestion.id,
                  name: ocrSuggestion.name,
                  type: 'supplier',
                })
              }
              disabled={isAssigning}
              className={cn(
                'w-full flex items-center gap-3 p-3 rounded-lg',
                'bg-primary/5 border border-primary/20',
                'hover:bg-primary/10 active:bg-primary/15',
                'transition-colors min-h-[56px]',
                isAssigning && 'opacity-50 cursor-not-allowed'
              )}
            >
              <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <UserCheck className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 text-left min-w-0">
                <p className="font-medium text-sm truncate">
                  {ocrSuggestion.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  Erkannter Geschäftspartner
                </p>
              </div>
              {isAssigning && assigningEntityId === ocrSuggestion.id ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              )}
            </button>
          </div>
        )}

        {/* Recent Entities */}
        {showRecentEntities && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Zuletzt verwendet
            </p>
            <div className="space-y-1">
              {recentEntities.map((entity) => {
                const Icon = getEntityTypeIcon(entity.type);
                return (
                  <EntityCard
                    key={entity.id}
                    id={entity.id}
                    name={entity.name}
                    type={entity.type}
                    icon={Icon}
                    isAssigning={isAssigning && assigningEntityId === entity.id}
                    disabled={isAssigning}
                    onAssign={() => handleAssign(entity)}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Search Results */}
        {showSearchResults && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Suchergebnisse ({suggestions.length})
            </p>
            <div className="space-y-1">
              {suggestions.map((entity) => {
                const Icon = getEntityTypeIcon(entity.type);
                return (
                  <EntityCard
                    key={entity.id}
                    id={entity.id}
                    name={entity.name}
                    type={entity.type}
                    icon={Icon}
                    folderPath={entity.folderPath}
                    isAssigning={isAssigning && assigningEntityId === entity.id}
                    disabled={isAssigning}
                    onAssign={() => handleAssign(entity)}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* No Results */}
        {showNoResults && (
          <div className="text-center py-8">
            <Search className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              Keine Ergebnisse für &quot;{searchQuery}&quot;
            </p>
          </div>
        )}

        {/* Cancel Button */}
        <Button
          variant="ghost"
          onClick={() => onOpenChange(false)}
          className="w-full min-h-[44px]"
          disabled={isAssigning}
        >
          Abbrechen
        </Button>
      </div>
    </BottomSheet>
  );
}

// ==================== EntityCard Sub-Component ====================

interface EntityCardProps {
  id: string;
  name: string;
  type: 'customer' | 'supplier';
  icon: typeof Users | typeof Building2;
  folderPath?: string | null;
  isAssigning: boolean;
  disabled: boolean;
  onAssign: () => void;
}

function EntityCard({
  name,
  type,
  icon: Icon,
  folderPath,
  isAssigning,
  disabled,
  onAssign,
}: EntityCardProps) {
  return (
    <button
      onClick={onAssign}
      disabled={disabled}
      className={cn(
        'w-full flex items-center gap-3 p-3 rounded-lg',
        'bg-card border hover:bg-muted/50 active:bg-muted',
        'transition-colors min-h-[56px]',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <div className="h-9 w-9 rounded-full bg-muted flex items-center justify-center shrink-0">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="flex-1 text-left min-w-0">
        <p className="font-medium text-sm truncate">{name}</p>
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className="text-[10px] px-1 py-0">
            {getEntityTypeLabel(type)}
          </Badge>
          {folderPath && (
            <span className="text-[10px] text-muted-foreground truncate">
              {folderPath}
            </span>
          )}
        </div>
      </div>
      {isAssigning ? (
        <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 min-h-[36px] text-xs"
          tabIndex={-1}
        >
          Zuordnen
        </Button>
      )}
    </button>
  );
}

export default QuickAssignSheet;
