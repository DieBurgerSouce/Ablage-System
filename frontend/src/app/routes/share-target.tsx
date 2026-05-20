/**
 * Share Target Redirect Route
 *
 * The PWA manifest uses /share-target as the action URL, but our
 * actual share handling logic is at /share. This route handles
 * the redirect and passes along all query parameters.
 *
 * This is necessary because the Web Share Target API requires
 * an exact URL match in the manifest.
 */

import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/share-target')({
  beforeLoad: ({ search }) => {
    // Preserve query parameters when redirecting
    const searchParams = new URLSearchParams()

    if (typeof search === 'object' && search !== null) {
      Object.entries(search).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.set(key, String(value))
        }
      })
    }

    const queryString = searchParams.toString()
    const targetPath = queryString ? `/share?${queryString}` : '/share'

    throw redirect({
      to: '/share',
      search: search as Record<string, string>,
    })
  },
  component: () => null, // Never rendered due to redirect
})
