/**
 * RuleTestPanel Component
 *
 * Eigenstaendiges Panel zum Testen von Regeln per Dry-Run.
 * Zeigt Testergebnisse mit Bedingungsdetails und ausgeloesten Aktionen.
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  Zap,
  FileText,
  AlertCircle,
} from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useTestRule } from '../api'
import type {
  RuleCondition,
  RuleAction,
  RuleTestResponse,
} from '../types'
import { ACTION_TYPE_LABELS } from '../types'

/**
 * Vordefinierte Test-Kontexte fuer schnelles Testen
 */
const SAMPLE_CONTEXTS = [
  {
    label: 'Hohe Rechnung',
    context: {
      amount: 15000,
      document_type: 'invoice',
      supplier: { name: 'Muster GmbH', is_new: false },
      status: 'pending',
    },
  },
  {
    label: 'Neuer Lieferant',
    context: {
      amount: 2500,
      document_type: 'invoice',
      supplier: { name: 'Neu AG', is_new: true },
      status: 'pending',
    },
  },
  {
    label: 'Niedrige Confidence',
    context: {
      amount: 500,
      document_type: 'receipt',
      confidence: 0.45,
      status: 'processing',
    },
  },
]

interface RuleTestPanelProps {
  condition: RuleCondition
  actions: RuleAction[]
  elseActions?: RuleAction[]
}

export function RuleTestPanel({
  condition,
  actions,
  elseActions,
}: RuleTestPanelProps) {
  const [testContext, setTestContext] = useState(
    JSON.stringify(SAMPLE_CONTEXTS[0].context, null, 2)
  )
  const [testResult, setTestResult] = useState<RuleTestResponse | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)

  const testMutation = useTestRule()

  const handleTest = async () => {
    setParseError(null)

    let context: Record<string, unknown>
    try {
      context = JSON.parse(testContext)
    } catch {
      setParseError('Ungueltiges JSON-Format. Bitte pruefen Sie die Eingabe.')
      return
    }

    try {
      const result = await testMutation.mutateAsync({
        condition,
        actions,
        else_actions: elseActions,
        context,
      })
      setTestResult(result)
    } catch {
      toast({
        title: 'Testfehler',
        description: 'Der Regeltest konnte nicht ausgefuehrt werden.',
        variant: 'destructive',
      })
    }
  }

  const handleSampleClick = (sampleContext: Record<string, unknown>) => {
    setTestContext(JSON.stringify(sampleContext, null, 2))
    setTestResult(null)
    setParseError(null)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Play className="h-4 w-4" />
            Regel testen
          </CardTitle>
          <CardDescription>
            Testen Sie die Regel mit einem simulierten Dokumentkontext (Dry-Run).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Beispiel-Kontexte */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">
              Schnellauswahl:
            </Label>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_CONTEXTS.map((sample) => (
                <Button
                  key={sample.label}
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => handleSampleClick(sample.context)}
                >
                  <FileText className="h-3 w-3 mr-1" />
                  {sample.label}
                </Button>
              ))}
            </div>
          </div>

          {/* JSON-Eingabe */}
          <div className="space-y-2">
            <Label htmlFor="test-context">Test-Kontext (JSON)</Label>
            <Textarea
              id="test-context"
              value={testContext}
              onChange={(e) => {
                setTestContext(e.target.value)
                setParseError(null)
              }}
              placeholder='{"amount": 15000, "document_type": "invoice"}'
              rows={8}
              className="font-mono text-sm"
            />
            {parseError && (
              <p className="text-sm text-destructive flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {parseError}
              </p>
            )}
          </div>

          {/* Test-Button */}
          <Button
            onClick={handleTest}
            disabled={testMutation.isPending}
            className="w-full"
          >
            {testMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Regel testen
          </Button>
        </CardContent>
      </Card>

      {/* Testergebnis */}
      {testResult && (
        <Card
          className={
            testResult.matched
              ? 'border-green-500/50 bg-green-50/50 dark:bg-green-950/20'
              : 'border-red-500/50 bg-red-50/50 dark:bg-red-950/20'
          }
        >
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              {testResult.matched ? (
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              {testResult.matched ? 'Regel trifft zu' : 'Regel trifft nicht zu'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Match-Status */}
            <div className="flex items-center gap-2">
              <Badge variant={testResult.matched ? 'default' : 'destructive'}>
                {testResult.matched ? 'MATCH' : 'KEIN MATCH'}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {testResult.would_trigger_actions.length} Aktion(en) wuerden
                ausgefuehrt
              </span>
            </div>

            <Separator />

            {/* Ausgeloeste Aktionen */}
            {testResult.would_trigger_actions.length > 0 && (
              <div className="space-y-2">
                <Label className="text-sm font-medium flex items-center gap-1">
                  <Zap className="h-4 w-4" />
                  Ausgeloeste Aktionen:
                </Label>
                <div className="space-y-1">
                  {testResult.would_trigger_actions.map((action, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-2 text-sm p-2 rounded bg-background"
                    >
                      <Badge variant="outline" className="text-xs">
                        {index + 1}
                      </Badge>
                      <span className="font-medium">
                        {ACTION_TYPE_LABELS[action.type] || action.type}
                      </span>
                      {Object.keys(action.params).length > 0 && (
                        <span className="text-muted-foreground text-xs">
                          ({Object.entries(action.params)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(', ')})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bedingungsdetails */}
            {testResult.condition_details &&
              Object.keys(testResult.condition_details).length > 0 && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">
                      Bedingungsdetails:
                    </Label>
                    <ScrollArea className="max-h-40">
                      <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto font-mono">
                        {JSON.stringify(testResult.condition_details, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                </>
              )}

            {/* Verwendeter Kontext */}
            {testResult.context_used &&
              Object.keys(testResult.context_used).length > 0 && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">
                      Verwendeter Kontext:
                    </Label>
                    <ScrollArea className="max-h-32">
                      <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto font-mono">
                        {JSON.stringify(testResult.context_used, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                </>
              )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
