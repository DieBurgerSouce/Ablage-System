import { createFileRoute } from '@tanstack/react-router'
import { DocumentVolumeReport } from '@/features/reports/components/DocumentVolumeReport'

export const Route = createFileRoute('/reports/document-volume')({
  component: DocumentVolumeReport,
})
