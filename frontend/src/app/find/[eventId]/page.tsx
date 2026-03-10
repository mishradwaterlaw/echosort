import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import SelfieCapture from '@/components/SelfieCapture'
import AttendeeFlowClientWrapper from './AttendeeFlowClientWrapper'

export default async function AttendeeFindPage({
  params
}: {
  params: Promise<{ eventId: string }>
}) {
  const { eventId } = await params
  
  // Requirement 2: Require login for now
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  // Server Action to return token to client
  async function getToken() {
    'use server'
    const authSupa = await createClient()
    const { data: { user } } = await authSupa.auth.getUser()
    if (!user) return undefined
    const { data: { session } } = await authSupa.auth.getSession()
    return session?.access_token
  }

  // Requirement 1: Verify event exists and is active
  const eventRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/events/${eventId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  })
  
  if (!eventRes.ok) {
    if (eventRes.status === 403) return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10 text-center"><h2 className="text-xl font-semibold mb-2">Access Denied</h2><p className="text-[var(--text-muted)]">You do not have permission to view this event.</p></div>
    if (eventRes.status === 404) return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10 text-center"><h2 className="text-xl font-semibold mb-2">Event Not Found</h2><p className="text-[var(--text-muted)]">This event does not exist or has been disabled.</p></div>
    return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10 text-center"><h2 className="text-xl font-semibold mb-2">Error</h2><p className="text-[var(--text-muted)]">Failed to load event information.</p></div>
  }
  
  const event = await eventRes.json()

  return (
    <main className="flex-1 p-6 sm:p-10 max-w-3xl mx-auto w-full flex flex-col items-center">
      <div className="text-center mb-10 w-full max-w-md">
        <span className="text-xs font-semibold px-3 py-1 bg-[var(--charcoal)] text-[var(--rose)] border border-[var(--border)] rounded-full mb-4 inline-block tracking-wider uppercase">
          Find Your Photos
        </span>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--text-primary)] mt-2">
          {event.name}
        </h1>
        <p className="text-[var(--text-muted)] mt-3 leading-relaxed">
          Take a selfie or upload a clear photo of your face, and AI will find all photos of you from this event.
        </p>
      </div>

      <div className="w-full mt-4">
        <AttendeeFlowClientWrapper eventId={eventId} getTokenAction={getToken} />
      </div>
    </main>
  )
}
