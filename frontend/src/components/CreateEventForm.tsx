'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

type Props = {
  // Server Action passed as prop — token never reaches the browser
  onSubmit: (body: object) => Promise<unknown>
}

export function CreateEventForm({ onSubmit }: Props) {
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const formData = new FormData(e.currentTarget)
    const body = {
      name: formData.get('name') as string,
      description: (formData.get('description') as string) || null,
      event_date: (formData.get('event_date') as string) || null,
    }

    try {
      await onSubmit(body)
      setIsOpen(false)
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const inputClass = "w-full rounded-lg px-3 py-2 text-sm outline-none transition"
  const inputStyle = {
    backgroundColor: 'var(--ink)',
    border: '1px solid var(--charcoal)',
    color: 'var(--text-primary)',
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{ backgroundColor: 'var(--copper)', color: '#F0EDE8' }}
        className="mb-8 rounded-lg px-5 py-2.5 text-sm font-semibold hover:opacity-90 transition-opacity"
      >
        + Create Event
      </button>
    )
  }

  return (
    <div
      style={{ backgroundColor: 'var(--space)', borderColor: 'var(--border)' }}
      className="mb-8 rounded-xl border p-5"
    >
      <h2 style={{ color: 'var(--text-primary)' }} className="text-base font-semibold mb-4">
        New Event
      </h2>

      {error && (
        <div
          style={{ color: 'var(--rose)', borderColor: 'var(--copper)' }}
          className="rounded-lg border px-4 py-3 text-sm mb-4"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label style={{ color: 'var(--text-muted)' }} className="block text-xs font-medium mb-1.5 uppercase tracking-wider">
            Event Name <span style={{ color: 'var(--rose)' }}>*</span>
          </label>
          <input
            name="name" type="text" required
            placeholder="e.g. Annual Company Retreat 2026"
            className={inputClass} style={inputStyle}
          />
        </div>
        <div>
          <label style={{ color: 'var(--text-muted)' }} className="block text-xs font-medium mb-1.5 uppercase tracking-wider">
            Description
          </label>
          <input
            name="description" type="text"
            placeholder="Optional short description"
            className={inputClass} style={inputStyle}
          />
        </div>
        <div>
          <label style={{ color: 'var(--text-muted)' }} className="block text-xs font-medium mb-1.5 uppercase tracking-wider">
            Event Date
          </label>
          <input
            name="event_date" type="date"
            className={inputClass} style={inputStyle}
          />
        </div>
        <div className="flex gap-3 pt-1">
          <button
            type="submit" disabled={loading}
            style={{ backgroundColor: 'var(--copper)', color: '#F0EDE8' }}
            className="rounded-lg px-5 py-2.5 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {loading ? 'Creating...' : 'Create Event'}
          </button>
          <button
            type="button"
            onClick={() => { setIsOpen(false); setError(null) }}
            style={{ borderColor: 'var(--charcoal)', color: 'var(--text-muted)' }}
            className="rounded-lg border px-5 py-2.5 text-sm font-medium hover:opacity-75 transition-opacity"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
