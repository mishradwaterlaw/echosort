import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import Link from 'next/link'
import { CreateEventForm } from '@/components/CreateEventForm'

type Event = {
  id: string
  name: string
  description: string | null
  event_date: string | null
  created_at: string
  is_active: boolean
}

async function createEventAction(body: object) {
  'use server'
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/events`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    cache: 'no-store',
  })

  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail || 'Failed to create event')
  }

  return res.json()
}

export default async function DashboardPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  let events: Event[] = []
  let fetchError: string | null = null

  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/events`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    if (res.ok) {
      events = await res.json()
    } else {
      fetchError = 'Failed to load events'
    }
  } catch {
    fetchError = 'Could not connect to the API'
  }

  return (
    <main className="flex-1 p-6 sm:p-10 max-w-5xl mx-auto w-full">

      {/* Header */}
      <div className="mb-8">
        <h1
          style={{ color: 'var(--text-primary)' }}
          className="text-2xl font-bold tracking-tight"
        >
          Your Events
        </h1>
        <p style={{ color: 'var(--text-muted)' }} className="text-sm mt-1">
          Manage your photo albums and share them with attendees
        </p>
      </div>

      {/* Create form — token stays on server via Server Action */}
      <CreateEventForm onSubmit={createEventAction} />

      {/* Error */}
      {fetchError && (
        <div
          style={{ borderColor: 'var(--copper)', color: 'var(--rose)' }}
          className="rounded-lg border px-4 py-3 text-sm mb-6"
        >
          {fetchError}
        </div>
      )}

      {/* Grid */}
      {events.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {events.map((event) => (
            <Link
              key={event.id}
              href={`/events/${event.id}`}
              style={{
                backgroundColor: 'var(--space)',
                borderColor: 'var(--border)',
              }}
              className="group rounded-xl border p-5 hover:border-[var(--rose)] transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <h2
                  style={{ color: 'var(--text-primary)' }}
                  className="font-semibold text-base leading-snug group-hover:text-[var(--rose)] transition-colors"
                >
                  {event.name}
                </h2>
                <span
                  style={{
                    backgroundColor: event.is_active ? 'var(--charcoal)' : 'transparent',
                    color: event.is_active ? 'var(--rose)' : 'var(--text-muted)',
                    border: event.is_active ? 'none' : '1px solid var(--border)',
                  }}
                  className="text-xs px-2 py-0.5 rounded-full shrink-0"
                >
                  {event.is_active ? 'Active' : 'Closed'}
                </span>
              </div>

              {event.description && (
                <p
                  style={{ color: 'var(--text-muted)' }}
                  className="text-sm mt-2 line-clamp-2"
                >
                  {event.description}
                </p>
              )}

              <div
                style={{ color: 'var(--text-muted)' }}
                className="mt-4 flex items-center gap-3 text-xs"
              >
                {event.event_date && (
                  <span>
                    {new Date(event.event_date).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric'
                    })}
                  </span>
                )}
                <span style={{ color: 'var(--charcoal)' }}>·</span>
                <span>
                  Created {new Date(event.created_at).toLocaleDateString()}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        !fetchError && (
          <div className="text-center py-20">
            <p style={{ color: 'var(--text-muted)' }} className="text-base font-medium">
              No events yet
            </p>
            <p style={{ color: 'var(--text-muted)' }} className="text-sm mt-1 opacity-60">
              Create your first event to get started
            </p>
          </div>
        )
      )}
    </main>
  )
}
