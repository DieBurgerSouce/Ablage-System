/**
 * RuleTemplateGallery Component
 *
 * Zeigt vordefinierte Regel-Vorlagen zur schnellen Erstellung.
 * Jede Vorlage kann uebernommen werden und fuellt den Editor vor.
 */

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  DollarSign,
  Copy,
  ShieldCheck,
  ArrowRight,
  AlertTriangle,
  FileSearch,
  Clock,
} from 'lucide-react'
import type {
  RuleTemplate,
  RuleCategory,
  RuleCreateRequest,
} from '../types'
import { CATEGORY_LABELS } from '../types'

/**
 * Vordefinierte Regelvorlagen
 */
const TEMPLATES: RuleTemplate[] = [
  {
    id: 'high-amount',
    name: 'Hoher Rechnungsbetrag',
    description:
      'Rechnungen ueber 10.000 EUR erfordern eine Genehmigung durch das Management.',
    category: 'approval',
    priority: 75,
    condition: {
      and: [
        { field: 'amount', op: '>' as const, value: 10000 },
        { field: 'document_type', op: '==' as const, value: 'invoice' },
      ],
    },
    actions: [
      {
        type: 'require_approval',
        params: { approver_role: 'manager' },
      },
      {
        type: 'send_notification',
        params: { message: 'Hoher Rechnungsbetrag - Genehmigung erforderlich' },
      },
    ],
  },
  {
    id: 'new-supplier',
    name: 'Neuer Lieferant',
    description:
      'Dokumente von neuen Lieferanten werden zur manuellen Pruefung markiert.',
    category: 'fraud',
    priority: 80,
    condition: {
      field: 'supplier.is_new',
      op: 'is_true' as const,
    },
    actions: [
      {
        type: 'require_review',
        params: {},
      },
      {
        type: 'add_tag',
        params: { tag: 'neuer-lieferant' },
      },
    ],
  },
  {
    id: 'duplicate-invoice',
    name: 'Doppelte Rechnung',
    description:
      'Erkennung und Blockierung potentiell doppelter Rechnungen.',
    category: 'fraud',
    priority: 100,
    condition: {
      field: 'is_duplicate',
      op: 'is_true' as const,
    },
    actions: [
      {
        type: 'block_processing',
        params: {},
      },
      {
        type: 'send_notification',
        params: {
          message: 'Potentielle Doppelrechnung erkannt - Verarbeitung blockiert',
        },
      },
      {
        type: 'add_tag',
        params: { tag: 'duplikat-verdacht' },
      },
    ],
  },
  {
    id: 'compliance-check',
    name: 'Compliance-Pruefung',
    description:
      'Dokumente mit fehlenden Pflichtangaben werden zur Nachbesserung markiert.',
    category: 'compliance',
    priority: 90,
    condition: {
      or: [
        { field: 'tax_id', op: 'is_null' as const },
        { field: 'invoice_number', op: 'is_null' as const },
      ],
    },
    actions: [
      {
        type: 'flag_for_review',
        params: {},
      },
      {
        type: 'add_tag',
        params: { tag: 'compliance-pruefung' },
      },
      {
        type: 'set_priority',
        params: { priority: 'high' },
      },
    ],
  },
  {
    id: 'low-confidence',
    name: 'Niedrige OCR-Confidence',
    description:
      'Dokumente mit niedriger OCR-Erkennungsrate erneut verarbeiten.',
    category: 'data_quality',
    priority: 60,
    condition: {
      field: 'confidence',
      op: '<' as const,
      value: 0.7,
    },
    actions: [
      {
        type: 'trigger_ocr',
        params: { backend: 'deepseek' },
      },
      {
        type: 'flag_for_review',
        params: {},
      },
    ],
  },
  {
    id: 'overdue-payment',
    name: 'Ueberfaellige Zahlung',
    description:
      'Rechnungen nach Faelligkeitsdatum eskalieren und Team benachrichtigen.',
    category: 'workflow',
    priority: 85,
    condition: {
      and: [
        { field: 'due_date', op: 'before' as const, value: 'today' },
        { field: 'status', op: '!=' as const, value: 'paid' },
      ],
    },
    actions: [
      {
        type: 'escalate',
        params: {},
      },
      {
        type: 'notify_team',
        params: {
          team_id: 'buchhaltung',
          message: 'Ueberfaellige Rechnung - Bitte pruefen',
        },
      },
      {
        type: 'set_priority',
        params: { priority: 'urgent' },
      },
    ],
  },
]

const CATEGORY_ICONS: Partial<Record<RuleCategory, React.ReactNode>> = {
  approval: <DollarSign className="h-5 w-5" />,
  fraud: <AlertTriangle className="h-5 w-5" />,
  compliance: <ShieldCheck className="h-5 w-5" />,
  data_quality: <FileSearch className="h-5 w-5" />,
  workflow: <Clock className="h-5 w-5" />,
}

const CATEGORY_COLORS: Partial<Record<RuleCategory, string>> = {
  approval: 'text-blue-500',
  fraud: 'text-red-500',
  compliance: 'text-purple-500',
  data_quality: 'text-orange-500',
  workflow: 'text-green-500',
}

interface RuleTemplateGalleryProps {
  onSelect: (template: RuleCreateRequest) => void
}

export function RuleTemplateGallery({ onSelect }: RuleTemplateGalleryProps) {
  const handleSelect = (template: RuleTemplate) => {
    const ruleData: RuleCreateRequest = {
      name: template.name,
      description: template.description,
      category: template.category,
      priority: template.priority,
      condition: template.condition,
      actions: template.actions,
      else_actions: template.else_actions,
      is_active: true,
    }
    onSelect(ruleData)
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Vorlagen</h3>
        <p className="text-sm text-muted-foreground">
          Starten Sie schnell mit einer vorgefertigten Regelvorlage.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {TEMPLATES.map((template) => (
          <Card
            key={template.id}
            className="group hover:shadow-md transition-shadow cursor-pointer"
          >
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div
                  className={`p-2 rounded-lg bg-muted ${
                    CATEGORY_COLORS[template.category] || 'text-muted-foreground'
                  }`}
                >
                  {CATEGORY_ICONS[template.category] || (
                    <Copy className="h-5 w-5" />
                  )}
                </div>
                <Badge variant="outline" className="text-xs">
                  {CATEGORY_LABELS[template.category]}
                </Badge>
              </div>
              <CardTitle className="text-base mt-2">{template.name}</CardTitle>
              <CardDescription className="text-sm">
                {template.description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex gap-1 flex-wrap">
                  {template.actions.slice(0, 2).map((action, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      {action.type.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                  {template.actions.length > 2 && (
                    <Badge variant="secondary" className="text-xs">
                      +{template.actions.length - 2}
                    </Badge>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => handleSelect(template)}
                >
                  Uebernehmen
                  <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
