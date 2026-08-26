/**
 * Harness 산출물의 도메인 타입.
 *
 * 값의 정의는 이 Dashboard가 새로 만드는 것이 아니라 `CLAUDE.md` §14 / §16 / §19 / §20 이
 * 규정한 계약을 그대로 옮긴 것이다. Dashboard는 계약의 소비자이며 계약을 바꾸지 않는다.
 */

/** `CLAUDE.md` §14 의 실패 원인 분류 5종. */
export const FAILURE_CATEGORIES = [
  'PRODUCT_CODE_DEFECT',
  'TEST_DEFECT',
  'PLAN_DEFECT',
  'ENVIRONMENT_ERROR',
  'UNKNOWN',
] as const

export type FailureCategory = (typeof FAILURE_CATEGORIES)[number]

/**
 * 재시도 예산을 소비하는 실패 원인. (`CLAUDE.md` §16)
 *
 * `ENVIRONMENT_ERROR` 와 `TEST_DEFECT` 는 예산을 쓰지 않고 즉시 종료하므로 여기에 없다.
 * Timeline의 retry_count 누적이 이 집합 하나에만 의존하도록 모아 둔다.
 */
export const BUDGET_CONSUMING_CATEGORIES: ReadonlySet<FailureCategory> = new Set([
  'PRODUCT_CODE_DEFECT',
  'PLAN_DEFECT',
  'UNKNOWN',
])

export type FinalStatus = 'SUCCESS' | 'BLOCKED'
export type TestStatus = 'PASS' | 'FAIL'
export type Verdict = 'APPROVED' | 'CHANGES_REQUESTED'

export interface Attempt {
  n: number
  changeLog: string
  testResult: string
  status: TestStatus
  failureCategory: FailureCategory | null
}

export interface EvalState {
  runId: string
  task: string
  currentStage: string
  retryCount: number
  retryBudget: number
  unknownRetryUsed: boolean
  /** 포맷이 실행마다 다르므로(3종 확인) Date로 변환하지 않고 원문 그대로 보관한다. */
  startedAt: string
  finishedAt: string
  startCommit: string
  attempts: Attempt[]
  review: { verdict: Verdict | null; file: string | null }
  finalStatus: FinalStatus
  blockedReason: string | null
}

export interface TestResult {
  attempt: number
  status: TestStatus
  command: string | null
  failureCategory: FailureCategory | null
  /** `8 failed, 62 passed in 0.15s` 형태의 집계 줄. 수집 단계에서 중단되면 없다. */
  pytestSummary: string | null
}

export interface FaultInjection {
  file: string
  attempt: number
  faultId: string
  targetFile: string
  injectedAt: string | null
  description: string | null
}

export interface PlanSnapshot {
  file: string
  /** `plan.md` 는 마지막 `plan-N.md` 와 동일하므로 스냅샷 번호가 없다. */
  attempt: number | null
  allowedFiles: string[]
}

export interface EvalCheck {
  no: number
  name: string
  result: 'PASS' | 'FAIL'
  evidence: string
}

export interface EvalResult {
  verdict: 'PASS' | 'FAIL'
  scenarioId: string | null
  judgedAt: string | null
  /** `## 검증 대상 전이` 본문. 여러 줄이다. */
  transition: string | null
  checks: EvalCheck[]
  passed: number
  total: number
}

export type ArtifactKind =
  | 'plan'
  | 'plan-final'
  | 'fault-injection'
  | 'change-log'
  | 'test-result'
  | 'review'
  | 'report'
  | 'state'
  | 'eval-result'

export interface Artifact {
  /** `test-result-2.md` */
  file: string
  /** URL 세그먼트. 확장자를 뗀 파일명. */
  slug: string
  kind: ArtifactKind
  attempt: number | null
  /** `plan.md` 가 마지막 `plan-N.md` 와 내용이 같은가. 같으면 목록에서 별칭으로만 표시한다. */
  isFinalPlanAlias: boolean
}

export interface EvalSummary {
  /** `harness-eval-002` */
  id: string
  /** `EVAL-002` */
  shortId: string
  /** `reports/examples/EVAL-20260820-1443-HARNESS-EVAL-002` */
  dir: string
  scenario: string
  state: EvalState
  evalResult: EvalResult | null
  /** 목록에 보여줄 대표 분류. BLOCKED면 blocked_reason, 아니면 1차 실패 분류. */
  headlineCategory: string | null
}

export interface EvalDetail extends EvalSummary {
  artifacts: Artifact[]
  plans: PlanSnapshot[]
  faults: FaultInjection[]
  testResults: TestResult[]
  reviewVerdict: Verdict | null
}

// ---------------------------------------------------------------------------
// Harness Audit — `evals/harness_audit.py` 의 JSON 봉투 (schema_version 1)
//
// Eval 타입과 한 파일에 있지만 **계약이 다르다.** Eval 은 실행된 상태 전이의 기록이고
// Audit 은 정지 상태 구조 계약의 채점이다. 두 수치를 합산하거나 같은 지표로 부르지
// 않는다. snake_case 원본을 camelCase 로 옮기기만 하며 값은 바꾸지 않는다.
// ---------------------------------------------------------------------------

/** rubric 의 check 하나. 이진 판정이므로 부분 점수가 없다. */
export interface AuditCheck {
  /** `B3`, `E4b` */
  id: string
  title: string
  result: 'PASS' | 'FAIL'
  score: number
  maxScore: number
  /** Critical Hard Gate 대상인가. 감점과 게이트는 다른 층위다. */
  critical: boolean
  /** 근거가 되는 문서 조항. `CLAUDE.md §22` */
  contract: string
  evidence: string[]
  remediation: string
}

export interface AuditCategory {
  /** `guard-enforcement` */
  id: string
  /** `B. Guard Registration & Enforcement` */
  title: string
  score: number
  maxScore: number
  checks: AuditCheck[]
}

/** Critical check 의 실패. 감점이 아니라 게이트 위반이다. */
export interface AuditCriticalFailure {
  /** `GUARD_NOT_ENFORCED` */
  gate: string
  checkId: string
  summary: string
  evidence: string[]
}

/** 점수와 verdict에 영향을 주지 않는 관측치. */
export interface AuditWarning {
  id: string
  summary: string
  detail: string[]
}

export interface AuditNextAction {
  checkId: string
  category: string
  critical: boolean
  maxScore: number
  action: string
}

export interface HarnessAudit {
  schemaVersion: number
  auditVersion: string
  /** 점수는 같은 rubric_version 안에서만 비교할 수 있다. */
  rubricVersion: string
  rubricDigest: string
  /** Critical 실패가 하나라도 있으면 FAIL. 점수 임계값과는 무관하다. */
  verdict: 'PASS' | 'FAIL'
  score: number
  maxScore: number
  categories: AuditCategory[]
  criticalFailures: AuditCriticalFailure[]
  warnings: AuditWarning[]
  nextActions: AuditNextAction[]
}
