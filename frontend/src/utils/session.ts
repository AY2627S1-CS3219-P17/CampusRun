// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-assisted review and debugging for storage of the access token and the signed-in user's role.
// Author review: <to be completed by author>

import { useSyncExternalStore } from 'react'

// The User Service's login will save its access token under this key. Until
// then, a development token from supplier-service/scripts/make_token.py is saved here.
const TOKEN_KEY = 'campusrun.accessToken'
const CHANGE_EVENT = 'campusrun:session'

export type Role = 'student' | 'admin'

export type Session = {
  token: string
  userId: string
  role: Role
  expiresAt: number
}

type Claims = { sub?: unknown; role?: unknown; exp?: unknown }

function decode(token: string): Session | null {
  try {
    const payload = token.split('.')[1]
    const claims = JSON.parse(
      atob(payload.replace(/-/g, '+').replace(/_/g, '/')),
    ) as Claims
    if (claims.role !== 'student' && claims.role !== 'admin') return null
    if (typeof claims.exp !== 'number' || claims.exp * 1000 < Date.now())
      return null
    return {
      token,
      userId: String(claims.sub),
      role: claims.role,
      expiresAt: claims.exp * 1000,
    }
  } catch {
    return null
  }
}

let cachedToken: string | null = null
let cachedSession: Session | null = null

// Only used to decide what to show. The services check the token themselves.
export function getSession(): Session | null {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token !== cachedToken) {
    cachedToken = token
    cachedSession = token ? decode(token) : null
  }
  return cachedSession
}

// Returns false if the token is malformed, expired or has no known role
export function saveToken(token: string): boolean {
  const trimmed = token.trim().replace(/^Bearer\s+/i, '')
  if (!decode(trimmed)) return false
  localStorage.setItem(TOKEN_KEY, trimmed)
  window.dispatchEvent(new Event(CHANGE_EVENT))
  return true
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange)
  // Signing out in another tab
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession)
}
