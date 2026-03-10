import { createBrowserClient } from '@supabase/ssr'

// Returns a Supabase client for use in Client Components ("use client").
// Why a function instead of a direct export?
// → Prevents multiple instances being created across React's re-render cycle.
//   Each call reuses the same singleton internally via @supabase/ssr.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
