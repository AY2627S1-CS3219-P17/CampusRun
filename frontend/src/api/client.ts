// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-generated request helper that sends the access token and turns error responses into ApiError.
// Author review: <to be completed by author>

import { clearSession, getSession } from '../utils/session'

const UNREACHABLE =
  "Can't reach the service. Check that it's running, then try again."

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

type ErrorBody = { detail?: string; errors?: Record<string, string> }

export async function request<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const session = getSession()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (init.body) headers['Content-Type'] = 'application/json'
  if (session) headers.Authorization = `Bearer ${session.token}`

  let response: Response
  try {
    response = await fetch(url, { ...init, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw error
    throw new ApiError(0, UNREACHABLE)
  }

  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    const error = (body ?? {}) as ErrorBody
    // Expired or invalid token: forget it so the page asks to sign in again
    if (response.status === 401) clearSession()
    if (response.status >= 502 && !error.detail)
      throw new ApiError(response.status, UNREACHABLE)
    throw new ApiError(
      response.status,
      error.detail ?? 'Something went wrong. Try again in a moment.',
      error.errors ?? {},
    )
  }
  return body as T
}
