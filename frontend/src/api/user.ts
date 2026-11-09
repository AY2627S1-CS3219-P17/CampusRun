// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-replaced the mocked calls with calls to the User Service (register, login, get and update profile).
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-changed login to return the refresh token as well; AI-added the admin user list, promotion and
//        stepping down.
// Author review: Validated request payloads, responses, and error handling.

import { request } from './client'
import type {
  AdminUser,
  AdminUserPage,
  AdminUserQuery,
  LoginUserPayload,
  RegisterUserPayload,
  UpdateUserPayload,
  User,
} from '../types/user'

// Relative, so it's same-origin behind the gateway; the Vite dev server proxies it (see vite.config.ts)
const USER_API_URL = '/api/users'

type TokenResponse = {
  access_token: string
  token_type: 'bearer'
  refresh_token: string
}

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
  return {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
  }
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

// Admin only: search accounts by username or email
export function listUsers(query: AdminUserQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({
    page: String(query.page),
    page_size: String(query.pageSize),
  })
  if (query.q.trim()) params.set('q', query.q.trim())
  if (query.role) params.set('role', query.role)
  return request<AdminUserPage>(`${USER_API_URL}/admin/users?${params}`, {
    signal,
  })
}

// Admin only. The user gets admin access at their next token refresh (within 5 minutes).
export function promoteUser(userId: number) {
  return request<AdminUser>(`${USER_API_URL}/admin/users/${userId}/promote`, {
    method: 'POST',
  })
}

// Admin only: give up your own admin role. Refused (409) for the last admin.
export function stepDown() {
  return request<AdminUser>(`${USER_API_URL}/admin/me/step-down`, {
    method: 'POST',
  })
}
