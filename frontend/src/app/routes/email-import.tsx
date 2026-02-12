import { createFileRoute } from '@tanstack/react-router'
import { EmailInboxPage } from '@/features/email/components/EmailInboxPage'

export const Route = createFileRoute('/email-import')({
  component: EmailInboxPage,
})
