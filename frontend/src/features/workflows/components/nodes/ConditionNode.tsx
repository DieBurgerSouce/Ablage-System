/**
 * ConditionNode Component
 *
 * ReactFlow Knoten für Bedingungsprüfungen.
 * Zeigt AND/OR-Logik und Regel-Zusammenfassung an.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Filter, CheckCircle, XCircle, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StepConfig, ConditionGroup } from '../../types/workflow-types';

interface ConditionNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
}

function countRules(group: ConditionGroup | undefined): number {
  if (!group?.rules) return 0;
  return group.rules.reduce((count, rule) => {
    if ('operator' in rule && 'rules' in rule) {
      return count + countRules(rule as ConditionGroup);
    }
    return count + 1;
  }, 0);
}

function ConditionNode({ data, selected }: NodeProps<ConditionNodeData>) {
  const conditions = data.config?.conditions;
  const operator = conditions?.operator || 'AND';
  const ruleCount = useMemo(() => countRules(conditions), [conditions]);

  const summary = useMemo(() => {
    if (!conditions?.rules?.length) {
      return 'Keine Bedingungen';
    }
    const firstRule = conditions.rules[0];
    if ('field' in firstRule) {
      return `${firstRule.field} ${firstRule.operator}`;
    }
    return `${ruleCount} Regeln`;
  }, [conditions, ruleCount]);

  return (
    <div
      className={cn(
        'min-w-[180px] rounded-lg border-2 bg-card shadow-md transition-all',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border'
      )}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
      />

      {/* Header */}
      <div className="flex items-center gap-2 rounded-t-md bg-orange-500 px-3 py-2">
        <Filter className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">Bedingung</span>
        <span
          className={cn(
            'ml-auto rounded px-1.5 py-0.5 text-xs font-bold',
            operator === 'AND' ? 'bg-orange-700/50 text-white' : 'bg-orange-300/50 text-white'
          )}
        >
          {operator}
        </span>
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Prüfung'}
        </div>
        <div className="text-xs text-muted-foreground">{summary}</div>
        {ruleCount > 1 && (
          <div className="text-xs text-muted-foreground">
            {ruleCount} Regeln mit {operator}
          </div>
        )}
      </div>

      {/* Footer with Output Labels */}
      <div className="flex items-center justify-between border-t border-border px-2 py-1">
        <div className="flex items-center gap-1 text-xs text-green-600">
          <CheckCircle className="h-3 w-3" />
          <span>Ja</span>
        </div>
        <Settings className="h-3 w-3 text-muted-foreground" />
        <div className="flex items-center gap-1 text-xs text-red-600">
          <XCircle className="h-3 w-3" />
          <span>Nein</span>
        </div>
      </div>

      {/* Output Handles */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        className="!left-[25%] !h-3 !w-3 !border-2 !border-background !bg-green-500"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        className="!left-[75%] !h-3 !w-3 !border-2 !border-background !bg-red-500"
      />
    </div>
  );
}

export default memo(ConditionNode);
