/**
 * ImportConflictPreview - Konflikt-Anzeige für Lexware Import
 *
 * WICHTIG: Types müssen EXAKT mit Backend übereinstimmen!
 * @see app/api/v1/lexware.py:ConflictInfo
 *
 * Zeigt Konflikte zwischen Folie- und Messer-Daten an:
 * - Kritische Konflikte (rot): Kundennummer, IBAN Unterschiede
 * - Harmlose Konflikte (gelb): Name, Adresse Unterschiede
 * - Duplikate (blau): Gleiche Daten in beiden Dateien
 */

import { useState } from 'react'
import {
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Copy,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { ConflictInfo } from '../api/lexware-admin-api'

interface ImportConflictPreviewProps {
  conflicts: ConflictInfo[]
}

export function ImportConflictPreview({ conflicts }: ImportConflictPreviewProps) {
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set())

  const toggleExpanded = (identifier: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev)
      if (next.has(identifier)) {
        next.delete(identifier)
      } else {
        next.add(identifier)
      }
      return next
    })
  }

  // Group by conflict type
  const criticalConflicts = conflicts.filter((c) => c.conflict_type === 'critical')
  const harmlessConflicts = conflicts.filter((c) => c.conflict_type === 'harmless')
  const duplicateConflicts = conflicts.filter((c) => c.conflict_type === 'duplicate')

  if (conflicts.length === 0) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <CheckCircle className="h-12 w-12 text-green-500" />
            <p className="font-medium text-lg">Keine Konflikte gefunden</p>
            <p className="text-muted-foreground">
              Alle Datensätze stimmen zwischen Folie und Messer überein.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-500" />
          Konflikte zwischen Folie und Messer
        </CardTitle>
        <CardDescription>
          {conflicts.length} Unterschiede zwischen den Lexware-Exporten gefunden
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Summary Badges */}
        <div className="flex flex-wrap gap-2">
          {criticalConflicts.length > 0 && (
            <Badge variant="destructive" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              {criticalConflicts.length} kritisch
            </Badge>
          )}
          {harmlessConflicts.length > 0 && (
            <Badge
              variant="outline"
              className="gap-1 bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950 dark:text-yellow-300 dark:border-yellow-800"
            >
              <AlertTriangle className="h-3 w-3" />
              {harmlessConflicts.length} harmlos
            </Badge>
          )}
          {duplicateConflicts.length > 0 && (
            <Badge
              variant="outline"
              className="gap-1 bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800"
            >
              <Copy className="h-3 w-3" />
              {duplicateConflicts.length} Duplikate
            </Badge>
          )}
        </div>

        {/* Explanation */}
        <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg">
          <p className="font-medium mb-1">Konflikt-Typen:</p>
          <ul className="list-disc list-inside space-y-1">
            <li><span className="text-red-600 dark:text-red-400">Kritisch:</span> Wichtige Felder unterscheiden sich (z.B. Kundennummer, IBAN)</li>
            <li><span className="text-yellow-600 dark:text-yellow-400">Harmlos:</span> Unwichtige Felder unterscheiden sich (z.B. Schreibweise)</li>
            <li><span className="text-blue-600 dark:text-blue-400">Duplikat:</span> Datensatz existiert in beiden Dateien identisch</li>
          </ul>
        </div>

        {/* Conflict List */}
        <div className="space-y-2">
          {conflicts.map((conflict) => {
            const isExpanded = expandedItems.has(conflict.identifier)

            return (
              <Collapsible
                key={conflict.identifier}
                open={isExpanded}
                onOpenChange={() => toggleExpanded(conflict.identifier)}
              >
                <div
                  className={`border rounded-lg ${
                    conflict.conflict_type === 'critical'
                      ? 'border-red-200 dark:border-red-800'
                      : conflict.conflict_type === 'harmless'
                      ? 'border-yellow-200 dark:border-yellow-800'
                      : 'border-blue-200 dark:border-blue-800'
                  }`}
                >
                  <CollapsibleTrigger asChild>
                    <div
                      className={`flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 rounded-t-lg ${
                        conflict.conflict_type === 'critical'
                          ? 'bg-red-50 dark:bg-red-950/20'
                          : conflict.conflict_type === 'harmless'
                          ? 'bg-yellow-50 dark:bg-yellow-950/20'
                          : 'bg-blue-50 dark:bg-blue-950/20'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        <div>
                          <span className="font-medium">{conflict.identifier}</span>
                        </div>
                        <ConflictTypeBadge type={conflict.conflict_type} />
                      </div>
                    </div>
                  </CollapsibleTrigger>

                  <CollapsibleContent>
                    <div className="p-3 border-t">
                      {/* Reason */}
                      <p className="text-sm text-muted-foreground mb-3">
                        {conflict.reason}
                      </p>

                      {/* Value Comparison Table */}
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-[200px]">Quelle</TableHead>
                            <TableHead>Wert</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">
                              Spargel Folie GmbH
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {conflict.folie_value || <span className="italic">nicht vorhanden</span>}
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">
                              Spargel Messer GmbH
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {conflict.messer_value || <span className="italic">nicht vorhanden</span>}
                            </TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function ConflictTypeBadge({ type }: { type: ConflictInfo['conflict_type'] }) {
  switch (type) {
    case 'critical':
      return (
        <Badge variant="destructive" className="text-xs">
          Kritisch
        </Badge>
      )
    case 'harmless':
      return (
        <Badge
          variant="outline"
          className="text-xs bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950 dark:text-yellow-300 dark:border-yellow-800"
        >
          Harmlos
        </Badge>
      )
    case 'duplicate':
      return (
        <Badge
          variant="outline"
          className="text-xs bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800"
        >
          Duplikat
        </Badge>
      )
    default:
      return null
  }
}
