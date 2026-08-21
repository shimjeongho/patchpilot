/**
 * 상태 전이 Timeline 합성.
 *
 * `state.json` 만으로는 전이를 그릴 수 없다. 예를 들어 EVAL-002의 Planner 재호출은
 * `state.json` 어디에도 기록되지 않고 `plan-2.md` 라는 산출물의 존재로만 드러난다.
 * 그래서 이 모듈은 state.json + 산출물 존재 여부 + 결함 주입 기록을 합쳐서 전이를 만든다.
 *
 * 재시도 예산 누적은 `CLAUDE.md` §16 을 그대로 따르고, 마지막에 `state.json` 의
 * `retry_count` 와 대조한다. 어긋나면 조용히 덮어쓰지 않고 화면에 경고로 드러낸다.
 */
import { BUDGET_CONSUMING_CATEGORIES, type EvalDetail, type FailureCategory } from './types'

export type EventActor =
  | 'PLANNER'
  | 'DEVELOPER'
  | 'FAULT'
  | 'TESTER'
  | 'ORCHESTRATOR'
  | 'REVIEWER'
  | 'SKIPPED'
  | 'TERMINAL'

export type Tone = 'neutral' | 'ok' | 'fail' | 'warn' | 'muted'

export interface EventLink {
  file: string
  slug: string
}

export interface TimelineEvent {
  seq: number
  actor: EventActor
  tone: Tone
  label: string
  badge: string | null
  lines: string[]
  /** 이벤트 직후의 재시도 예산 상태. 예산과 무관한 이벤트는 null. */
  retryBefore: number | null
  retryAfter: number | null
  retryConsumed: boolean
  links: EventLink[]
}

export interface AgentLane {
  agent: string
  calls: number
  /** 호출되지 않은 것이 정상인 경우의 설명. 자동 검증으로 보증된 부재를 구분한다. */
  skippedNote: string | null
}

export interface Timeline {
  events: TimelineEvent[]
  retryBudget: number
  derivedRetryCount: number
  /** 합성한 누적값이 state.json 의 retry_count 와 일치하는가. */
  retryMatchesState: boolean
  agentLanes: AgentLane[]
}

function slugOf(file: string): EventLink {
  return { file, slug: file.replace(/\.(md|json)$/, '') }
}

/** `CLAUDE.md` §20 의 라우팅 결과를 한 줄로 옮긴다. */
function routingNote(category: FailureCategory | null): string {
  switch (category) {
    case 'PRODUCT_CODE_DEFECT':
      return '§20 PRODUCT_CODE_DEFECT → Developer 재호출'
    case 'PLAN_DEFECT':
      return '§20 PLAN_DEFECT → Planner 재호출 (계획을 다시 세운다)'
    case 'ENVIRONMENT_ERROR':
      return '§20 ENVIRONMENT_ERROR → 코드 문제가 아니므로 예산을 쓰지 않고 즉시 종료'
    case 'TEST_DEFECT':
      return '§20 TEST_DEFECT → 테스트를 자동 수정하지 않고 즉시 종료'
    case 'UNKNOWN':
      return '§20 UNKNOWN → Developer에게 1회만 추가 기회'
    default:
      return '§20 분류 없음'
  }
}

