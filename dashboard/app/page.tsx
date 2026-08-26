import Link from 'next/link'

import { Badge, RetryGauge, Section, StatCard, toneOf } from '@/components/Ui'
import { AUDIT_SOURCE, categoryLabel, getAudit } from '@/lib/audit'
import { getEvals, getSummary } from '@/lib/evals'
import type { AuditCategory, AuditCheck, HarnessAudit } from '@/lib/types'
import type { Tone } from '@/lib/timeline'

/**
 * Category 하나의 색.
 *
 * Critical 실패와 단순 감점을 같은 색으로 칠하면 "거짓말이면 Critical, 미완성이면 감점"
 * 이라는 rubric 의 기준선이 화면에서 사라진다. 세 단계를 분리한다.
 */
function categoryTone(category: AuditCategory): Tone {
  const failing = category.checks.filter((check) => check.result === 'FAIL')
  if (failing.some((check) => check.critical)) return 'fail'
  return failing.length > 0 ? 'warn' : 'ok'
}

function failingChecks(audit: HarnessAudit): AuditCheck[] {
  return audit.categories.flatMap((category) =>
    category.checks.filter((check) => check.result === 'FAIL'),
  )
}

/**
 * 구조 검증 패널.
 *
 * 표시하는 모든 수치는 `reports/audit/latest.json` 에 그대로 있는 값이다. Dashboard 는
 * 점수를 재계산하지 않고, FAIL 한 check 를 숨기지도 않는다. 자기 저장소를 만점으로
 * 보이게 만드는 감사 도구는 감사 도구가 아니다.
 */
