// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-generated request helper that sends the access token and turns error responses into ApiError;
//        AI-added form bodies and FastAPI's default 422 format (Claude Code, 2026-09-27).
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-added refreshing the access token before a request when it's about to run out, and once after a 401,
//        retrying the request with the new token.
// Author review: Validated authentication, request bodies, and error boundaries.

import { clearSession, getSession, refreshSession } from '../utils/session'

const UNREACHABLE =
  "Can't reach the service. Check that it's running, then try again."
const SESSION_ENDED = 'Your session has ended. Sign in again.'
// Refresh before sending if the access token has less than this left (or a
// quarter of its lifetime, if that's less), so it doesn't run out on the way.
// The Order Service passes the token on to other services, up to two calls of
// 5 seconds each in a row, and reports their 401s as "unavailable".
const EXPIRY_MARGIN_MS = 30_000

export class ApiError extends Error {
  status: number
  // Field name -> message, from 422 responses
  fieldErrors: Record<string, string>

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

// FastAPI's default 422 body lists each problem instead of giving one message (the User Service uses it)
type ValidationIssue = { loc?: (string | number)[]; msg?: string }
type ErrorBody = {
  detail?: string | ValidationIssue[]
  errors?: Record<string, string>
}

function readIssues(issues: ValidationIssue[]) {
  const fieldErrors: Record<string, string> = {}

  for (const { loc, msg } of issues) {
    if (!msg) continue
    // Pydantic prefixes messages from custom validators with "Value error, "
    const message = msg.replace(/^Value error, /, '')
    fieldErrors[String(loc?.at(-1) ?? '')] ??= message
  }

  const first = Object.values(fieldErrors)[0]
  return { message: first ? `${first}.` : undefined, fieldErrors }
}

// Refreshes the session; false if it has ended. If the User Service can't be
// reached, carries on with the current token and lets the request decide.
async function tryRefresh(): Promise<boolean | null> {
  try {
    return await refreshSession()
  } catch {
    return null
  }
}

async function send(url: string, init: RequestInit): Promise<Response> {
  const session = getSession()
  const headers: Record<string, string> = { Accept: 'application/json' }

  // Other bodies (e.g. URLSearchParams for the login form) let fetch set their own type
  if (typeof init.body === 'string')
    headers['Content-Type'] = 'application/json'
  if (session) headers.Authorization = `Bearer ${session.token}`

  try {
    return await fetch(url, { ...init, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw error
    throw new ApiError(0, UNREACHABLE)
  }
}

// Main request wrapper
export async function request<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const session = getSession()
  const margin = Math.min(EXPIRY_MARGIN_MS, (session?.lifetimeMs ?? 0) / 4)
  if (session && session.expiresAt - Date.now() < margin) {
    if ((await tryRefresh()) === false)
      throw new ApiError(401, SESSION_ENDED)
  }

  let response = await send(url, init)

  // The access token was refused (e.g. it ran out while the tab was asleep):
  // refresh once and try again. A request sent without a token, like signing
  // in, gets its 401 as it is.
  if (response.status === 401 && session) {
    const refreshed = await tryRefresh()
    if (refreshed === false) throw new ApiError(401, SESSION_ENDED)
    if (refreshed) {
      response = await send(url, init)
      // Refused even with fresh tokens (e.g. the account was deleted): give up
      // on the session so the page asks to sign in again
      if (response.status === 401) clearSession()
    }
  }

  // No content
  if (response.status === 204) return undefined as T

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (body ?? {}) as ErrorBody

    // Server side issue
    if (response.status >= 502 && !error.detail)
      throw new ApiError(response.status, UNREACHABLE)

    const { message, fieldErrors } = Array.isArray(error.detail)
      ? readIssues(error.detail)
      : { message: error.detail, fieldErrors: error.errors ?? {} }

    throw new ApiError(
      response.status,
      message ?? 'Something went wrong. Try again in a moment.',
      fieldErrors,
    )
  }
  return body as T
}
