// AI Assistance Disclosure:
// Tool: Codex (model: GPT-5), date: 2026-09-28
// Scope: AI-assisted session storage and cross-tab sign-in handling.
// Author review: Validated per-tab isolation and same-user sign-out behaviour.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-28
// Scope: AI-changed the session to read the "role" claim instead of "type".
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-added refresh tokens: one refresh at a time per tab, refreshing before the access token runs out,
//        logging out on the server, and signing out a duplicated tab so it can't trip reuse detection.
// Author review: I tested the behaviour: the access token refreshes before it expires and a failed refresh logs out.

import { useSyncExternalStore } from 'react'
import type { Role } from '../types/user'

// Each tab keeps its tokens in its own sessionStorage. CHANGE_EVENT notifies
// React in the current tab when that tab's session changes.
const TOKEN_KEY = 'campusrun.accessToken'
const REFRESH_KEY = 'campusrun.refreshToken'
// A random id per sign-in, so tabs can tell whether they hold the same session
// without sharing the refresh token itself
const SESSION_ID_KEY = 'campusrun.sessionId'
// When the access token runs out, by this browser's clock (see storeTokens)
const EXPIRES_KEY = 'campusrun.accessTokenExpiresAt'
const CHANGE_EVENT = 'campusrun:session'
const SESSION_CHANNEL = 'campusrun:session'
const REFRESH_URL = '/api/users/auth/refresh'
const LOGOUT_URL = '/api/users/auth/logout'
// Refresh this long before the access token runs out (it lasts 5 minutes), or
// at half its lifetime if that's sooner, so a refresh never follows straight on
// from another even with a very short token
const REFRESH_AHEAD_MS = 60_000
// After a failed attempt (e.g. the User Service is down), try again this soon
const RETRY_MS = 15_000
// How long a freshly loaded tab waits to hear whether it's a duplicate before
// it may refresh. Tabs answer over BroadcastChannel within milliseconds.
const DUPLICATE_CHECK_MS = 300

type Session = {
  token: string
  userId: string
  role: Role
  // Milliseconds, by this browser's clock
  expiresAt: number
  lifetimeMs: number
}

// The User Service puts the user's role in the "role" claim
type Claims = { sub?: unknown; role?: unknown; exp?: unknown; iat?: unknown }
type ChannelMessage =
  | { type: 'signed-in-elsewhere'; userId: string }
  | { type: 'session-opened'; sessionId: string; tabId: string }
  | { type: 'session-in-use'; sessionId: string; tabId: string }

// Not crypto.randomUUID(): that only exists on https or localhost, and the app
// is also opened over plain http (e.g. from a phone on the same network)
function randomId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

// Changes on every page load, so a duplicated tab and its original differ
const TAB_ID = randomId()

function decode(token: string): Session | null {
  try {
    const payload = token.split('.')[1]
    const claims = JSON.parse(
      atob(payload.replace(/-/g, '+').replace(/_/g, '/')),
    ) as Claims
    if (claims.role !== 'student' && claims.role !== 'admin') return null
    if (typeof claims.exp !== 'number') return null
    const lifetimeMs =
      typeof claims.iat === 'number' ? (claims.exp - claims.iat) * 1000 : 0
    return {
      token,
      userId: String(claims.sub),
      role: claims.role,
      // Replaced by the stored local expiry when there is one (getSession)
      expiresAt: claims.exp * 1000,
      lifetimeMs,
    }
  } catch {
    return null
  }
}

let cachedToken: string | null = null
let cachedSession: Session | null = null
const sessionChannel = new BroadcastChannel(SESSION_CHANNEL)

function isChannelMessage(value: unknown): value is ChannelMessage {
  if (typeof value !== 'object' || value === null || !('type' in value))
    return false
  if (value.type === 'signed-in-elsewhere')
    return 'userId' in value && typeof value.userId === 'string'
  return (
    (value.type === 'session-opened' || value.type === 'session-in-use') &&
    'sessionId' in value &&
    typeof value.sessionId === 'string' &&
    'tabId' in value &&
    typeof value.tabId === 'string'
  )
}

sessionChannel.addEventListener('message', (event: MessageEvent<unknown>) => {
  const message = event.data
  if (!isChannelMessage(message)) return
  const sessionId = sessionStorage.getItem(SESSION_ID_KEY)

  switch (message.type) {
    case 'signed-in-elsewhere':
      // A new session for this account replaces this tab's session, which is
      // ended on the server too. Sessions for other accounts stay independent.
      if (getSession()?.userId === message.userId) void signOut()
      break
    case 'session-opened':
      // Another tab has just loaded with this tab's session: it's a duplicate
      // (e.g. "Duplicate tab" copies sessionStorage). Tell it.
      if (sessionId === message.sessionId)
        sessionChannel.postMessage({
          type: 'session-in-use',
          sessionId,
          tabId: message.tabId,
        })
      break
    case 'session-in-use':
      // This tab is the duplicate. Both tabs holding one refresh token would
      // look like a stolen token to the server, which would end the session for
      // both, so this tab gives it up. Locally only: logging out on the server
      // would end the original tab's session too.
      if (message.tabId === TAB_ID && sessionId === message.sessionId)
        clearSession()
      break
  }
})

