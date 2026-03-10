import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import Link from 'next/link'
import { SubmitButton } from '@/components/SubmitButton'

/*
  Why Server Actions for auth instead of a client-side fetch() to our FastAPI backend?

  With a Server Action the user's credentials (email + password) travel from the
  browser directly to our Next.js server over a single HTTPS request. The server
  then talks to Supabase — the credentials never touch client-side JS and never
  traverse a second network hop to FastAPI.

  If we used a client-side fetch():
    1. Credentials would live in browser memory inside JS — accessible to XSS.
    2. They'd travel browser → FastAPI → Supabase — two hops, double the attack surface.
    3. We'd need CORS config plus a separate API endpoint just to proxy auth.

  Server Actions keep credentials on the shortest, most secure path:
    Browser form POST → Next.js server (same origin) → Supabase Auth.
*/

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>
}) {
  const params = await searchParams

  async function loginAction(formData: FormData) {
    'use server'

    const friendlyError = (msg: string) => {
      if (msg.includes('Invalid login')) return 'Invalid email or password'
      if (msg.includes('Email not confirmed')) return 'Please confirm your email first'
      return 'Something went wrong. Please try again.'
    }

    const email = formData.get('email') as string
    const password = formData.get('password') as string

    const supabase = await createClient()
    const { error } = await supabase.auth.signInWithPassword({ email, password })

    if (error) {
      redirect(`/login?error=${encodeURIComponent(friendlyError(error.message))}`)
    }

    redirect('/dashboard')
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">Welcome back</h1>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-foreground">
            Sign in to your EchoSort account
          </h2>
        </div>

        {params.error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {params.error}
          </div>
        )}

        <form action={loginAction} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium mb-1.5">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              placeholder="you@example.com"
              className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-100 transition"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1.5">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              placeholder="••••••••"
              className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-100 transition"
            />
          </div>
          <SubmitButton label="Sign In" />
        </form>

        <p className="text-center text-sm text-zinc-500 dark:text-zinc-400">
          Don&apos;t have an account?{' '}
          <Link href="/signup" className="font-medium text-zinc-900 dark:text-white hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  )
}
