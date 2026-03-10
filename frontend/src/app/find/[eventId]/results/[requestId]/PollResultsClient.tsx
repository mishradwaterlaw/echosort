'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function PollResultsClient({ 
  requestId,
  getTokenAction
}: { 
  requestId: string,
  getTokenAction: () => Promise<string | undefined>
}) {
  const router = useRouter()

  useEffect(() => {
    let interval: NodeJS.Timeout

    const startPolling = async () => {
      try {
        const token = await getTokenAction()
        if (!token) return

        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

        interval = setInterval(async () => {
          try {
            const res = await fetch(`${apiUrl}/events/matches/${requestId}`, {
              headers: { 'Authorization': `Bearer ${token}` },
              cache: 'no-store'
            })

            if (res.ok) {
              const data = await res.json()
              if (data.status === 'done' || data.status === 'failed') {
                router.refresh()
                clearInterval(interval)
              }
            }
          } catch (err) {
            console.error('Error polling match status', err)
          }
        }, 3000)
      } catch (err) {
        console.error('Failed to initialize polling', err)
      }
    }

    startPolling()
    
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [requestId, router, getTokenAction])

  return null // Headless component, just performs logic to tell Server Component router to refresh
}
