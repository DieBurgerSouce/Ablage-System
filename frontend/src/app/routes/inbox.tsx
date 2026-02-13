/**
 * Smart Inbox Route
 *
 * Intelligenter Posteingang mit KI-basierter Priorisierung und Insights.
 */

import { createFileRoute } from '@tanstack/react-router'
import { SmartInboxPage } from '@/features/smart-inbox'

export const Route = createFileRoute('/inbox')({
  component: InboxRoute,
})

function InboxRoute() {
  return <SmartInboxPage />
}
