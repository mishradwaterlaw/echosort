import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import "./globals.css"
import { createClient } from "@/lib/supabase/server"
import Link from "next/link"
import { ThemeToggle } from "@/components/ThemeToggle"

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: "EchoSort",
  description: "AI-powered photo discovery for your events.",
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-screen flex flex-col`}>
        <nav
          style={{
            backgroundColor: 'var(--space)',
            borderBottom: '1px solid var(--border)',
          }}
          className="flex items-center justify-between px-6 py-4"
        >
          {/* Left: Brand */}
          <Link
            href="/"
            style={{ color: 'var(--text-primary)' }}
            className="font-semibold text-base tracking-tight hover:opacity-75 transition-opacity"
          >
            Face<span style={{ color: 'var(--rose)' }}>Find</span>
          </Link>

          {/* Right: Auth + Theme */}
          <div className="flex items-center gap-5 text-sm">
            <ThemeToggle />
            {user ? (
              <>
                <span
                  style={{ color: 'var(--text-muted)' }}
                  className="hidden sm:inline-block text-xs"
                >
                  {user.email}
                </span>
                <form action="/auth/signout" method="post">
                  <button
                    type="submit"
                    style={{ color: 'var(--rose)' }}
                    className="font-medium hover:opacity-75 transition-opacity text-sm"
                  >
                    Sign Out
                  </button>
                </form>
              </>
            ) : (
              <Link
                href="/login"
                style={{ color: 'var(--text-primary)' }}
                className="font-medium hover:opacity-75 transition-opacity"
              >
                Login
              </Link>
            )}
          </div>
        </nav>

        <div className="flex-1 flex flex-col">
          {children}
        </div>
      </body>
    </html>
  )
}
