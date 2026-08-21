/**
 * Dashboard가 쓰는 공개 데이터 API.
 *
 * `reports/examples/` 의 디렉터리 하나가 Eval 하나다. 빌드 타임에 한 번만 읽고 캐시한다.
 */
import {
  discoverArtifacts,
  listExampleDirs,
  parseEvalResult,
  parseFaultInjection,
  parsePlan,
  parseState,
  parseTestResult,
  readExampleFile,
} from './parse'
import type {
  EvalDetail,
  EvalSummary,
  FaultInjection,
  PlanSnapshot,
  TestResult,
} from './types'

/** `EVAL-20260820-1443-HARNESS-EVAL-002` */
const EXAMPLE_DIR = /^EVAL-(\d{8})-(\d{4})-(.+)$/

interface Identity {
  id: string
  shortId: string
}

function identityOf(dir: string): Identity | null {
  const match = EXAMPLE_DIR.exec(dir)
  if (!match) return null
  const scenarioToken = match[3]
  const numbered = /-(\d+)$/.exec(scenarioToken)
  return {
    id: scenarioToken.toLowerCase(),
    shortId: numbered ? `EVAL-${numbered[1]}` : scenarioToken,
  }
}

function loadDetail(dir: string, identity: Identity): EvalDetail {
  const where = `reports/examples/${dir}`

  const stateRaw = readExampleFile(dir, 'state.json')
  if (stateRaw === null) {
    throw new Error(`${where}: state.json 이 없습니다. Dashboard의 필수 데이터입니다.`)
  }
  const state = parseState(stateRaw, where)

  const evalResultRaw = readExampleFile(dir, 'eval-result.md')
  const evalResult = evalResultRaw === null ? null : parseEvalResult(evalResultRaw)

  const artifacts = discoverArtifacts(dir)

  const plans: PlanSnapshot[] = []
  const faults: FaultInjection[] = []
  const testResults: TestResult[] = []

  for (const artifact of artifacts) {
    const text = readExampleFile(dir, artifact.file)
    if (text === null) continue
    if (artifact.kind === 'plan') plans.push(parsePlan(artifact.file, text))
    if (artifact.kind === 'plan-final' && !artifact.isFinalPlanAlias) {
      // 스냅샷이 하나도 없는 실행에서는 plan.md 자체가 Planner 1차 산출물이다.
      plans.push(parsePlan(artifact.file, text))
    }
    if (artifact.kind === 'fault-injection') faults.push(parseFaultInjection(artifact.file, text))
    if (artifact.kind === 'test-result') testResults.push(parseTestResult(artifact.file, text))
  }

  plans.sort((a, b) => (a.attempt ?? 1) - (b.attempt ?? 1))
  faults.sort((a, b) => a.attempt - b.attempt)
  testResults.sort((a, b) => a.attempt - b.attempt)

  const headlineCategory =
    state.finalStatus === 'BLOCKED'
      ? state.blockedReason
      : (state.attempts.find((attempt) => attempt.failureCategory)?.failureCategory ?? null)

  return {
    ...identity,
    dir,
    scenario: evalResult?.scenarioId ?? identity.id,
    state,
    evalResult,
    headlineCategory,
    artifacts,
    plans,
    faults,
    testResults,
    reviewVerdict: state.review.verdict,
  }
}

let cache: EvalDetail[] | null = null

export function getEvals(): EvalDetail[] {
  if (cache) return cache
  const loaded: EvalDetail[] = []
  for (const dir of listExampleDirs()) {
    const identity = identityOf(dir)
    if (!identity) continue
    loaded.push(loadDetail(dir, identity))
  }
  if (loaded.length === 0) {
    throw new Error('reports/examples/ 에서 읽을 수 있는 대표 결과를 찾지 못했습니다.')
  }
  cache = loaded.sort((a, b) => a.shortId.localeCompare(b.shortId))
  return cache
}

export function getEval(id: string): EvalDetail {
  const found = getEvals().find((item) => item.id === id)
  if (!found) throw new Error(`알 수 없는 Eval id 입니다: ${id}`)
  return found
}

export interface DashboardSummary {
  totalEvals: number
  success: number
  blocked: number
  totalAttempts: number
  totalRetry: number
  totalRetryBudget: number
  checksPassed: number
  checksTotal: number
}

export function getSummary(evals: EvalSummary[] = getEvals()): DashboardSummary {
  return {
    totalEvals: evals.length,
    success: evals.filter((item) => item.state.finalStatus === 'SUCCESS').length,
    blocked: evals.filter((item) => item.state.finalStatus === 'BLOCKED').length,
    totalAttempts: evals.reduce((sum, item) => sum + item.state.attempts.length, 0),
    totalRetry: evals.reduce((sum, item) => sum + item.state.retryCount, 0),
    totalRetryBudget: evals.reduce((sum, item) => sum + item.state.retryBudget, 0),
    checksPassed: evals.reduce((sum, item) => sum + (item.evalResult?.passed ?? 0), 0),
    checksTotal: evals.reduce((sum, item) => sum + (item.evalResult?.total ?? 0), 0),
  }
}
