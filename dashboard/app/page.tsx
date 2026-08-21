import Link from 'next/link'

import { Badge, RetryGauge, Section, StatCard, toneOf } from '@/components/Ui'
import { getEvals, getSummary } from '@/lib/evals'

export default function OverviewPage() {
  const evals = getEvals()
  const summary = getSummary(evals)

  return (
    <>
      <div className="page-head">
        <h1 className="page-head__title">Harness Eval 결과</h1>
        <p className="page-head__meta">
          Fault Injection으로 실제 pytest 실패를 만들어 Harness의 상태 전이 4종을 검증한 결과입니다.
        </p>
      </div>

      <Section title="Summary">
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
