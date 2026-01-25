/**
 * RulesAdminPage
 *
 * Hauptseite fuer die Verwaltung von Business Rules.
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Scale,
  Plus,
  Search,
  Shield,
  AlertTriangle,
  Workflow,
  Bell,
  Settings,
  History,
  CheckCircle,
  XCircle,
  Sparkles,
} from 'lucide-react'
import { RuleTable, RuleFormDialog, AIRuleGenerator } from './components'
import { useRulesList, useExecutionLogs } from './api'
import type { BusinessRule, RuleCategory, RuleCreateRequest } from './types'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

const CATEGORY_OPTIONS: { value: RuleCategory | 'all'; label: string; icon: React.ReactNode }[] = [
  { value: 'all', label: 'Alle Kategorien', icon: <Settings className="h-4 w-4" /> },
  { value: 'approval', label: 'Genehmigung', icon: <Shield className="h-4 w-4" /> },
  { value: 'compliance', label: 'Compliance', icon: <Scale className="h-4 w-4" /> },
  { value: 'fraud', label: 'Betrugs-Erkennung', icon: <AlertTriangle className="h-4 w-4" /> },
  { value: 'workflow', label: 'Workflow', icon: <Workflow className="h-4 w-4" /> },
  { value: 'notification', label: 'Benachrichtigung', icon: <Bell className="h-4 w-4" /> },
]

export function RulesAdminPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [aiGeneratorOpen, setAiGeneratorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<BusinessRule | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<RuleCategory | 'all'>('all')

  const { data, isLoading } = useRulesList({
    category: categoryFilter === 'all' ? undefined : categoryFilter,
    search: searchQuery || undefined,
    limit: 100,
  })

  const { data: logs, isLoading: logsLoading } = useExecutionLogs({
    limit: 20,
  })

  const handleEdit = (rule: BusinessRule) => {
    setEditingRule(rule)
    setDialogOpen(true)
  }

  const handleCreate = () => {
    setEditingRule(null)
    setDialogOpen(true)
  }

  const handleDialogClose = (open: boolean) => {
    setDialogOpen(open)
    if (!open) {
      setEditingRule(null)
    }
  }

  const handleDuplicate = (rule: BusinessRule) => {
    // Erstelle Kopie ohne ID
    setEditingRule({
      ...rule,
      id: '',
      name: `${rule.name} (Kopie)`,
      code: rule.code ? `${rule.code}_COPY` : null,
      execution_count: 0,
      match_count: 0,
      last_executed_at: null,
      last_matched_at: null,
    })
    setDialogOpen(true)
  }

  const handleAiGenerate = () => {
    setAiGeneratorOpen(true)
  }

  const handleAiRuleGenerated = (ruleData: RuleCreateRequest) => {
    // Erstelle neue Regel mit generierten Daten
    setEditingRule({
      ...ruleData,
      id: '',
      execution_count: 0,
      match_count: 0,
      last_executed_at: null,
      last_matched_at: null,
      created_by_id: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as BusinessRule)
    setAiGeneratorOpen(false)
    setDialogOpen(true)
  }

  // Stats
  const rules = data?.items ?? []
  const activeCount = rules.filter((r) => r.is_active).length
  const totalExecutions = rules.reduce((sum, r) => sum + r.execution_count, 0)
  const totalMatches = rules.reduce((sum, r) => sum + r.match_count, 0)
  const matchRate = totalExecutions > 0 ? Math.round((totalMatches / totalExecutions) * 100) : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Scale className="h-6 w-6" />
            Business Rules
          </h1>
          <p className="text-muted-foreground">
            Automatisieren Sie Entscheidungen mit konfigurierbaren Regeln.
          </p>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" onClick={handleAiGenerate}>
            <Sparkles className="h-4 w-4 mr-2" />
            KI-Generierung
          </Button>
          <Button onClick={handleCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Neue Regel
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Regeln gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{rules.length}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Aktive Regeln
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-2xl font-bold">{activeCount}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Ausfuehrungen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Workflow className="h-4 w-4 text-blue-500" />
              <span className="text-2xl font-bold">
                {totalExecutions.toLocaleString('de-DE')}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Match-Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              <span className="text-2xl font-bold">{matchRate}%</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="rules" className="space-y-4">
        <TabsList>
          <TabsTrigger value="rules" className="gap-2">
            <Scale className="h-4 w-4" />
            Regeln
          </TabsTrigger>
          <TabsTrigger value="logs" className="gap-2">
            <History className="h-4 w-4" />
            Ausfuehrungslog
          </TabsTrigger>
        </TabsList>

        {/* Rules Tab */}
        <TabsContent value="rules">
          <Card>
            <CardHeader>
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex-1">
                  <CardTitle>Regeluebersicht</CardTitle>
                  <CardDescription>
                    Verwalten Sie Ihre automatischen Verarbeitungsregeln.
                  </CardDescription>
                </div>

                <div className="flex gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Suchen..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-8 w-[200px]"
                    />
                  </div>

                  <Select
                    value={categoryFilter}
                    onValueChange={(v) => setCategoryFilter(v as RuleCategory | 'all')}
                  >
                    <SelectTrigger className="w-[180px]">
                      <SelectValue placeholder="Kategorie" />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          <span className="flex items-center gap-2">
                            {opt.icon}
                            {opt.label}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <RuleTable
                rules={rules}
                isLoading={isLoading}
                onEdit={handleEdit}
                onDuplicate={handleDuplicate}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Logs Tab */}
        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <CardTitle>Ausfuehrungslog</CardTitle>
              <CardDescription>
                Protokoll der letzten Regel-Ausfuehrungen.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {logsLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : logs && logs.length > 0 ? (
                <div className="space-y-2">
                  {logs.map((log) => (
                    <div
                      key={log.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                    >
                      <div className="flex items-center gap-3">
                        {log.matched ? (
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div>
                          <div className="font-medium text-sm">
                            Regel: {log.rule_id.slice(0, 8)}...
                          </div>
                          {log.document_id && (
                            <div className="text-xs text-muted-foreground">
                              Dokument: {log.document_id.slice(0, 8)}...
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={log.matched ? 'default' : 'secondary'}>
                          {log.matched ? 'Match' : 'Kein Match'}
                        </Badge>
                        {log.dry_run && (
                          <Badge variant="outline">Dry-Run</Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                          {formatDistanceToNow(new Date(log.executed_at), {
                            addSuffix: true,
                            locale: de,
                          })}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <History className="h-12 w-12 mx-auto mb-4 opacity-30" />
                  <p>Noch keine Ausfuehrungen protokolliert.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Rule Form Dialog */}
      <RuleFormDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        rule={editingRule}
      />

      {/* AI Rule Generator Dialog */}
      <AIRuleGenerator
        open={aiGeneratorOpen}
        onOpenChange={setAiGeneratorOpen}
        onRuleGenerated={handleAiRuleGenerated}
      />
    </div>
  )
}
