export type RegisterUserValues = {
  username: string
  email: string
  password: string
  confirmPassword: string
}

export type RegisterUserPayload = Omit<RegisterUserValues, 'confirmPassword'>
export type LoginUserPayload = Omit<RegisterUserPayload, 'username'>
export type UpdateUserPayload = Omit<
  RegisterUserValues,
  'confirmPassword' | 'email'
>
