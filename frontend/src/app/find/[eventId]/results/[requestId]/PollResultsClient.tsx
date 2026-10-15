'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

export default function PollResultsClient({
  requestId,
  getTokenAction
}: {
  requestId: string,
  getTokenAction: () => Promise<string | undefined>
}) {
  const router = useRouter()

  // Store the interval ID in a ref so the cleanup function below can cancel it.
  // Q: Why useRef and not useState?
  // A: We only need to cancel the interval on unmount — we never render the ID to the UI.
  //    useRef holds a mutable value without triggering re-renders, which is exactly what
  //    we want for something that's purely a side-effect handle.
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

    intervalRef.current = setInterval(async () => {
      // Q: Why call getTokenAction() inside the interval, not once before it starts?
      // A: Supabase access tokens expire after 1 hour. If we fetch the token once
      //    at the start and the user's session naturally refreshes (Supabase silently
      //    rotates it), the old token we captured becomes invalid and every poll tick
      //    returns a 401. Calling getTokenAction() on each tick invokes a Server Action
      //    that re-reads the session from the server-side cookie, which Supabase has
      //    already refreshed. This ensures we always send a valid, current token.
      try {
        const token = await getTokenAction()
        if (!token) {
          // If we can't get a token, the user's session has fully expired.
          // Stop polling — they need to log in again.
          clearInterval(intervalRef.current!)
          intervalRef.current = null
          return
        }

        const res = await fetch(`${apiUrl}/matches/${requestId}`, {
          headers: { 'Authorization': `Bearer ${token}` },
          cache: 'no-store'
        })

        if (res.ok) {
          const data = await res.json()
          if (data.status === 'done' || data.status === 'failed') {
            // Job finished: tell Next.js to re-render this Server Component with fresh data.
            // router.refresh() re-fetches the page from the server without a full navigation.
            router.refresh()
            clearInterval(intervalRef.current!)
            intervalRef.current = null
          }
        }
      } catch (err) {
        console.error('Error polling match status', err)
      }
    }, 3000)

    // Cleanup: this runs when the component unmounts (user navigates away).
    // Without this, the interval keeps firing fetch() calls indefinitely,
    // even after the component is gone — a classic React memory leak.
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]) // Only re-run if the requestId changes (it won't — but this is the correct dep)

  return null // Headless component, just performs logic to tell Server Component router to refresh
}
