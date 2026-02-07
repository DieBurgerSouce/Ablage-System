/**
 * Department Breakdown Component
 *
 * Table displaying statistics by department/area.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import type { DepartmentBreakdown as DepartmentBreakdownType } from '../types/executive-types'
import { Badge } from '@/components/ui/badge'

interface DepartmentBreakdownProps {
  departments: DepartmentBreakdownType[]
}

export function DepartmentBreakdown({ departments }: DepartmentBreakdownProps) {
  // Format processing time
  const formatTime = (ms: number) => {
    const seconds = ms / 1000
    if (seconds < 1) return `${ms.toFixed(0)}ms`
    return `${seconds.toFixed(1)}s`
  }

  // Format accuracy as percentage
  const formatAccuracy = (accuracy: number) => {
    return `${(accuracy * 100).toFixed(1)}%`
  }

  // Determine accuracy badge variant
  const getAccuracyBadge = (accuracy: number) => {
    if (accuracy >= 0.95) return 'default' // Excellent
    if (accuracy >= 0.85) return 'secondary' // Good
    return 'destructive' // Needs improvement
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Statistiken nach Bereichen</CardTitle>
        <CardDescription>
          Dokumentenverarbeitung gruppiert nach Dokumenttyp
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Bereich</TableHead>
                <TableHead className="text-right">Dokumente</TableHead>
                <TableHead className="text-right">Ø Verarbeitungszeit</TableHead>
                <TableHead className="text-right">Ø Genauigkeit</TableHead>
                <TableHead className="text-right">Ausstehend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {departments.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    Keine Daten verfügbar
                  </TableCell>
                </TableRow>
              ) : (
                departments.map((dept) => (
                  <TableRow key={dept.department}>
                    <TableCell className="font-medium">{dept.department}</TableCell>
                    <TableCell className="text-right">
                      {new Intl.NumberFormat('de-DE').format(dept.document_count)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatTime(dept.avg_processing_time_ms)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant={getAccuracyBadge(dept.accuracy)}>
                        {formatAccuracy(dept.accuracy)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {dept.pending_count > 0 ? (
                        <Badge variant="outline">
                          {new Intl.NumberFormat('de-DE').format(dept.pending_count)}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
