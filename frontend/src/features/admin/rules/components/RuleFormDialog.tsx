/**
 * RuleFormDialog Component
 *
 * Dialog zum Erstellen und Bearbeiten von Business Rules.
 */

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Loader2, Play, Settings, Zap, GitBranch, FlaskConical } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { ConditionBuilder } from './ConditionBuilder'
import { ActionBuilder } from './ActionBuilder'
import { useCreateRule, useUpdateRule, useTestRule } from '../api'
import type {
  BusinessRule,
  RuleCondition,
  RuleAction,
  RuleCategory,
  RuleCreateRequest,
} from '../types'

const CATEGORIES: { value: RuleCategory; label: string }[] = [
  { value: 'approval', label: 'Genehmigung' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'fraud', label: 'Betrugs-Erkennung' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'notification', label: 'Benachrichtigung' },
  { value: 'assignment', label: 'Zuweisung' },
  { value: 'data_quality', label: 'Datenqualitaet' },
  { value: 'custom', label: 'Benutzerdefiniert' },
]

const PRIORITIES = [
  { value: 100, label: 'Kritisch (100)' },
  { value: 75, label: 'Hoch (75)' },
  { value: 50, label: 'Normal (50)' },
  { value: 25, label: 'Niedrig (25)' },
  { value: 10, label: 'Hintergrund (10)' },
]

interface RuleFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  rule: BusinessRule | null
}

