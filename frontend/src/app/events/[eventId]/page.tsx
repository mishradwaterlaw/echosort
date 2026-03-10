import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import Link from 'next/link'
import PhotoUploader from '@/components/PhotoUploader'

export default async function EventDetailsPage({
  params
}: {
  params: Promise<{ eventId: string }>
}) {
  const { eventId } = await params
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

  // Fetch Event
  const eventRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/events/${eventId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  })
  if (!eventRes.ok) {
    if (eventRes.status === 403) return <div className="p-10 text-center">Not authorized</div>
    if (eventRes.status === 404) return <div className="p-10 text-center">Event not found</div>
    return <div className="p-10 text-center">Failed to load event</div>
  }
  const event = await eventRes.json()

  // Fetch photos
  const photosRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/events/${eventId}/photos`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  })
  
  let photos = []
  if (photosRes.ok) {
    const data = await photosRes.json()
    photos = data.photos || []
  }

  const shareUrl = `${process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'}/find/${eventId}`

  return (
    <main className="flex-1 p-6 sm:p-10 max-w-5xl mx-auto w-full">
      <div className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            {event.name}
          </h1>
          {event.event_date && (
            <p className="text-sm mt-1 text-[var(--text-muted)]">
              {new Date(event.event_date).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric'
              })}
            </p>
          )}
        </div>
        <div className="bg-[var(--space)] border border-[var(--border)] p-3 rounded-xl flex gap-3 items-center">
          <span className="text-xs text-[var(--text-muted)] font-medium">Share Link:</span>
          <code className="text-xs bg-[var(--charcoal)] px-2 py-1 rounded text-[var(--text-primary)] select-all overflow-hidden text-ellipsis whitespace-nowrap max-w-[200px] sm:max-w-xs block">
            {shareUrl}
          </code>
        </div>
      </div>

      <PhotoUploader eventId={eventId} getTokenAction={getToken} />

      <div className="mt-12">
        <h2 className="text-lg font-semibold mb-6 text-[var(--text-primary)]">Event Photos ({photos.length})</h2>
        {photos.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {photos.map((p: any) => (
              <div key={p.id} className="relative aspect-square bg-[var(--space)] rounded-xl overflow-hidden border border-[var(--border)] group">
                <div className="w-full h-full flex items-center justify-center">
                  <span style={{ color: 'var(--text-muted)' }} className="text-xs">
                    📷
                  </span>
                </div>
                <div className="absolute top-2 right-2 flex flex-col gap-1">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium shadow-sm bg-[var(--charcoal)] ${p.embedding_status === 'done' ? 'text-green-400' : 'text-yellow-400'}`}>
                    {p.embedding_status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-20 border border-[var(--border)] rounded-xl border-dashed">
            <p className="text-sm text-[var(--text-muted)]">No photos uploaded yet. Begin by uploading photos above.</p>
          </div>
        )}
      </div>
    </main>
  )
}