export function buildTimeline(detail: EvalDetail): Timeline {
  const { state, plans, faults, testResults, artifacts, evalResult } = detail
  const events: TimelineEvent[] = []
  let retry = 0

  const push = (event: Omit<TimelineEvent, 'seq'>) => {
    events.push({ ...event, seq: events.length + 1 })
  }

  const planFor = (attempt: number) =>
    plans.find((plan) => (plan.attempt ?? 1) === attempt) ?? null

  // --- Planner 1차 -----------------------------------------------------------
  const firstPlan = planFor(1) ?? plans[0] ?? null
  push({
    actor: 'PLANNER',
    tone: 'neutral',
    label: 'Planner 1차',
    badge: null,
    lines: firstPlan
      ? [`수정 허용 파일: ${firstPlan.allowedFiles.join(', ') || '(기록 없음)'}`]
      : ['plan 산출물을 찾지 못했습니다.'],
    retryBefore: null,
    retryAfter: null,
    retryConsumed: false,
    links: firstPlan ? [slugOf(firstPlan.file)] : [],
  })

  // --- 시도 반복 -------------------------------------------------------------
  for (const attempt of state.attempts) {
    const n = attempt.n

    // 재계획은 state.json 에 없다. plan-N.md 의 존재로만 드러난다.
    const replan = n > 1 ? planFor(n) : null
    if (replan) {
      const previous = planFor(n - 1)
      const added = previous
        ? replan.allowedFiles.filter((file) => !previous.allowedFiles.includes(file))
        : []
      push({
        actor: 'PLANNER',
        tone: 'warn',
        label: `Planner ${n}차 (재계획)`,
        badge: '재계획',
        lines: [
          `수정 허용 파일: ${replan.allowedFiles.join(', ') || '(기록 없음)'}`,
          added.length > 0 ? `${n}차에서 추가된 파일: ${added.join(', ')}` : '허용 목록 변화 없음',
        ],
        retryBefore: null,
        retryAfter: null,
        retryConsumed: false,
        links: [slugOf(replan.file)],
      })
    }

    push({
      actor: 'DEVELOPER',
      tone: 'neutral',
      label: `Developer ${n}차`,
      badge: null,
      lines: n > 1 ? [`이전 test-result-${n - 1}.md 를 근거로 재수정`] : [],
      retryBefore: null,
      retryAfter: null,
      retryConsumed: false,
      links: attempt.changeLog ? [slugOf(attempt.changeLog)] : [],
    })

    const fault = faults.find((item) => item.attempt === n)
    if (fault) {
      push({
        actor: 'FAULT',
        tone: 'warn',
        label: `Fault Injection ${n}`,
        badge: fault.faultId,
        lines: [`대상: ${fault.targetFile}`, fault.description ?? ''].filter(Boolean),
        retryBefore: null,
        retryAfter: null,
        retryConsumed: false,
        links: [slugOf(fault.file)],
      })
    }

    const testResult = testResults.find((item) => item.attempt === n)
    push({
      actor: 'TESTER',
      tone: attempt.status === 'PASS' ? 'ok' : 'fail',
      label: `Tester ${n}차`,
      badge: `STATUS: ${attempt.status}`,
      lines: [
        testResult?.pytestSummary ?? 'pytest 집계 줄 없음 (수집 단계에서 중단)',
        testResult?.command ? `실행 명령: ${testResult.command}` : '',
      ].filter(Boolean),
      retryBefore: null,
      retryAfter: null,
      retryConsumed: false,
      links: attempt.testResult ? [slugOf(attempt.testResult)] : [],
    })

    if (attempt.status !== 'FAIL') continue

    const consumed =
      attempt.failureCategory !== null &&
      BUDGET_CONSUMING_CATEGORIES.has(attempt.failureCategory)
    const before = retry
    if (consumed) retry += 1
    const exhausted = consumed && retry >= state.retryBudget

    // 예산이 소진된 시점에는 라우팅 대상(`Developer 재호출`)을 말하면 사실과 어긋난다.
    // 분류는 그대로 두되 재호출이 일어나지 않았음을 이유와 함께 적는다.
    const lines = exhausted
      ? [
          `분류: ${attempt.failureCategory} (§20 상 재수정 대상)`,
          `retry_count(${retry}) >= retry_budget(${state.retryBudget}) → §16 추가 Agent 재호출 없이 BLOCKED 종료`,
        ]
      : [routingNote(attempt.failureCategory)]

    if (!exhausted) {
      lines.push(
        consumed
          ? `재시도 예산 1회 소비 (retry_count ${before} → ${retry})`
          : `재시도 예산 미소비 (retry_count ${before} 유지)`,
      )
    }

    push({
      actor: 'ORCHESTRATOR',
      tone: exhausted || !consumed ? 'fail' : 'warn',
      label: 'Orchestrator 라우팅',
      badge: attempt.failureCategory,
      lines,
      retryBefore: before,
      retryAfter: retry,
      retryConsumed: consumed,
      links: [],
    })
  }

  // --- 호출되지 않은 주체 -----------------------------------------------------
  // 부재를 추측하지 않는다. eval-result.md 가 "호출되지 않음"을 자동 검증 항목으로
  // 판정해 두었으므로 그 판정을 그대로 읽어서 표시한다.
  const skippedChecks = (evalResult?.checks ?? []).filter((check) =>
    /호출되지 않음|이루어지지 않음/.test(check.name),
  )
  for (const check of skippedChecks) {
    push({
      actor: 'SKIPPED',
      tone: 'muted',
      label: check.name,
      badge: check.result === 'PASS' ? '검증됨' : '검증 실패',
      lines: [check.evidence],
      retryBefore: null,
      retryAfter: null,
      retryConsumed: false,
      links: [],
    })
  }

  // --- Reviewer --------------------------------------------------------------
  if (state.review.verdict) {
    push({
      actor: 'REVIEWER',
      tone: state.review.verdict === 'APPROVED' ? 'ok' : 'fail',
      label: 'Reviewer',
      badge: `VERDICT: ${state.review.verdict}`,
      lines: ['실제 git diff 기준 검토 (CLAUDE.md §15)'],
      retryBefore: null,
      retryAfter: null,
      retryConsumed: false,
      links: state.review.file ? [slugOf(state.review.file)] : [],
    })
  }

  // --- 종료 ------------------------------------------------------------------
  push({
    actor: 'TERMINAL',
    tone: state.finalStatus === 'SUCCESS' ? 'ok' : 'fail',
    label: state.finalStatus,
    badge: state.blockedReason,
    lines:
      state.finalStatus === 'SUCCESS'
        ? ['최종 test-result 가 PASS 이고 review 가 APPROVED (CLAUDE.md §19)']
        : [`Orchestrator가 BLOCKED로 종료 (사유: ${state.blockedReason ?? '미기록'})`],
    retryBefore: null,
    retryAfter: retry,
    retryConsumed: false,
    links: ['report.md', 'state.json'].map(slugOf),
  })

  // --- Agent 실행 여부 --------------------------------------------------------
  const countKind = (kind: string) => artifacts.filter((item) => item.kind === kind).length
  const skippedNoteFor = (agent: string) => {
    const check = skippedChecks.find((item) => item.name.includes(agent))
    if (!check) return '미호출'
    return check.result === 'PASS' ? '미호출 (자동 검증됨)' : '미호출 (검증 실패)'
  }

  const plannerCalls = plans.length
  const agentLanes: AgentLane[] = [
    {
      agent: 'Planner',
      calls: plannerCalls,
      skippedNote: plannerCalls === 0 ? skippedNoteFor('Planner') : null,
    },
    {
      agent: 'Developer',
      calls: countKind('change-log'),
      skippedNote: null,
    },
    {
      agent: 'Tester',
      calls: countKind('test-result'),
      skippedNote: null,
    },
    {
      agent: 'Reviewer',
      calls: state.review.verdict ? 1 : 0,
      skippedNote: state.review.verdict ? null : skippedNoteFor('Reviewer'),
    },
  ]

  return {
    events,
    retryBudget: state.retryBudget,
    derivedRetryCount: retry,
    retryMatchesState: retry === state.retryCount,
    agentLanes,
  }
}
