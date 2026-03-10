import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

// Returns a Supabase client for use in Server Components and Server Actions.
// Why async? → cookies() is async in Next.js 14. The server client needs to
// read and write cookies to persist the user's auth session across requests.
export async function createClient() {
  const cookieStore = await cookies()

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // setAll called from a Server Component (read-only context).
            // Safe to ignore — middleware will handle session refresh.
          }
        },
      },
    }
  )
}
