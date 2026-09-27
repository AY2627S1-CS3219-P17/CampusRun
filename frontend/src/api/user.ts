// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-replaced the mocked calls with calls to the User Service (register, login, get and update profile).
// Author review: Validated request payloads, responses, and error handling.

import { request } from './client'
import type {
  LoginUserPayload,
  RegisterUserPayload,
  UpdateUserPayload,
  User,
} from '../types/user'

// Relative, so it's same-origin behind the gateway; the Vite dev server proxies it (see vite.config.ts)
const USER_API_URL = '/api/users'

type TokenResponse = { access_token: string; token_type: 'bearer' }

export function registerUser(registerUserPayload: RegisterUserPayload) {
  return request<User>(`${USER_API_URL}/auth/register`, {
    method: 'POST',
    body: JSON.stringify(registerUserPayload),
  })
}

export async function loginUser({ email, password }: LoginUserPayload) {
  const response = await request<TokenResponse>(`${USER_API_URL}/auth/login`, {
    method: 'POST',
    body: new URLSearchParams({ username: email, password }),
  })
  return response.access_token
}

export function updateUser(updateUserPayload: UpdateUserPayload) {
  return request<User>(`${USER_API_URL}/users/me`, {
    method: 'PATCH',
    body: JSON.stringify(updateUserPayload),
  })
}

// Abort signal to stop the in-flight request (eg: when the edit-user-info modal is closed)
export function getCurrentUser(signal?: AbortSignal) {
  return request<User>(`${USER_API_URL}/users/me`, { signal })
}
