/**
 * AIRuleGenerator Component
 *
 * Vision 2.0 - Phase 2 (Januar 2026)
 *
 * Generiert Business Rules aus natürlichsprachlichen Beschreibungen
 * mittels lokalem LLM (Ollama).
 */

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles,
  Loader2,
  ChevronRight,
  Check,
  AlertCircle,
  Lightbulb,
  Wand2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/use-toast'
import { useGenerateRule } from '../api'
import type { RuleCreateRequest } from '../types'

// Beispiel-Prompts für schnellen Einstieg
const EXAMPLE_PROMPTS = [
  {
    category: 'Genehmigung',
    prompt: 'Rechnungen über 10.000 EUR benötigen CFO-Genehmigung',
    icon: '💰',
  },
  {
    category: 'Skonto',
    prompt: 'Skonto-Fristen überwachen und bei ablaufenden Fristen warnen',
    icon: '⏰',
  },
  {
    category: 'Betrug',
    prompt: 'Neue Lieferanten mit hohen Beträgen zur manuellen Prüfung markieren',
    icon: '🔍',
  },
  {
    category: 'Compliance',
    prompt: 'SEPA-Mandate vor Ablauf zur Erneuerung markieren',
    icon: '📋',
  },
  {
    category: 'Workflow',
    prompt: 'Wenn Dokument-Status auf abgelehnt gesetzt wird, Ersteller benachrichtigen',
    icon: '🔄',
  },
]

interface GeneratedRulePreview {
  name: string
  description: string
  code?: string | null
  category: string
  priority: number
  condition: Record<string, unknown>
  actions: Array<{ type: string; params: Record<string, unknown> }>
  else_actions?: Array<{ type: string; params: Record<string, unknown> }> | null
  confidence: number
  explanation: string
}

interface AIRuleGeneratorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onRuleGenerated: (rule: RuleCreateRequest) => void
}

