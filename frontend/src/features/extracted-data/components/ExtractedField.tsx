import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, Edit2, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip';
import {
  type ExtractedField as ExtractedFieldType,
  type FieldConfig,
  getConfidenceLevel,
  getConfidenceColor,
  getConfidenceBgColor,
  formatCurrency,
  formatDate,
} from '../types/extracted-types';
import { cn } from '@/lib/utils';

interface ExtractedFieldProps {
  field: ExtractedFieldType | undefined;
  config: FieldConfig;
  onEdit?: (newValue: string) => void;
  showConfidence?: boolean;
  compact?: boolean;
}

export function ExtractedFieldDisplay({
  field,
  config,
  onEdit,
  showConfidence = true,
  compact = false,
}: ExtractedFieldProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');

  if (!field && !config.required) {
    return null;
  }

  const value = field?.value || '';
  const confidence = field?.confidence || 0;
  const confidenceLevel = getConfidenceLevel(confidence);
  const isEdited = field?.edited || false;
  const isValidated = field?.validated || false;

  const displayValue = (() => {
    if (!value) return '-';
    switch (config.type) {
      case 'currency':
        return formatCurrency(value);
      case 'date':
        return formatDate(value);
      default:
        return value;
    }
  })();

  const handleStartEdit = () => {
    setEditValue(value);
    setIsEditing(true);
  };

  const handleSave = () => {
    if (onEdit && editValue !== value) {
      onEdit(editValue);
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue('');
    setIsEditing(false);
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between py-1 px-2 rounded hover:bg-muted/50">
        <span className="text-sm text-muted-foreground">{config.german_label}:</span>
        <span className="text-sm font-medium">{displayValue}</span>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <motion.div
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          'group relative rounded-lg border p-3 transition-all',
          confidenceLevel === 'low' && 'border-red-200 bg-red-50/50',
          confidenceLevel === 'medium' && 'border-yellow-200 bg-yellow-50/30',
          confidenceLevel === 'high' && 'border-green-200 bg-green-50/30',
          isEdited && 'ring-2 ring-blue-500/20',
          isValidated && 'ring-2 ring-green-500/20'
        )}
      >
        {/* Header row */}
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {config.german_label}
            </span>
            {config.required && (
              <span className="text-xs text-red-500">*</span>
            )}
          </div>

          <div className="flex items-center gap-1">
            {/* Status indicators */}
            {isValidated && (
              <Tooltip>
                <TooltipTrigger>
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                </TooltipTrigger>
                <TooltipContent>Validiert</TooltipContent>
              </Tooltip>
            )}
            {isEdited && (
              <Tooltip>
                <TooltipTrigger>
                  <Edit2 className="h-4 w-4 text-blue-500" />
                </TooltipTrigger>
                <TooltipContent>
                  Bearbeitet (Original: {field?.original_value})
                </TooltipContent>
              </Tooltip>
            )}
            {confidenceLevel === 'low' && (
              <Tooltip>
                <TooltipTrigger>
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                </TooltipTrigger>
                <TooltipContent>
                  Niedrige Konfidenz - Pruefung empfohlen
                </TooltipContent>
              </Tooltip>
            )}

            {/* Confidence badge */}
            {showConfidence && confidence > 0 && (
              <Tooltip>
                <TooltipTrigger>
                  <span
                    className={cn(
                      'ml-2 text-xs px-1.5 py-0.5 rounded-full',
                      getConfidenceBgColor(confidence),
                      getConfidenceColor(confidence)
                    )}
                  >
                    {Math.round(confidence * 100)}%
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  Extraktions-Konfidenz: {(confidence * 100).toFixed(1)}%
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>

        {/* Value row */}
        <AnimatePresence mode="wait">
          {isEditing ? (
            <motion.div
              key="editing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2"
            >
              <Input
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="h-8 text-sm"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSave();
                  if (e.key === 'Escape') handleCancel();
                }}
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-green-600 hover:text-green-700"
                onClick={handleSave}
              >
                <Check className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-red-600 hover:text-red-700"
                onClick={handleCancel}
              >
                <X className="h-4 w-4" />
              </Button>
            </motion.div>
          ) : (
            <motion.div
              key="display"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center justify-between"
            >
              <span
                className={cn(
                  'text-base font-medium',
                  !value && 'text-muted-foreground italic'
                )}
              >
                {displayValue}
              </span>

              {config.editable && onEdit && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={handleStartEdit}
                >
                  <Edit2 className="h-3.5 w-3.5 mr-1" />
                  Bearbeiten
                </Button>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Source indicator */}
        {field?.source && (
          <div className="mt-1 text-xs text-muted-foreground/70">
            Quelle: {field.source}
          </div>
        )}
      </motion.div>
    </TooltipProvider>
  );
}

// Compact list version for sidebar or summary
interface FieldListProps {
  fields: Record<string, ExtractedFieldType | undefined>;
  configs: FieldConfig[];
  onEdit?: (key: string, value: string) => void;
}

export function ExtractedFieldList({ fields, configs, onEdit }: FieldListProps) {
  const visibleConfigs = configs.filter(
    (c) => fields[c.key]?.value || c.required
  );

  if (visibleConfigs.length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        Keine Felder extrahiert
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {visibleConfigs.map((config) => (
        <ExtractedFieldDisplay
          key={config.key}
          field={fields[config.key]}
          config={config}
          onEdit={onEdit ? (v) => onEdit(config.key, v) : undefined}
        />
      ))}
    </div>
  );
}