export function RuleFormDialog({ open, onOpenChange, rule }: RuleFormDialogProps) {
  const isEdit = !!rule

  // Form State
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [code, setCode] = useState('')
  const [category, setCategory] = useState<RuleCategory>('custom')
  const [priority, setPriority] = useState(50)
  const [isActive, setIsActive] = useState(true)
  const [stopOnMatch, setStopOnMatch] = useState(false)
  const [condition, setCondition] = useState<RuleCondition>({
    field: 'amount',
    op: '>',
    value: 0,
  })
  const [actions, setActions] = useState<RuleAction[]>([
    { type: 'flag_for_review', params: {} },
  ])
  const [elseActions, setElseActions] = useState<RuleAction[]>([])
  const [hasElseActions, setHasElseActions] = useState(false)

  // Test State
  const [testContext, setTestContext] = useState('{\n  "amount": 15000,\n  "document_type": "invoice"\n}')
  const [testResult, setTestResult] = useState<{
    matched: boolean
    details: Record<string, unknown>
  } | null>(null)

  const createMutation = useCreateRule()
  const updateMutation = useUpdateRule()
  const testMutation = useTestRule()

  // Reset form when opening/closing or rule changes
  useEffect(() => {
    if (open) {
      if (rule) {
        setName(rule.name)
        setDescription(rule.description ?? '')
        setCode(rule.code ?? '')
        setCategory(rule.category)
        setPriority(rule.priority)
        setIsActive(rule.is_active)
        setStopOnMatch(rule.stop_on_match)
        setCondition(rule.condition)
        setActions(rule.actions)
        setElseActions(rule.else_actions ?? [])
        setHasElseActions((rule.else_actions?.length ?? 0) > 0)
      } else {
        // Reset to defaults
        setName('')
        setDescription('')
        setCode('')
        setCategory('custom')
        setPriority(50)
        setIsActive(true)
        setStopOnMatch(false)
        setCondition({ field: 'amount', op: '>', value: 0 })
        setActions([{ type: 'flag_for_review', params: {} }])
        setElseActions([])
        setHasElseActions(false)
      }
      setTestResult(null)
    }
  }, [open, rule])

  const handleSave = async () => {
    if (!name.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Namen ein.',
        variant: 'destructive',
      })
      return
    }

    if (actions.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Mindestens eine Aktion ist erforderlich.',
        variant: 'destructive',
      })
      return
    }

    const data: RuleCreateRequest = {
      name: name.trim(),
      description: description.trim() || undefined,
      code: code.trim() || undefined,
      category,
      priority,
      is_active: isActive,
      stop_on_match: stopOnMatch,
      condition,
      actions,
      else_actions: hasElseActions && elseActions.length > 0 ? elseActions : undefined,
    }

    try {
      if (isEdit) {
        await updateMutation.mutateAsync({ id: rule.id, data })
        toast({
          title: 'Regel aktualisiert',
          description: `"${name}" wurde gespeichert.`,
        })
      } else {
        await createMutation.mutateAsync(data)
        toast({
          title: 'Regel erstellt',
          description: `"${name}" wurde erstellt.`,
        })
      }
      onOpenChange(false)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Regel konnte nicht gespeichert werden.',
        variant: 'destructive',
      })
    }
  }

  const handleTest = async () => {
    try {
      const context = JSON.parse(testContext)
      const result = await testMutation.mutateAsync({
        condition,
        actions,
        else_actions: hasElseActions ? elseActions : undefined,
        context,
      })
      setTestResult({
        matched: result.matched,
        details: result.condition_details,
      })
      toast({
        title: result.matched ? 'Regel würde matchen' : 'Regel würde NICHT matchen',
        description: `${result.would_trigger_actions.length} Aktion(en) würden ausgeführt.`,
      })
    } catch (e) {
      toast({
        title: 'Fehler beim Test',
        description: e instanceof SyntaxError ? 'Ungültiges JSON' : 'Testfehler',
        variant: 'destructive',
      })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Regel bearbeiten' : 'Neue Regel erstellen'}
          </DialogTitle>
          <DialogDescription>
            Definieren Sie Bedingungen und Aktionen für die automatische Verarbeitung.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="basics" className="flex-1 overflow-hidden flex flex-col">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="basics" className="gap-2">
              <Settings className="h-4 w-4" />
              Grundlagen
            </TabsTrigger>
            <TabsTrigger value="condition" className="gap-2">
              <GitBranch className="h-4 w-4" />
              Bedingungen
            </TabsTrigger>
            <TabsTrigger value="actions" className="gap-2">
              <Zap className="h-4 w-4" />
              Aktionen
            </TabsTrigger>
            <TabsTrigger value="test" className="gap-2">
              <FlaskConical className="h-4 w-4" />
              Testen
            </TabsTrigger>
          </TabsList>

          <ScrollArea className="flex-1 px-1">
            {/* Grundlagen */}
            <TabsContent value="basics" className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name *</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="z.B. Hohe Beträge an CFO"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="code">Code (optional)</Label>
                  <Input
                    id="code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="z.B. RULE_HIGH_AMOUNT"
                    className="font-mono"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Beschreibung</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Wann und warum wird diese Regel angewendet?"
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Kategorie</Label>
                  <Select value={category} onValueChange={(v) => setCategory(v as RuleCategory)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((cat) => (
                        <SelectItem key={cat.value} value={cat.value}>
                          {cat.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Priorität</Label>
                  <Select
                    value={String(priority)}
                    onValueChange={(v) => setPriority(Number(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITIES.map((p) => (
                        <SelectItem key={p.value} value={String(p.value)}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center gap-8 py-4">
                <div className="flex items-center gap-2">
                  <Switch checked={isActive} onCheckedChange={setIsActive} />
                  <Label>Regel aktiv</Label>
                </div>

                <div className="flex items-center gap-2">
                  <Switch checked={stopOnMatch} onCheckedChange={setStopOnMatch} />
                  <Label>Bei Match stoppen</Label>
                  <span className="text-xs text-muted-foreground">
                    (Keine weiteren Regeln ausführen)
                  </span>
                </div>
              </div>
            </TabsContent>

            {/* Bedingungen */}
            <TabsContent value="condition" className="mt-4">
              <ConditionBuilder condition={condition} onChange={setCondition} />
            </TabsContent>

            {/* Aktionen */}
            <TabsContent value="actions" className="space-y-6 mt-4">
              <ActionBuilder
                actions={actions}
                onChange={setActions}
                title="Wenn Bedingung erfüllt"
                description="Diese Aktionen werden ausgeführt, wenn alle Bedingungen erfüllt sind."
              />

              <div className="border-t pt-4">
                <div className="flex items-center gap-2 mb-4">
                  <Switch checked={hasElseActions} onCheckedChange={setHasElseActions} />
                  <Label>Else-Aktionen (wenn NICHT erfüllt)</Label>
                </div>

                {hasElseActions && (
                  <ActionBuilder
                    actions={elseActions}
                    onChange={setElseActions}
                    title="Wenn Bedingung NICHT erfüllt"
                    description="Diese Aktionen werden ausgeführt, wenn die Bedingungen nicht erfüllt sind."
                  />
                )}
              </div>
            </TabsContent>

            {/* Test */}
            <TabsContent value="test" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label>Test-Kontext (JSON)</Label>
                <Textarea
                  value={testContext}
                  onChange={(e) => setTestContext(e.target.value)}
                  placeholder='{"amount": 15000, "document_type": "invoice"}'
                  rows={8}
                  className="font-mono text-sm"
                />
              </div>

              <Button onClick={handleTest} disabled={testMutation.isPending}>
                {testMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Regel testen
              </Button>

              {testResult && (
                <div
                  className={`p-4 rounded-lg ${
                    testResult.matched
                      ? 'bg-green-100 dark:bg-green-900/30 border border-green-500'
                      : 'bg-red-100 dark:bg-red-900/30 border border-red-500'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant={testResult.matched ? 'default' : 'destructive'}>
                      {testResult.matched ? 'MATCH' : 'KEIN MATCH'}
                    </Badge>
                  </div>
                  <pre className="text-xs overflow-auto max-h-40">
                    {JSON.stringify(testResult.details, null, 2)}
                  </pre>
                </div>
              )}
            </TabsContent>
          </ScrollArea>
        </Tabs>

        <DialogFooter className="border-t pt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={isPending}>
            {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEdit ? 'Speichern' : 'Erstellen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
