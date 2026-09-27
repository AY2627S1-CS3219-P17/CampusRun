// AI Assistance Disclosure:
// Tool: Codex (model: GPT-5), date: 2026-09-28
// Scope: AI-assisted session storage and cross-tab sign-in handling.
// Author review: Validated per-tab isolation and same-user sign-out behaviour.

import { useSyncExternalStore } from 'react'

// Each tab stores its token under this key in its own sessionStorage. CHANGE_EVENT
// notifies React in the current tab when that tab's session changes.
const TOKEN_KEY = 'campusrun.accessToken'
const CHANGE_EVENT = 'campusrun:session'
const SESSION_CHANNEL = 'campusrun:session'

type Role = 'student' | 'admin'
type Session = {
  token: string
  userId: string
  role: Role
  expiresAt: number
}

// The User Service puts the account type in the "type" claim
type Claims = { sub?: unknown; type?: unknown; exp?: unknown }
type SignInMessage = { type: 'signed-in-elsewhere'; userId: string }

function decode(token: string): Session | null {
  try {
    const payload = token.split('.')[1]
    const claims = JSON.parse(
      atob(payload.replace(/-/g, '+').replace(/_/g, '/')),
    ) as Claims
    if (claims.type !== 'student' && claims.type !== 'admin') return null

    if (typeof claims.exp !== 'number' || claims.exp * 1000 < Date.now())
      return null
    return {
      token,
      userId: String(claims.sub),
      role: claims.type,
      expiresAt: claims.exp * 1000,
    }
  } catch {
    return null
  }
}

let cachedToken: string | null = null
let cachedSession: Session | null = null
const sessionChannel = new BroadcastChannel(SESSION_CHANNEL)

function isSignInMessage(value: unknown): value is SignInMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    'type' in value &&
    value.type === 'signed-in-elsewhere' &&
    'userId' in value &&
    typeof value.userId === 'string'
  )
}

sessionChannel.addEventListener('message', (event: MessageEvent<unknown>) => {
  const message = event.data
  if (!isSignInMessage(message)) return

  // A new session for this account replaces this tab's session. Sessions for
  // other accounts remain independent.
  if (getSession()?.userId === message.userId) clearSession()
})

export function getSession(): Session | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token !== cachedToken) {
    cachedToken = token
    cachedSession = token ? decode(token) : null
  }
  return cachedSession
}

export function saveToken(token: string): boolean {
  // False if token malformed/expired/unknown account type
  const trimmed = token.trim().replace(/^Bearer\s+/i, '')
  const session = decode(trimmed)
  if (!session) return false

  sessionStorage.setItem(TOKEN_KEY, trimmed)
  window.dispatchEvent(new Event(CHANGE_EVENT))
  sessionChannel.postMessage({
    type: 'signed-in-elsewhere',
    userId: session.userId,
  })
  return true
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange)

  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
  }
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession)
}