export function getSession(): Session | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token !== cachedToken) {
    cachedToken = token
    cachedSession = token ? decode(token) : null
    const expiresAt = Number(sessionStorage.getItem(EXPIRES_KEY))
    if (cachedSession && expiresAt > 0) cachedSession.expiresAt = expiresAt
  }
  if (!cachedSession) return null
  // An expired access token still counts as signed in while there's a refresh
  // token to renew it with; requests refresh it first (see api/client.ts)
  if (cachedSession.expiresAt <= Date.now() && !getRefreshToken()) return null
  return cachedSession
}

function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY)
}

function notifyChange() {
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

function storeTokens(accessToken: string, refreshToken: string): boolean {
  const session = decode(accessToken)
  if (!session) return false
  // exp is the server's clock. Counting the lifetime from now, on this
  // browser's clock, keeps a fast or slow device clock from refreshing too
  // late, or over and over.
  if (session.lifetimeMs > 0)
    sessionStorage.setItem(EXPIRES_KEY, String(Date.now() + session.lifetimeMs))
  else sessionStorage.removeItem(EXPIRES_KEY)
  sessionStorage.setItem(TOKEN_KEY, accessToken)
  sessionStorage.setItem(REFRESH_KEY, refreshToken)
  notifyChange()
  scheduleRefresh()
  return true
}

// After signing in. False if the access token is malformed or has an unknown role.
export function startSession(accessToken: string, refreshToken: string) {
  const session = decode(accessToken)
  if (!session || !storeTokens(accessToken, refreshToken)) return false
  sessionStorage.setItem(SESSION_ID_KEY, randomId())
  sessionChannel.postMessage({
    type: 'signed-in-elsewhere',
    userId: session.userId,
  })
  return true
}

// Forgets this tab's session, without telling the server
export function clearSession(): void {
  window.clearTimeout(refreshTimer)
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(SESSION_ID_KEY)
  sessionStorage.removeItem(EXPIRES_KEY)
  notifyChange()
}

// Logout: ends the session on the server as well, so its refresh token stops
// working. The server answers 204 even for an unknown token.
export async function signOut(): Promise<void> {
  const refreshToken = getRefreshToken()
  clearSession()
  if (!refreshToken) return
  try {
    await fetch(LOGOUT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      // Still sent if the page is being closed or navigated away
      keepalive: true,
    })
  } catch {
    // Unreachable: the session simply runs out on its own (7 days at most)
  }
}

type TokenResponse = { access_token: string; refresh_token: string }

let inFlight: Promise<boolean> | null = null

// Swaps the refresh token for new tokens. Only one runs at a time per tab: a
// refresh token works once, so a second request with the same token would look
// like reuse and end the session. Resolves false if the session has ended.
// Rejects if the User Service couldn't be reached, keeping the session.
export function refreshSession(): Promise<boolean> {
  inFlight ??= doRefresh().finally(() => {
    inFlight = null
  })
  return inFlight
}

async function doRefresh(): Promise<boolean> {
  // A duplicate tab must not refresh before it learns it's a duplicate
  await duplicateCheck
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearSession()
    return false
  }

  const response = await fetch(REFRESH_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  // Signed out (or into another account) while the request was in flight
  if (getRefreshToken() !== refreshToken) return getSession() !== null

  if (response.ok) {
    const body = (await response.json()) as TokenResponse
    if (storeTokens(body.access_token, body.refresh_token)) return true
  }
  if (response.ok || response.status === 401 || response.status === 422) {
    // Ended (logout elsewhere, password change, expired, reuse) or unusable
    clearSession()
    return false
  }
  // 5xx, 429 and the like: the session may still be fine, so keep it
  throw new Error(`Refresh failed with ${response.status}`)
}

let refreshTimer: number | undefined

// Refreshes shortly before the access token runs out, so requests rarely have
// to wait for a refresh, and a tab left open stays signed in
function scheduleRefresh() {
  window.clearTimeout(refreshTimer)
  const session = getSession()
  if (!session || !getRefreshToken()) return
  const ahead = Math.min(REFRESH_AHEAD_MS, session.lifetimeMs / 2)
  const delay = Math.max(0, session.expiresAt - Date.now() - ahead)
  refreshTimer = window.setTimeout(() => {
    refreshSession().catch(() => {
      refreshTimer = window.setTimeout(scheduleRefresh, RETRY_MS)
    })
  }, delay)
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

// On page load: ask whether another tab already holds this session (if so,
// this tab is a duplicate and gives it up), then keep the session fresh
const loadedSessionId = sessionStorage.getItem(SESSION_ID_KEY)
if (loadedSessionId)
  sessionChannel.postMessage({
    type: 'session-opened',
    sessionId: loadedSessionId,
    tabId: TAB_ID,
  })
const duplicateCheck: Promise<void> = loadedSessionId
  ? new Promise((resolve) => window.setTimeout(resolve, DUPLICATE_CHECK_MS))
  : Promise.resolve()
scheduleRefresh()
