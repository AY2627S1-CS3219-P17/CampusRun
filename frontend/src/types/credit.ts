// AI Assistance Disclosure:
// Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
// Scope: AI-added the wallet type returned by the Credit Service's GET /wallets/me.
// Author review: <to be completed by author>

// PENDING: registered, but the credit service hasn't opened the wallet yet (its OpenWallet message is in flight)
export type WalletStatus = 'ACTIVE' | 'PENDING'

// Field names follow the Credit Service's JSON, which is camelCase. Balances are null while PENDING.
export type Wallet = {
  userId: number
  status: WalletStatus
  available: number | null
  reserved: number | null
  total: number | null
  updatedAt: string | null
}
