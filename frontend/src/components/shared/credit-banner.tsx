// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Extracted the reusable active and reserved credit banner component.
// Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
// Scope: Replaced the placeholder amounts with the Credit Service wallet, polled while a change is pending,
//        and added the pending state.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added reloading the wallet straight away when an errand changes.
// Tool: OpenAI Codex (GPT-6), date: 2026-10-20
// Scope: Kept the last wallet balance for the signed-in user across main-page navigation.
// Author review: <to be completed by author>

import { useEffect, useState } from 'react'
import { CircleDollarSign } from 'lucide-react'
import { getWallet } from '../../api/credit'
import { onErrandsChanged } from '../../utils/errand-events'
import { useSession } from '../../utils/session'
import { ApiError } from '../../api/client'
import type { Wallet } from '../../types/credit'
import sharedBanner from '../../assets/shared_banner.png'
import './credit-banner.css'

// Check often while something is on its way, otherwise just keep the numbers fresh
const PENDING_POLL_MS = 2000
const IDLE_POLL_MS = 15000
type WalletSnapshot = { userId: string; wallet: Wallet }
let cachedWallet: WalletSnapshot | null = null

type CreditBannerProps = {
  // Set while a page knows a credit change is in flight that the wallet doesn't show yet,
  // e.g. an errand the Order Service has marked COMPLETED but whose transfer hasn't been applied
  pending?: boolean
}

export default function CreditBanner({ pending = false }: CreditBannerProps) {
  const userId = useSession()?.userId
  const [walletSnapshot, setWalletSnapshot] = useState(cachedWallet)
  const wallet = walletSnapshot && walletSnapshot.userId === userId ? walletSnapshot.wallet : null
  const [error, setError] = useState('')
  const waiting = pending || wallet?.status === 'PENDING'

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const load = () => {
      getWallet(controller.signal)
        .then((next) => {
          if (userId) {
            cachedWallet = { userId, wallet: next }
            setWalletSnapshot(cachedWallet)
          }
          setError('')
        })
        .catch((reason: unknown) => {
          if (controller.signal.aborted) return
          setError(
            reason instanceof ApiError
              ? reason.message
              : 'Credits are unavailable right now.',
          )
        })
        .finally(() => {
          if (controller.signal.aborted) return
          // An errand change can start a second load while one is in flight; keep a single timer
          window.clearTimeout(timer)
          timer = window.setTimeout(
            load,
            waiting ? PENDING_POLL_MS : IDLE_POLL_MS,
          )
        })
    }
    load()
    // e.g. a new errand's reward is about to be reserved
    const stopListening = onErrandsChanged(() => {
      window.clearTimeout(timer)
      load()
    })

    return () => {
      stopListening()
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [waiting, userId])

  const active = wallet?.status === 'ACTIVE'
  const label = !wallet
    ? 'Your credits are loading'
    : active
      ? `Your credits: ${wallet.available} active, ${wallet.reserved} reserved${pending ? ', an update is pending' : ''}`
      : 'Your starter credits are on their way'

  return (
    <section
      className="credit-banner"
      style={{ backgroundImage: `url(${sharedBanner})` }}
      aria-label={label}
      aria-busy={waiting || !wallet}
    >
      <div className="credit-banner-summary">
        <p>
          Total Credits
          {waiting && (
            <span className="credit-banner-pending" role="status">
              <span className="credit-banner-pending-dot" aria-hidden="true" />
              Pending
            </span>
          )}
        </p>
        {wallet && !active ? (
          <p className="credit-banner-note">
            Your starter credits are on their way. This updates by itself.
          </p>
        ) : (
          <div className="credit-banner-balance">
            <span className="credit-banner-active">
              <CircleDollarSign size={30} strokeWidth={2} aria-hidden="true" />
              <span className="credit-banner-value">
                {active ? wallet.available : '–'}
              </span>
              <small>Active</small>
            </span>
            <span className="credit-banner-reserved">
              <CircleDollarSign size={30} strokeWidth={2} aria-hidden="true" />
              <span className="credit-banner-value">
                {active ? wallet.reserved : '–'}
              </span>
              <small>Reserved</small>
            </span>
          </div>
        )}
        {error && <p className="credit-banner-error">{error}</p>}
      </div>
    </section>
  )
}
