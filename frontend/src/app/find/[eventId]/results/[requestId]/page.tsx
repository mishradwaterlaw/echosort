import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import PollResultsClient from './PollResultsClient'

/**
 * Question: The results page needs to auto-refresh every 3 seconds while status is pending. 
 * Should this polling happen in a Server Component or a Client Component — and why can't it be a Server Component?
 * 
 * Answer: Polling must happen in a Client Component. Server Components run once on the server per request 
 * and stream the output to the client. They do not maintain a continuous connection or execute intervals 
 * like `setInterval` that can push new UI updates to the browser. To achieve a 3-second auto-refresh without 
 * full page reloads via a meta tag or router.refresh() (which is heavy), we must use a Client Component 
 * where `useEffect` and `setInterval` can run in the browser to periodically fetch updates and trigger React state re-renders.
 */

export default async function MatchResultsPage({
  params
}: {
  params: Promise<{ eventId: string, requestId: string }>
}) {
  const { eventId, requestId } = await params
  
  // Requirement 1: Auth guard
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  // Server Action
  async function getToken() {
    'use server'
    const authSupa = await createClient()
    const { data: { user } } = await authSupa.auth.getUser()
    if (!user) return undefined
    const { data: { session } } = await authSupa.auth.getSession()
    return session?.access_token
  }

  // Requirement 2: Fetch GET /matches/{requestId}
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const matchRes = await fetch(`${apiUrl}/matches/${requestId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  })

  // Basic API errors
  if (!matchRes.ok) {
    if (matchRes.status === 403) return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10"><h2 className="text-xl font-semibold mb-2">Access Denied</h2><p className="text-[var(--text-muted)]">Not authorized to view this match request.</p></div>
    if (matchRes.status === 404) return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10"><h2 className="text-xl font-semibold mb-2">Match Request Not Found</h2><p className="text-[var(--text-muted)]">We couldn't find this match request.</p></div>
    return <div className="min-h-[60vh] flex flex-col items-center justify-center p-10"><h2 className="text-xl font-semibold mb-2">Error</h2><p className="text-[var(--text-muted)]">There was an error communicating with the server.</p></div>
  }

  const matchData = await matchRes.json()
  const status = matchData.status

  // Requirement 5: If status is failed, show friendly error
  if (status === 'failed') {
    return (
      <main className="flex-1 p-6 sm:p-10 max-w-5xl mx-auto w-full flex flex-col items-center justify-center min-h-[60vh]">
        <div className="text-center p-8 bg-[var(--space)] border border-[var(--border)] rounded-2xl max-w-md w-full">
          <span className="text-4xl block mb-4">❌</span>
          <h2 className="text-xl font-semibold mb-2 text-[var(--text-primary)]">Something went wrong</h2>
          <p className="text-sm text-[var(--text-muted)] mb-6">
            We couldn't process your selfie or find matching photos. Please try again with a clearer picture.
          </p>
          <a
            href={`/find/${eventId}`}
            className="inline-block py-3 px-6 bg-[var(--rose)] text-white rounded-xl font-medium shadow-sm hover:opacity-90 transition-opacity"
          >
            Try Again
          </a>
        </div>
      </main>
    )
  }

  // Requirement 3: If status pending/processing -> auto refresh every 3 seconds
  if (status === 'pending' || status === 'processing') {
    return (
      <main className="flex-1 p-6 sm:p-10 max-w-5xl mx-auto w-full flex flex-col items-center justify-center min-h-[60vh]">
        <div className="text-center max-w-md w-full p-10">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--rose)] mx-auto mb-6"></div>
          <h2 className="text-xl font-bold mb-2 text-[var(--text-primary)]">
            Finding Your Photos...
          </h2>
          <p className="text-[var(--text-muted)] mb-8">
            Analyzing faces. This may take a minute depending on the size of the event.
          </p>
          
          <PollResultsClient requestId={requestId} getTokenAction={getToken} />
        </div>
      </main>
    )
  }

  // Requirement 4: If status done -> show photo grid with signed URLs
  const photos = matchData.photos || []

  return (
    <main className="flex-1 p-6 sm:p-10 max-w-5xl mx-auto w-full">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            Your Matched Photos
          </h1>
          <p className="text-sm mt-1 text-[var(--text-muted)]">
            We found {photos.length} {photos.length === 1 ? 'photo' : 'photos'} of you at this event.
          </p>
        </div>
        <a
          href={`/find/${eventId}`}
          className="text-sm font-medium text-[var(--text-primary)] bg-[var(--charcoal)] hover:bg-[var(--space)] border border-[var(--border)] px-4 py-2 rounded-lg transition-colors"
        >
          New Search
        </a>
      </div>

      {photos.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {photos.map((p: any) => (
            <div key={p.id} className="relative aspect-square bg-[var(--space)] rounded-xl overflow-hidden border border-[var(--border)] group">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img 
                src={p.signed_url} 
                alt="Matched photo" 
                className="object-cover w-full h-full opacity-90 group-hover:opacity-100 transition-opacity" 
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-20 border border-[var(--border)] rounded-xl border-dashed">
          <span className="text-4xl block mb-4">👻</span>
          <p className="text-[var(--text-primary)] font-medium mb-1">No matches found</p>
          <p className="text-sm text-[var(--text-muted)]">We couldn't find your face in any photos from this event.</p>
        </div>
      )}
    </main>
  )
}
