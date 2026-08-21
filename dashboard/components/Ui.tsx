import type { ReactNode } from 'react'

import type { Tone } from '@/lib/timeline'

/** 분류 문자열마다 색을 고정한다. 같은 값이 화면 어디에 나와도 같은 색이어야 읽힌다. */
const TONE_BY_TOKEN: Record<string, Tone> = {
  SUCCESS: 'ok',
  PASS: 'ok',
  APPROVED: 'ok',
  BLOCKED: 'fail',
  FAIL: 'fail',
  CHANGES_REQUESTED: 'fail',
  PRODUCT_CODE_DEFECT: 'warn',
  PLAN_DEFECT: 'warn',
  UNKNOWN: 'warn',
  ENVIRONMENT_ERROR: 'fail',
  TEST_DEFECT: 'fail',
  RETRY_BUDGET_EXCEEDED: 'fail',
}

export function toneOf(token: string | null | undefined): Tone {
  if (!token) return 'muted'
  const key = token.replace(/^(STATUS|VERDICT|EVAL):\s*/, '').trim()
  return TONE_BY_TOKEN[key] ?? 'neutral'
}

export function Badge({
  children,
  tone,
}: {
  children: ReactNode
  tone?: Tone
}) {
  const resolved = tone ?? toneOf(typeof children === 'string' ? children : null)
  return <span className={`badge badge--${resolved}`}>{children}</span>
}

export function StatCard({
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  sub?: string
  tone?: Tone
}) {
  return (
    <div className={`stat stat--${tone}`}>
      <div className="stat__label">
        <span className="stat__dot" aria-hidden="true" />
        {label}
      </div>
      <div className="stat__value">{value}</div>
      {sub ? <div className="stat__sub">{sub}</div> : null}
    </div>
  )
}

/**
 * 재시도 예산 게이지.
 *
 * EVAL-003의 `0/3`(예산 미소비)과 EVAL-004의 `3/3`(예산 소진)이 한눈에 구분되어야 해서
 * 숫자만 쓰지 않고 칸을 그린다.
 */
export function RetryGauge({
  count,
  budget,
  compact = false,
}: {
  count: number
  budget: number
  compact?: boolean
}) {
  const exhausted = budget > 0 && count >= budget
  return (
    <span className={`gauge ${compact ? 'gauge--compact' : ''}`}>
      <span className="gauge__cells">
        {Array.from({ length: budget }, (_, index) => (
          <span
            key={index}
            className={`gauge__cell ${index < count ? (exhausted ? 'is-exhausted' : 'is-used') : ''}`}
          />
        ))}
      </span>
      <span className={`gauge__text ${exhausted ? 'is-exhausted' : ''}`}>
        {count}/{budget}
      </span>
    </span>
  )
}

export function Section({
  title,
  aside,
  children,
}: {
  title: string
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="section">
      <header className="section__head">
        <h2 className="section__title">{title}</h2>
        {aside ? <div className="section__aside">{aside}</div> : null}
      </header>
      {children}
    </section>
  )
}
