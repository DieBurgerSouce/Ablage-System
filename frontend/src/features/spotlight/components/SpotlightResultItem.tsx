/**
 * SpotlightResultItem Component
 *
 * Rendert einzelne Ergebnis-Items je nach Typ:
 * Vorschlag, Dokument oder Entity.
 */

import { useNavigate } from '@tanstack/react-router';
import {
  FileText,
  Users,
  Building2,
  Sparkles,
  ArrowRight,
  Search,
} from 'lucide-react';
import { CommandItem } from '@/components/ui/command';
import type {
  SpotlightSuggestionResponse,
  SpotlightDocumentResponse,
  SpotlightEntityResponse,
} from '../types/spotlight-types';

// ==================== Navigation Mapping ====================

const NAVIGATION_ROUTES: Record<string, string> = {
  dashboard: '/',
  dokumente: '/dokumente',
  entities: '/entities',
  kunden: '/entities',
  lieferanten: '/entities',
  rechnungen: '/rechnungen',
  banking: '/banking',
  einstellungen: '/einstellungen',
  statistiken: '/statistiken',
  upload: '/upload',
};

function resolveNavigationRoute(text: string): string | null {
  const lower = text.toLowerCase();
  for (const [keyword, route] of Object.entries(NAVIGATION_ROUTES)) {
    if (lower.includes(keyword)) {
      return route;
    }
  }
  return null;
}

// ==================== Suggestion Item ====================

interface SuggestionItemProps {
  suggestion: SpotlightSuggestionResponse;
  onSelect: () => void;
}

export function SuggestionItem({ suggestion, onSelect }: SuggestionItemProps) {
  const navigate = useNavigate();

  const isNavigation = suggestion.suggestionType === 'navigation';
  const Icon = isNavigation ? ArrowRight : suggestion.suggestionType === 'recent' ? Search : Sparkles;

  function handleSelect() {
    if (isNavigation) {
      const route = resolveNavigationRoute(suggestion.text);
      if (route) {
        navigate({ to: route });
      }
    }
    onSelect();
  }

  return (
    <CommandItem
      value={`suggestion-${suggestion.text}`}
      onSelect={handleSelect}
      className="flex items-center gap-2"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate">{suggestion.text}</span>
      {suggestion.confidence !== null && (
        <span className="text-xs text-muted-foreground shrink-0">
          {Math.round(suggestion.confidence * 100)}%
        </span>
      )}
    </CommandItem>
  );
}

// ==================== Document Item ====================

interface DocumentItemProps {
  document: SpotlightDocumentResponse;
  onSelect: () => void;
}

export function DocumentItem({ document, onSelect }: DocumentItemProps) {
  const navigate = useNavigate();

  function handleSelect() {
    navigate({ to: `/dokumente/${document.documentId}` });
    onSelect();
  }

  return (
    <CommandItem
      value={`doc-${document.documentId}-${document.filename}`}
      onSelect={handleSelect}
      className="flex items-center gap-2"
    >
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{document.filename}</span>
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            {document.documentType}
          </span>
        </div>
        {document.highlight && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {document.highlight}
          </p>
        )}
      </div>
      <span className="text-xs text-muted-foreground shrink-0">
        {Math.round(document.relevanceScore * 100)}%
      </span>
    </CommandItem>
  );
}

// ==================== Entity Item ====================

interface EntityItemProps {
  entity: SpotlightEntityResponse;
  onSelect: () => void;
}

export function EntityItem({ entity, onSelect }: EntityItemProps) {
  const navigate = useNavigate();

  const isCustomer = entity.entityType === 'customer';
  const Icon = isCustomer ? Users : Building2;
  const typeLabel = isCustomer ? 'Kunde' : 'Lieferant';
  const identifier = isCustomer ? entity.customerNumber : entity.supplierNumber;

  function handleSelect() {
    navigate({ to: `/entities/${entity.entityId}` });
    onSelect();
  }

  return (
    <CommandItem
      value={`entity-${entity.entityId}-${entity.entityName}`}
      onSelect={handleSelect}
      className="flex items-center gap-2"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{entity.entityName}</span>
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            {typeLabel}
          </span>
        </div>
        {identifier && (
          <p className="text-xs text-muted-foreground mt-0.5">
            Nr. {identifier}
          </p>
        )}
      </div>
      <span className="text-xs text-muted-foreground shrink-0">
        {Math.round(entity.matchConfidence * 100)}%
      </span>
    </CommandItem>
  );
}
