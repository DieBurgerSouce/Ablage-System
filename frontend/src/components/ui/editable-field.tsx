/**
 * EditableField - Click-to-Edit Pattern Component
 *
 * Ermoeglicht inline Bearbeitung von Text-Werten mit:
 * - Click-to-edit Aktivierung
 * - Auto-Save mit Debounce
 * - Visueller Speicher-Indikator
 * - Validierung mit Zod
 * - Keyboard Navigation (Enter=Save, Escape=Cancel)
 *
 * @example
 * ```tsx
 * <EditableField
 *   value={document.invoiceNumber}
 *   onSave={(value) => updateDocument({ invoiceNumber: value })}
 *   label="Rechnungsnummer"
 *   type="text"
 * />
 * ```
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Check, X, Pencil, Loader2, AlertCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { z } from 'zod';

// ==================== Types ====================

export type EditableFieldType = 'text' | 'number' | 'date' | 'currency' | 'email';

export interface EditableFieldProps {
  /** Aktueller Wert */
  value: string | number | null | undefined;
  /** Callback zum Speichern - gibt Promise zurueck */
  onSave: (value: string) => Promise<void>;
  /** Optionales Label */
  label?: string;
  /** Platzhalter wenn leer */
  placeholder?: string;
  /** Feldtyp fuer Formatierung */
  type?: EditableFieldType;
  /** Validierungs-Schema (Zod) */
  schema?: z.ZodString | z.ZodNumber;
  /** Ist das Feld editierbar? */
  editable?: boolean;
  /** Zusaetzliche Klassen */
  className?: string;
  /** Auto-Save Debounce Zeit in ms (0 = kein Auto-Save) */
  autoSaveDelay?: number;
  /** Zeige Edit-Icon immer an */
  showEditIcon?: boolean;
}

// ==================== Formatter ====================

function formatValue(value: string | number | null | undefined, type: EditableFieldType): string {
  if (value === null || value === undefined || value === '') return '';

  switch (type) {
    case 'currency':
      const num = typeof value === 'string' ? parseFloat(value) : value;
      if (isNaN(num)) return String(value);
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
      }).format(num);

    case 'date':
      try {
        return new Date(value.toString()).toLocaleDateString('de-DE');
      } catch {
        return String(value);
      }

    case 'number':
      const numVal = typeof value === 'string' ? parseFloat(value) : value;
      if (isNaN(numVal)) return String(value);
      return new Intl.NumberFormat('de-DE').format(numVal);

    default:
      return String(value);
  }
}

function getInputValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

// ==================== Component ====================

export function EditableField({
  value,
  onSave,
  label,
  placeholder = 'Nicht angegeben',
  type = 'text',
  schema,
  editable = true,
  className,
  autoSaveDelay = 0,
  showEditIcon = false,
}: EditableFieldProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(getInputValue(value));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSaved, setShowSaved] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync edit value with prop
  useEffect(() => {
    if (!isEditing) {
      setEditValue(getInputValue(value));
    }
  }, [value, isEditing]);

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  const validate = useCallback((val: string): string | null => {
    if (!schema) return null;

    try {
      schema.parse(val);
      return null;
    } catch (err) {
      if (err instanceof z.ZodError) {
        return err.errors[0]?.message || 'Ungueltiger Wert';
      }
      return 'Validierungsfehler';
    }
  }, [schema]);

  const handleSave = useCallback(async () => {
    // Validate
    const validationError = validate(editValue);
    if (validationError) {
      setError(validationError);
      return;
    }

    // Skip if unchanged
    if (editValue === getInputValue(value)) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await onSave(editValue);
      setIsEditing(false);
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen');
    } finally {
      setIsSaving(false);
    }
  }, [editValue, value, validate, onSave]);

  const handleCancel = useCallback(() => {
    setEditValue(getInputValue(value));
    setIsEditing(false);
    setError(null);
  }, [value]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    },
    [handleSave, handleCancel]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      setEditValue(newValue);
      setError(null);

      // Auto-save with debounce
      if (autoSaveDelay > 0) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }
        saveTimeoutRef.current = setTimeout(() => {
          if (newValue !== getInputValue(value)) {
            handleSave();
          }
        }, autoSaveDelay);
      }
    },
    [autoSaveDelay, value, handleSave]
  );

  const handleStartEdit = useCallback(() => {
    if (editable) {
      setIsEditing(true);
    }
  }, [editable]);

  const displayValue = formatValue(value, type);
  const isEmpty = !value || value === '';

  // Editing Mode
  if (isEditing) {
    return (
      <div className={cn('relative', className)}>
        {label && (
          <label className="text-xs text-muted-foreground mb-1 block">
            {label}
          </label>
        )}
        <div className="flex items-center gap-1">
          <Input
            ref={inputRef}
            type={type === 'number' || type === 'currency' ? 'number' : type === 'date' ? 'date' : 'text'}
            value={editValue}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              // Delay blur handling to allow button clicks
              setTimeout(() => {
                if (!isSaving && document.activeElement !== inputRef.current) {
                  handleCancel();
                }
              }, 150);
            }}
            disabled={isSaving}
            className={cn(
              'h-8 text-sm',
              error && 'border-destructive focus-visible:ring-destructive'
            )}
            step={type === 'currency' ? '0.01' : undefined}
          />
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 shrink-0"
            onClick={handleSave}
            disabled={isSaving}
            aria-label="Speichern"
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4 text-green-600" />
            )}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 shrink-0"
            onClick={handleCancel}
            disabled={isSaving}
            aria-label="Abbrechen"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
        {error && (
          <div className="flex items-center gap-1 mt-1 text-xs text-destructive">
            <AlertCircle className="h-3 w-3" />
            {error}
          </div>
        )}
      </div>
    );
  }

  // Display Mode
  return (
    <div
      className={cn(
        'group relative',
        editable && 'cursor-pointer hover:bg-muted/50 rounded-md transition-colors',
        className
      )}
      onClick={handleStartEdit}
      role={editable ? 'button' : undefined}
      tabIndex={editable ? 0 : undefined}
      onKeyDown={(e) => {
        if (editable && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          handleStartEdit();
        }
      }}
    >
      {label && (
        <span className="text-xs text-muted-foreground block mb-0.5">
          {label}
        </span>
      )}
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'text-sm',
            isEmpty && 'text-muted-foreground italic'
          )}
        >
          {isEmpty ? placeholder : displayValue}
        </span>

        {/* Edit Icon */}
        {editable && (showEditIcon || isEditing === false) && (
          <Pencil
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground transition-opacity',
              showEditIcon ? 'opacity-50' : 'opacity-0 group-hover:opacity-50'
            )}
          />
        )}

        {/* Saved Indicator */}
        {showSaved && (
          <span className="flex items-center gap-1 text-xs text-green-600 animate-in fade-in">
            <Check className="h-3 w-3" />
            Gespeichert
          </span>
        )}
      </div>
    </div>
  );
}

export default EditableField;
