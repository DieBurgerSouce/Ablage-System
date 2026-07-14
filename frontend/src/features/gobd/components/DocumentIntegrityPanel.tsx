/**
 * DocumentIntegrityPanel — „Beweisen"-Button mit Live-Beweisführung.
 *
 * Macht die unsichtbare GoBD-Versiegelung am Dokument erlebbar:
 * Badge zeigt den Versiegelungsstatus, der Button führt eine echte
 * Beweisführung durch (Server lädt das Original aus dem Storage, hasht
 * neu und prüft Baseline, Beweiskette und RFC-3161-Zeitstempel).
 */

import { useState } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Shield,
  Loader2,
  ChevronDown,
  Info,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { StatusBadge } from '@/components/ui/status-badge'
import { useArchiveEntry, useProveDocument } from '../hooks/use-gobd'
import type { DocumentProof } from '../types'

interface DocumentIntegrityPanelProps {
  documentId: string
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : `${date.toLocaleDateString('de-DE')}, ${date.toLocaleTimeString('de-DE')} Uhr`
}

function HashRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-mono text-xs break-all bg-muted rounded px-2 py-1">
        {value ?? '—'}
      </p>
    </div>
  )
}

function TechnicalDetails({ proof }: { proof: DocumentProof }) {
  const [open, setOpen] = useState(proof.verdict === 'tampered')

  const baselineLabel =
    proof.baseline_source === 'archiv'
      ? 'GoBD-Archiv (versiegelte Kopie)'
      : proof.baseline_source === 'integritaets_hash'
        ? 'Integritäts-Hash'
        : 'Keine Baseline vorhanden'

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="w-full justify-between px-2">
          Technische Details
          <ChevronDown
            className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 pt-2" data-testid="integrity-technical-details">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Baseline-Quelle</p>
            <p>{baselineLabel}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Algorithmus</p>
            <p className="uppercase">{proof.hash_algorithm}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Versiegelt am</p>
            <p>{formatDate(proof.archived_at)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Geprüft am</p>
            <p>{formatDateTime(proof.verified_at)}</p>
          </div>
        </div>
        <HashRow label="Versiegelter Hash (Baseline)" value={proof.stored_hash} />
        <HashRow label="Live neu berechneter Hash" value={proof.computed_hash} />
        <Separator />
        <div className="space-y-1 text-sm">
          <p className="text-xs text-muted-foreground">Beweiskette (Audit-Protokoll)</p>
          <p data-testid="integrity-chain-message">{proof.chain.message}</p>
          <p className="text-xs text-muted-foreground">Zeitstempel (RFC 3161 / TSA)</p>
          <p data-testid="integrity-tsa-message">{proof.tsa.message}</p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function ProofResult({ proof }: { proof: DocumentProof }) {
  if (proof.verdict === 'verified') {
    return (
      <div className="space-y-3" data-testid="integrity-result" data-verdict="verified">
        <Alert className="border-green-500 bg-green-50 dark:bg-green-950 text-green-900 dark:text-green-100">
          <ShieldCheck className="h-5 w-5 text-green-600 dark:text-green-400" />
          <AlertTitle className="text-green-800 dark:text-green-200">
            Mathematisch bewiesen: unverändert
          </AlertTitle>
          <AlertDescription className="text-green-800 dark:text-green-200">
            {proof.message_de}
          </AlertDescription>
        </Alert>
        <TechnicalDetails proof={proof} />
      </div>
    )
  }

  if (proof.verdict === 'tampered') {
    return (
      <div className="space-y-3" data-testid="integrity-result" data-verdict="tampered">
        <Alert variant="destructive">
          <ShieldAlert className="h-5 w-5" />
          <AlertTitle>Integrität verletzt</AlertTitle>
          <AlertDescription>{proof.message_de}</AlertDescription>
        </Alert>
        <TechnicalDetails proof={proof} />
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="integrity-result" data-verdict="no_baseline">
      <Alert>
        <Info className="h-5 w-5" />
        <AlertTitle>Noch keine versiegelte Baseline</AlertTitle>
        <AlertDescription>{proof.message_de}</AlertDescription>
      </Alert>
      <TechnicalDetails proof={proof} />
    </div>
  )
}

export function DocumentIntegrityPanel({ documentId }: DocumentIntegrityPanelProps) {
  const archiveQuery = useArchiveEntry(documentId)
  const prove = useProveDocument()
  const [dialogOpen, setDialogOpen] = useState(false)

  const isArchived = archiveQuery.isSuccess

  const handleProve = () => {
    setDialogOpen(true)
    prove.mutate(documentId)
  }

  return (
    <div className="flex items-center gap-2" data-testid="document-integrity-panel">
      {archiveQuery.isPending ? (
        <StatusBadge
          variant="outline-neutral"
          icon={Loader2}
          spinning
          label="Integrität wird geladen"
        />
      ) : isArchived ? (
        <StatusBadge
          variant="outline-success"
          icon={ShieldCheck}
          label={`GoBD-versiegelt seit ${formatDate(archiveQuery.data.archived_at)} · SHA-256`}
        />
      ) : (
        <StatusBadge
          variant="outline-neutral"
          icon={Shield}
          label="Noch nicht versiegelt"
        />
      )}

      <Button
        size="sm"
        variant="outline"
        onClick={handleProve}
        disabled={prove.isPending}
        data-testid="prove-integrity-button"
      >
        {prove.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
        )}
        Integrität beweisen
      </Button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Integritätsnachweis</DialogTitle>
            <DialogDescription>
              Das Original wird direkt aus dem Archiv-Storage geladen, neu
              gehasht und gegen die versiegelte Prüfsumme, die Beweiskette und
              den Zeitstempel geprüft.
            </DialogDescription>
          </DialogHeader>

          {prove.isPending && (
            <div
              className="flex items-center gap-3 py-6 justify-center text-muted-foreground"
              data-testid="integrity-loading"
            >
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              <span>Beweis wird geführt …</span>
            </div>
          )}

          {prove.isError && (
            <Alert variant="destructive" data-testid="integrity-error">
              <ShieldAlert className="h-5 w-5" />
              <AlertTitle>Beweisführung nicht möglich</AlertTitle>
              <AlertDescription>
                Die Prüfung konnte nicht durchgeführt werden (Server oder
                Storage nicht erreichbar). Bitte versuchen Sie es erneut oder
                informieren Sie den Administrator.
              </AlertDescription>
            </Alert>
          )}

          {prove.isSuccess && <ProofResult proof={prove.data} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
