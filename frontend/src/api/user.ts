import type {
  RegisterUserPayload,
  LoginUserPayload,
  UpdateUserPayload,
} from '../types/user'

// All APIs requests to User Service are mocked for now
export async function registerUser(registerUserPayload: RegisterUserPayload) {
  console.log(registerUserPayload)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}

export async function loginUser(loginUserPayload: LoginUserPayload) {
  console.log(loginUserPayload)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}

export async function updateUser(updateUserPayload: UpdateUserPayload) {
  console.log(updateUserPayload)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}
