'use client'

import { useRouter } from 'next/navigation'
import SelfieCapture from '@/components/SelfieCapture'

export default function AttendeeFlowClientWrapper({ 
  eventId, 
  getTokenAction 
}: { 
  eventId: string, 
  getTokenAction: () => Promise<string | undefined> 
}) {
  const router = useRouter()
  return (
    <SelfieCapture 
      eventId={eventId} 
      getTokenAction={getTokenAction} 
      onSuccess={(requestId) => router.push(`/find/${eventId}/results/${requestId}`)} 
    />
  )
}