export function AIRuleGenerator({ open, onOpenChange, onRuleGenerated }: AIRuleGeneratorProps) {
  const [prompt, setPrompt] = useState('')
  const [generatedRule, setGeneratedRule] = useState<GeneratedRulePreview | null>(null)
  const [step, setStep] = useState<'input' | 'preview' | 'success'>('input')

  const generateMutation = useGenerateRule()

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte beschreiben Sie die gewünschte Regel.',
        variant: 'destructive',
      })
      return
    }

    try {
      const result = await generateMutation.mutateAsync(prompt.trim())
      setGeneratedRule(result)
      setStep('preview')
    } catch (error) {
      toast({
        title: 'Generierung fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Ein Fehler ist aufgetreten.',
        variant: 'destructive',
      })
    }
  }

  const handleAccept = () => {
    if (!generatedRule) return

    // Konvertiere zu RuleCreateRequest
    const ruleRequest: RuleCreateRequest = {
      name: generatedRule.name,
      description: generatedRule.description,
      code: generatedRule.code || undefined,
      category: generatedRule.category as RuleCreateRequest['category'],
      priority: generatedRule.priority,
      condition: generatedRule.condition as RuleCreateRequest['condition'],
      actions: generatedRule.actions as RuleCreateRequest['actions'],
      else_actions: generatedRule.else_actions as RuleCreateRequest['else_actions'],
      is_active: true,
    }

    onRuleGenerated(ruleRequest)
    setStep('success')

    // Nach kurzer Anzeige schließen
    setTimeout(() => {
      handleClose()
    }, 1500)
  }

  const handleClose = () => {
    setPrompt('')
    setGeneratedRule(null)
    setStep('input')
    onOpenChange(false)
  }

  const handleExampleClick = (examplePrompt: string) => {
    setPrompt(examplePrompt)
  }

  const handleBack = () => {
    setStep('input')
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            KI-Regelgenerator
          </DialogTitle>
          <DialogDescription>
            Beschreiben Sie die gewünschte Regel in natürlicher Sprache.
            Die KI generiert automatisch eine strukturierte Geschäftsregel.
          </DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait">
          {step === 'input' && (
            <motion.div
              key="input"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="space-y-4"
            >
              {/* Prompt-Eingabe */}
              <div className="space-y-2">
                <Textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="z.B. 'Rechnungen über 10.000 EUR zur CFO-Genehmigung weiterleiten'"
                  rows={4}
                  className="resize-none"
                />
                <p className="text-xs text-muted-foreground">
                  Beschreiben Sie Bedingungen und Aktionen so konkret wie möglich.
                </p>
              </div>

              {/* Beispiel-Prompts */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Lightbulb className="h-4 w-4" />
                  <span>Beispiele zum Ausprobieren:</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLE_PROMPTS.map((example) => (
                    <TooltipProvider key={example.prompt}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-xs"
                            onClick={() => handleExampleClick(example.prompt)}
                          >
                            {example.icon} {example.category}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="max-w-xs">{example.prompt}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {step === 'preview' && generatedRule && (
            <motion.div
              key="preview"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Confidence-Anzeige */}
              <div className="flex items-center gap-2">
                <Badge
                  variant={generatedRule.confidence >= 0.8 ? 'default' : 'secondary'}
                  className={cn(
                    generatedRule.confidence >= 0.8
                      ? 'bg-green-500'
                      : generatedRule.confidence >= 0.6
                        ? 'bg-yellow-500'
                        : 'bg-orange-500'
                  )}
                >
                  {Math.round(generatedRule.confidence * 100)}% Konfidenz
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {generatedRule.explanation}
                </span>
              </div>

              {/* Regel-Vorschau */}
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{generatedRule.name}</CardTitle>
                    <Badge variant="outline">{generatedRule.category}</Badge>
                  </div>
                  <CardDescription>{generatedRule.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Bedingung */}
                  <div>
                    <div className="text-sm font-medium mb-1">Bedingung:</div>
                    <ScrollArea className="h-20">
                      <pre className="text-xs bg-muted p-2 rounded-md overflow-x-auto">
                        {JSON.stringify(generatedRule.condition, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>

                  {/* Aktionen */}
                  <div>
                    <div className="text-sm font-medium mb-1">Aktionen:</div>
                    <div className="flex flex-wrap gap-2">
                      {generatedRule.actions.map((action, index) => (
                        <Badge key={index} variant="secondary">
                          {action.type}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  {/* Priorität */}
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-muted-foreground">Priorität:</span>
                    <Badge variant="outline">{generatedRule.priority}</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Warnung bei niedriger Konfidenz */}
              {generatedRule.confidence < 0.7 && (
                <div className="flex items-start gap-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-sm">
                  <AlertCircle className="h-4 w-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                  <span>
                    Die Konfidenz ist niedrig. Bitte prüfen Sie die generierte Regel
                    sorgfältig und passen Sie sie bei Bedarf an.
                  </span>
                </div>
              )}
            </motion.div>
          )}

          {step === 'success' && (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center justify-center py-8"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', duration: 0.5 }}
                className="rounded-full bg-green-100 dark:bg-green-900/30 p-4 mb-4"
              >
                <Check className="h-8 w-8 text-green-500" />
              </motion.div>
              <p className="text-lg font-medium">Regel übernommen!</p>
              <p className="text-sm text-muted-foreground">
                Die Regel wurde in den Editor geladen.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {step !== 'success' && (
          <DialogFooter>
            {step === 'preview' && (
              <Button variant="outline" onClick={handleBack}>
                Zurück
              </Button>
            )}
            <Button variant="outline" onClick={handleClose}>
              Abbrechen
            </Button>
            {step === 'input' && (
              <Button onClick={handleGenerate} disabled={generateMutation.isPending}>
                {generateMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generiere...
                  </>
                ) : (
                  <>
                    <Wand2 className="h-4 w-4 mr-2" />
                    Regel generieren
                  </>
                )}
              </Button>
            )}
            {step === 'preview' && (
              <Button onClick={handleAccept}>
                <Check className="h-4 w-4 mr-2" />
                Übernehmen
              </Button>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default AIRuleGenerator
