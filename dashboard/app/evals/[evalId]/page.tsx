import Link from 'next/link'

import { Timeline } from '@/components/Timeline'
import { Badge, RetryGauge, Section, toneOf } from '@/components/Ui'
import { getEval, getEvals } from '@/lib/evals'
import { buildTimeline } from '@/lib/timeline'
import { BUDGET_CONSUMING_CATEGORIES } from '@/lib/types'

export function generateStaticParams() {
  return getEvals().map((item) => ({ evalId: item.id }))
}

export default async function EvalDetailPage({
  params,
}: {
  params: Promise<{ evalId: string }>
}) {
  const { evalId } = await params
  const detail = getEval(evalId)
  const timeline = buildTimeline(detail)
  const { state, evalResult } = detail

  // Attempt 표의 retry 변화 열도 Timeline과 같은 §16 규칙으로 계산한다.
  let running = 0

  return (
    <>
      <p className="breadcrumb">
        <Link href="/">Overview</Link> / {detail.shortId}
      </p>

      <div className="page-head">
        <h1 className="page-head__title">
          {detail.shortId} · {detail.scenario}{' '}
          <Badge tone={toneOf(state.finalStatus)}>{state.finalStatus}</Badge>
        </h1>
        <p className="page-head__meta">
          {state.runId}
          <br />
          task: {state.task} · started: {state.startedAt} · finished: {state.finishedAt}
          <br />
          start commit: {state.startCommit.slice(0, 12)}
        </p>
      </div>

      {evalResult?.transition ? (
        <Section title="검증 대상 전이" aside="eval-result.md 기록">
          <div className="card card--pad">
            <pre className="transition">{evalResult.transition}</pre>
          </div>
        </Section>
      ) : null}

      <Section title="Agent 실행 여부">
        <div className="lanes">
          {timeline.agentLanes.map((lane) => (
            <div key={lane.agent} className={`lane ${lane.calls === 0 ? 'lane--skipped' : ''}`}>
              <span className="lane__dot" />
              <span className="lane__name">{lane.agent}</span>
              <span className="lane__meta">{lane.calls > 0 ? `${lane.calls}회` : lane.skippedNote}</span>
            </div>
          ))}
        </div>
        <p className="note">
          호출되지 않은 주체는 Harness가 멈춘 것이 아니라 규칙에 따라 부르지 않은 것이며,{' '}
          <code>eval-result.md</code> 가 그 부재를 자동 검증 항목으로 판정했습니다.
        </p>
      </Section>

      <Section
        title="Timeline"
        aside={
          <span>
            retry_count {state.retryCount} / retry_budget {state.retryBudget}
            {timeline.retryMatchesState ? ' · state.json 과 일치' : ' · state.json 과 불일치'}
          </span>
        }
      >
        <Timeline timeline={timeline} evalId={detail.id} />
      </Section>

      <Section title="Attempts">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>change-log</th>
                <th>test-result</th>
                <th>STATUS</th>
                <th>failure_category</th>
                <th>pytest</th>
                <th>retry_count</th>
              </tr>
            </thead>
            <tbody>
              {state.attempts.map((attempt) => {
                const testResult = detail.testResults.find((item) => item.attempt === attempt.n)
                const consumed =
                  attempt.status === 'FAIL' &&
                  attempt.failureCategory !== null &&
                  BUDGET_CONSUMING_CATEGORIES.has(attempt.failureCategory)
                const before = running
                if (consumed) running += 1
                return (
                  <tr key={attempt.n}>
                    <td className="mono">{attempt.n}</td>
                    <td>
                      <Link
                        className="row-link"
                        href={`/evals/${detail.id}/artifacts/${attempt.changeLog.replace('.md', '')}/`}
                      >
                        {attempt.changeLog}
                      </Link>
                    </td>
                    <td>
                      <Link
                        className="row-link"
                        href={`/evals/${detail.id}/artifacts/${attempt.testResult.replace('.md', '')}/`}
                      >
                        {attempt.testResult}
                      </Link>
                    </td>
                    <td>
                      <Badge tone={toneOf(attempt.status)}>{attempt.status}</Badge>
                    </td>
                    <td>
                      {attempt.failureCategory ? (
                        <Badge tone={toneOf(attempt.failureCategory)}>
                          {attempt.failureCategory}
                        </Badge>
                      ) : (
                        <span className="mono">—</span>
                      )}
                    </td>
                    <td className="mono">{testResult?.pytestSummary ?? '집계 줄 없음'}</td>
                    <td className="mono">
                      {before} → {running}
                      {consumed ? '' : ' (미소비)'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Section>

      {evalResult ? (
        <Section title="자동 검증">
          <details className="checks">
            <summary>
              {evalResult.passed}/{evalResult.total} 항목 통과 — 펼쳐서 개별 항목 보기
            </summary>
            <ul className="checks__list">
              {evalResult.checks.map((check) => (
                <li key={check.no} className="checks__item">
                  <span className="checks__no">{check.no}</span>
                  <Badge tone={check.result === 'PASS' ? 'ok' : 'fail'}>{check.result}</Badge>
                  <span>
                    {check.name}
                    <p className="checks__evidence">{check.evidence}</p>
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </Section>
      ) : null}

      <Section title="Artifacts">
        <div className="lanes">
          {detail.artifacts
            .filter((artifact) => !artifact.isFinalPlanAlias)
            .map((artifact) => (
              <Link
                key={artifact.slug}
                className="lane"
                href={`/evals/${detail.id}/artifacts/${artifact.slug}/`}
                style={{ textDecoration: 'none' }}
              >
                <span className="lane__dot" />
                <span className="lane__name mono">{artifact.file}</span>
              </Link>
            ))}
        </div>
      </Section>

      <Section title="재시도 예산">
        <div className="card card--pad">
          <RetryGauge count={state.retryCount} budget={state.retryBudget} />
          <p className="note">
            {state.blockedReason === 'RETRY_BUDGET_EXCEEDED'
              ? 'retry_count 가 retry_budget 에 도달해 추가 Agent 재호출 없이 종료했습니다. (CLAUDE.md §16)'
              : state.blockedReason === 'ENVIRONMENT_ERROR'
                ? '실행 환경 오류이므로 재시도 예산을 소비하지 않고 즉시 종료했습니다. (CLAUDE.md §20)'
                : `재시도 ${state.retryCount}회를 소비하고 성공했습니다.`}
          </p>
        </div>
      </Section>
    </>
  )
}