function AuditPanel({ audit }: { audit: HarnessAudit }) {
  const failing = failingChecks(audit)
  const nonCritical = failing.filter((check) => !check.critical)
  const criticalCount = audit.criticalFailures.length

  return (
    <div className="audit">
      <div className="audit__head">
        <div className={`audit__verdict audit__verdict--${audit.verdict === 'PASS' ? 'ok' : 'fail'}`}>
          <span className="audit__verdict-token">{audit.verdict}</span>
          <span className="audit__verdict-sub">
            {criticalCount === 0
              ? 'Critical Hard Gate 위반 없음'
              : `Critical Hard Gate ${criticalCount}건 위반`}
          </span>
        </div>

        <div className="audit__score">
          <span className="audit__score-value">{audit.score}</span>
          <span className="audit__score-max">/ {audit.maxScore}</span>
        </div>

        <dl className="audit__meta">
          <div className="audit__meta-item">
            <dt>Critical</dt>
            <dd className={criticalCount > 0 ? 'is-fail' : ''}>{criticalCount}</dd>
          </div>
          <div className="audit__meta-item">
            <dt>Rubric</dt>
            <dd>{audit.rubricVersion}</dd>
          </div>
          <div className="audit__meta-item">
            <dt>Audit</dt>
            <dd>{audit.auditVersion}</dd>
          </div>
        </dl>
      </div>

      <ul className="audit-cats">
        {audit.categories.map((category) => {
          const tone = categoryTone(category)
          const ratio = category.maxScore > 0 ? category.score / category.maxScore : 0
          return (
            <li key={category.id} className={`audit-cat audit-cat--${tone}`}>
              <span className="audit-cat__name">{categoryLabel(category.title)}</span>
              <span className="audit-cat__bar" aria-hidden="true">
                <span className="audit-cat__fill" style={{ width: `${ratio * 100}%` }} />
              </span>
              <span className="audit-cat__score">
                {category.score} / {category.maxScore}
              </span>
            </li>
          )
        })}
      </ul>

      {criticalCount > 0 ? (
        <div className="audit-block audit-block--fail">
          <h3 className="audit-block__title">Critical Hard Gate 위반</h3>
          <ul className="audit-miss">
            {audit.criticalFailures.map((failure) => (
              <li key={failure.checkId} className="audit-miss__row">
                <code className="audit-miss__id">{failure.checkId}</code>
                <span className="audit-miss__text">{failure.summary}</span>
                <Badge tone="fail">{failure.gate}</Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {nonCritical.length > 0 ? (
        <div className="audit-block audit-block--warn">
          <h3 className="audit-block__title">미달 check (감점 · 게이트 아님)</h3>
          <ul className="audit-miss">
            {nonCritical.map((check) => (
              <li key={check.id} className="audit-miss__row">
                <code className="audit-miss__id">{check.id}</code>
                <span className="audit-miss__text">{check.title}</span>
                <span className="audit-miss__weight">-{check.maxScore}점</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {audit.nextActions.length > 0 ? (
        <div className="audit-block">
          <h3 className="audit-block__title">Next Actions</h3>
          <ol className="audit-actions">
            {audit.nextActions.map((action) => (
              <li key={action.checkId} className="audit-actions__row">
                <span className="audit-actions__head">
                  <code className="audit-miss__id">{action.checkId}</code>
                  <span className="audit-actions__weight">{action.maxScore}점</span>
                  {action.critical ? <Badge tone="fail">Critical</Badge> : null}
                </span>
                <span className="audit-actions__text">{action.action}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {audit.warnings.length > 0 ? (
        <div className="audit-block">
          <h3 className="audit-block__title">경고 (점수 미반영)</h3>
          <ul className="audit-warn">
            {audit.warnings.map((warning) => (
              <li key={warning.id}>
                <code className="audit-miss__id">{warning.id}</code>{' '}
                <span className="audit-miss__text">{warning.summary}</span>
                {warning.detail.length > 0 ? (
                  <span className="audit-warn__detail mono">{warning.detail.join(' · ')}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export default function OverviewPage() {
  const evals = getEvals()
  const summary = getSummary(evals)
  const audit = getAudit()

  return (
    <>
      <div className="page-head">
        <h1 className="page-head__title">Harness 검증 결과</h1>
        <p className="page-head__meta">
          서로 다른 두 층의 검증입니다. <strong>구조 검증</strong>은 저장소가 선언한 통제 계약이
          실제로 갖춰져 있는지 정적으로 채점하고, <strong>실행 검증</strong>은 결함을 주입해 실제로
          일어난 상태 전이를 보존된 산출물로 판정합니다.
        </p>
      </div>

      <Section
        title="구조 검증 · Harness Audit"
        aside={audit ? <code>{AUDIT_SOURCE}</code> : undefined}
      >
        <p className="note note--lead">
          저장소가 선언한 Harness 통제 계약이 실제로 갖춰져 있고 서로 모순되지 않는지{' '}
          <strong>정적으로</strong> 검사한 결과입니다. Agent를 실행하지 않고 저장소 파일만 읽어
          채점하므로, Harness가 실제로 동작한다는 증명이 아니라 계약이 정합적이라는 증거입니다.
        </p>
        {audit ? (
          <>
            <AuditPanel audit={audit} />
            <p className="note">
              33개 check 이진 판정 · rubric <code>{audit.rubricVersion}</code> ·{' '}
              <code className="audit-digest">{audit.rubricDigest}</code> · 점수는 같은 rubric
              버전 안에서만 비교할 수 있습니다. 아래 실행 검증의 항목 수와는 검사 대상이 달라
              합산하지 않습니다.
            </p>
          </>
        ) : (
          <div className="card card--pad audit-empty">
            <p className="audit-empty__title">대표 Audit 결과가 아직 생성되지 않았습니다.</p>
            <p className="audit-empty__hint">
              <code>uv run python evals/harness_audit.py --write</code> 를 실행하면{' '}
              <code>{AUDIT_SOURCE}</code> 가 생성됩니다. 구조 검증은 선택 데이터이므로 없어도
              아래 실행 검증은 그대로 표시됩니다.
            </p>
          </div>
        )}
      </Section>

      <Section title="실행 검증 · Harness Eval">
        <p className="note note--lead">
          결함을 주입해 <strong>실제로 실행된</strong> Harness 상태 전이를, 보존된 실행 산출물만
          근거로 판정한 결과입니다.
        </p>
        <div className="stats">
          <StatCard label="Total Evals" value={summary.totalEvals} sub="검증한 상태 전이 시나리오" />
          <StatCard label="Success" value={summary.success} tone="ok" sub="PASS + APPROVED 종료" />
          <StatCard label="Blocked" value={summary.blocked} tone="fail" sub="Orchestrator 중단 종료" />
          <StatCard label="Attempts" value={summary.totalAttempts} sub="Developer → Tester 시도" />
          <StatCard
            label="Retry Budget"
            value={`${summary.totalRetry}/${summary.totalRetryBudget}`}
            sub="소비한 재시도 예산"
            tone="warn"
          />
        </div>
        <p className="note">
          자동 검증 {summary.checksPassed}/{summary.checksTotal} 항목 통과 ·{' '}
          모든 수치는 <code>reports/examples/</code> 의 <code>state.json</code> 과{' '}
          <code>eval-result.md</code> 에서 읽었습니다.
        </p>
      </Section>

      <Section title="Eval 목록">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Eval ID</th>
                <th>Scenario</th>
                <th>Final Status</th>
                <th>Failure Category / Blocked Reason</th>
                <th>retry / budget</th>
                <th>Attempts</th>
                <th>자동 검증</th>
              </tr>
            </thead>
            <tbody>
              {evals.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link className="row-link" href={`/evals/${item.id}/`}>
                      {item.shortId}
                    </Link>
                  </td>
                  <td className="mono">{item.scenario}</td>
                  <td>
                    <Badge tone={toneOf(item.state.finalStatus)}>{item.state.finalStatus}</Badge>
                  </td>
                  <td>
                    {item.headlineCategory ? (
                      <Badge tone={toneOf(item.headlineCategory)}>{item.headlineCategory}</Badge>
                    ) : (
                      <span className="mono">—</span>
                    )}
                  </td>
                  <td>
                    <RetryGauge count={item.state.retryCount} budget={item.state.retryBudget} />
                  </td>
                  <td className="mono">{item.state.attempts.length}</td>
                  <td>
                    {item.evalResult ? (
                      <Badge tone={item.evalResult.verdict === 'PASS' ? 'ok' : 'fail'}>
                        {item.evalResult.passed}/{item.evalResult.total}
                      </Badge>
                    ) : (
                      <span className="mono">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          EVAL-003의 <code>0/3</code> 은 예산을 쓰지 않고 즉시 종료한 경우이고, EVAL-004의{' '}
          <code>3/3</code> 은 예산을 모두 소진한 경우입니다. 같은 <code>BLOCKED</code> 라도 종료
          경로가 다릅니다.
        </p>
      </Section>
    </>
  )
}
