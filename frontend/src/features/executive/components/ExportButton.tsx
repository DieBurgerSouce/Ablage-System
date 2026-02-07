/**
 * Export Button Component
 *
 * Triggers browser print/PDF export of the dashboard.
 */

import { Button } from '@/components/ui/button'
import { Printer } from 'lucide-react'

export function ExportButton() {
  const handleExport = () => {
    // Trigger browser print dialog (user can save as PDF)
    window.print()
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleExport}
      className="print:hidden"
    >
      <Printer className="h-4 w-4 mr-2" />
      Als PDF exportieren
    </Button>
  )
}
