'use client'
import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const [light, setLight] = useState(false)

  useEffect(() => {
    // On mount, read saved preference
    const saved = localStorage.getItem('theme')
    if (saved === 'light') {
      document.documentElement.classList.add('light')
      setLight(true)
    }
  }, [])

  function toggle() {
    const next = !light
    setLight(next)
    if (next) {
      document.documentElement.classList.add('light')
      localStorage.setItem('theme', 'light')
    } else {
      document.documentElement.classList.remove('light')
      localStorage.setItem('theme', 'dark')
    }
  }

  return (
    <button
      onClick={toggle}
      style={{ color: 'var(--text-muted)' }}
      className="text-xs hover:opacity-75 transition-opacity"
      aria-label="Toggle theme"
    >
      {light ? '◐ Dark' : '◑ Light'}
    </button>
  )
}
