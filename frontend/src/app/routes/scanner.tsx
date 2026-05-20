import { createFileRoute } from '@tanstack/react-router'
import { ScannerPage } from '@/features/scanner/components/ScannerPage'

export const Route = createFileRoute('/scanner')({
  component: ScannerPage,
})
