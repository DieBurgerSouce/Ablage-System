import { createFileRoute } from '@tanstack/react-router'
import { CalendarSyncSettings } from '@/features/calendar/components/CalendarSyncSettings'

export const Route = createFileRoute('/admin/calendar-sync')({
  component: CalendarSyncSettings,
})
