/**
 * `reports/examples/` 읽기와 Harness 산출물 파싱.
 *
 * 이 모듈은 저장소에 대해 **읽기 전용**이다. 쓰기 계열 fs 함수는 import 하지 않으며,
 * 모든 경로 접근은 `reports/examples/` 경계 안으로 제한된다.
 *
 * `evals/eval_harness.py` 를 import 하거나 수정하지 않고 같은 파일 계약을 독립 구현한다.
 * Eval 판정 코드와 Dashboard가 서로의 버그에 영향받지 않게 하려는 의도적 분리다.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'

import {
  FAILURE_CATEGORIES,
  type Artifact,
  type ArtifactKind,
  type Attempt,
  type EvalCheck,
  type EvalResult,
  type EvalState,
  type FailureCategory,
  type FaultInjection,
  type PlanSnapshot,
  type TestResult,
  type Verdict,
} from './types'

/** `dashboard/` 는 저장소 루트 바로 아래에 있다. 빌드 타임에 1회만 평가된다. */
export const REPO_ROOT = path.resolve(process.cwd(), '..')
export const EXAMPLES_DIR = path.join(REPO_ROOT, 'reports', 'examples')

// ---------------------------------------------------------------------------
// 읽기 전용 파일 접근
// ---------------------------------------------------------------------------

/** `[slug]` 가 URL에서 오므로 `../` 탈출을 실제로 막아야 한다. */
function resolveInsideExamples(...segments: string[]): string {
  const root = path.resolve(EXAMPLES_DIR)
  const target = path.resolve(root, ...segments)
  if (target !== root && !target.startsWith(root + path.sep)) {
    throw new Error(`reports/examples 밖의 경로에 접근했습니다: ${target}`)
  }
  return target
}

/**
 * 산출물을 읽어 개행을 LF로 통일한다.
 *
 * 산출물이 Windows에서 생성되어 CRLF가 섞여 있다. 정규화하지 않으면 첫 줄 판정
 * (`STATUS:` / `VERDICT:` / `EVAL:`)과 파일 내용 동일성 비교가 모두 어긋난다.
 */
export function readExampleFile(...segments: string[]): string | null {
  const target = resolveInsideExamples(...segments)
  try {
    if (!statSync(target).isFile()) return null
  } catch {
    return null
  }
  return readFileSync(target, 'utf8').replace(/\r\n/g, '\n')
}

export function listExampleDirs(): string[] {
  return readdirSync(EXAMPLES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
}

export function listExampleFiles(dir: string): string[] {
  return readdirSync(resolveInsideExamples(dir), { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort()
}

// ---------------------------------------------------------------------------
// Markdown 유틸
// ---------------------------------------------------------------------------

/** `STATUS: FAIL` 의 첫 줄에서 라벨 뒤 값을 꺼낸다. 라벨이 다르면 null. */
export function labeledFirstLine(text: string, label: string): string | null {
  const first = text.split('\n', 1)[0]?.trim() ?? ''
  const prefix = `${label}:`
  if (!first.startsWith(prefix)) return null
  return first.slice(prefix.length).trim()
}

const HEADING = /^#{1,4}\s+(.*)$/

/**
 * 키워드를 포함하는 헤딩 다음부터 그 다음 헤딩 직전까지의 본문.
 *
 * 헤딩 표기가 시나리오마다 달라(`## 실패 원인 분류` vs `## 7. 수정 허용 파일 목록`)
 * 완전 일치가 아니라 키워드 포함으로 찾는다.
 */
export function sectionBody(text: string, keyword: string): string | null {
  const lines = text.split('\n')

  // 코드 펜스 안의 `# 주석` 을 헤딩으로 오인하면 안 된다. `fault-injection.md` 의
  // `## 주입된 코드` 블록에는 `#` 로 시작하는 파이썬 주석이 실제로 들어 있다.
  const inFence: boolean[] = []
  let fenced = false
  for (const line of lines) {
    if (/^\s*```/.test(line)) {
      inFence.push(true)
      fenced = !fenced
      continue
    }
    inFence.push(fenced)
  }

  const isHeading = (index: number) => !inFence[index] && HEADING.test(lines[index])

  let start = -1
  for (let i = 0; i < lines.length; i += 1) {
    if (!isHeading(i)) continue
    const heading = HEADING.exec(lines[i])
    if (heading && heading[1].includes(keyword)) {
      start = i + 1
      break
    }
  }
  if (start === -1) return null

  const body: string[] = []
  for (let i = start; i < lines.length; i += 1) {
    if (isHeading(i)) break
    body.push(lines[i])
  }
  return body.join('\n').trim() || null
}

/**
 * 섹션 본문의 첫 번째 비어있지 않은 줄.
 *
 * EVAL-003의 `## 실패 원인 분류` 는 헤딩과 값 사이에 빈 줄이 있으므로 빈 줄 스킵이 필수다.
 */
export function sectionValue(text: string, keyword: string): string | null {
  const body = sectionBody(text, keyword)
  if (!body) return null
  return body.split('\n').map((line) => line.trim()).find((line) => line.length > 0) ?? null
}

function stripBackticks(value: string): string {
  return value.replace(/`/g, '').trim()
}

/** GFM 파이프 표 → 셀 배열. 구분선 행은 버린다. */
export function parseGfmTable(body: string): string[][] {
  return body
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('|'))
    .map((line) =>
      line
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((cell) => cell.trim()),
    )
    .filter((cells) => !cells.every((cell) => /^:?-{3,}:?$/.test(cell)))
}

/**
 * 섹션 본문 맨 앞의 연속된 불릿 블록에서만 백틱 경로를 뽑는다.
 *
 * 첫 블록으로 제한하는 이유가 있다. `수정 허용 파일 목록` 섹션은 허용 목록 뒤에 산문이
 * 오고, 실행에 따라서는 그 뒤에 **수정하면 안 되는 파일의 불릿 목록**이 다시 나온다
 * (EVAL-003의 plan). 모든 불릿을 긁으면 금지 목록이 허용 목록으로 뒤집혀 표시된다.
 */
export function leadingBulletPaths(body: string): string[] {
  const paths: string[] = []
  let started = false

  for (const line of body.split('\n')) {
    const trimmed = line.trim()
    const isBullet = trimmed.startsWith('- ') || trimmed.startsWith('* ')

    if (!started) {
      if (trimmed.length === 0) continue
      if (!isBullet) break // 불릿보다 산문이 먼저 오면 목록이 없는 것으로 본다
      started = true
    } else if (!isBullet) {
      if (trimmed.length === 0) continue
      break // 산문이 시작되면 첫 블록이 끝난 것이다
    }

    const match = /`([^`]+)`/.exec(trimmed)
    if (match) paths.push(match[1].trim())
  }

  return paths
}

// ---------------------------------------------------------------------------
// 산출물 parser
// ---------------------------------------------------------------------------

function asFailureCategory(value: string | null | undefined): FailureCategory | null {
  if (!value) return null
  const token = value.trim()
  // 근거 설명문에는 "PLAN_DEFECT 가 아니다" 같은 부정 서술이 흔하다. 부분 일치로 긁으면
  // 오탐하므로 열거값과 정확히 같을 때만 분류로 인정한다.
  return (FAILURE_CATEGORIES as readonly string[]).includes(token)
    ? (token as FailureCategory)
    : null
}

/**
 * `state.json` 파싱.
 *
 * 여기서의 계약 위반은 조용히 넘기지 않고 예외로 빌드를 세운다. 잘못 읽은 값으로 요약을
 * 보여주는 것이 이 대시보드에서 가장 나쁜 실패 모드다.
 */
export function parseState(raw: string, where: string): EvalState {
  let json: Record<string, unknown>
  try {
    json = JSON.parse(raw) as Record<string, unknown>
  } catch (error) {
    throw new Error(`${where}: state.json 을 파싱하지 못했습니다. (${String(error)})`)
  }

  const finalStatus = json.final_status
  if (finalStatus !== 'SUCCESS' && finalStatus !== 'BLOCKED') {
    throw new Error(
      `${where}: final_status 가 SUCCESS/BLOCKED 가 아닙니다. (${String(finalStatus)})`,
    )
  }

  const rawAttempts = Array.isArray(json.attempts) ? json.attempts : []
  const attempts: Attempt[] = rawAttempts.map((entry, index) => {
    const item = entry as Record<string, unknown>
    const status = item.status
    if (status !== 'PASS' && status !== 'FAIL') {
      throw new Error(
        `${where}: attempts[${index}].status 가 PASS/FAIL 이 아닙니다. (${String(status)})`,
      )
    }
    const category = item.failure_category
    if (category != null && asFailureCategory(String(category)) === null) {
      throw new Error(
        `${where}: attempts[${index}].failure_category 가 CLAUDE.md §14 의 분류가 아닙니다. (${String(category)})`,
      )
    }
    return {
      n: Number(item.n ?? index + 1),
      changeLog: String(item.change_log ?? ''),
      testResult: String(item.test_result ?? ''),
      status,
      failureCategory: category == null ? null : asFailureCategory(String(category)),
    }
  })

  const review = (json.review ?? {}) as Record<string, unknown>
  const verdict = review.verdict == null ? null : String(review.verdict)
  if (verdict !== null && verdict !== 'APPROVED' && verdict !== 'CHANGES_REQUESTED') {
    throw new Error(`${where}: review.verdict 가 CLAUDE.md §15 의 판정이 아닙니다. (${verdict})`)
  }

  return {
    runId: String(json.run_id ?? ''),
    task: String(json.task ?? ''),
    currentStage: String(json.current_stage ?? ''),
    retryCount: Number(json.retry_count ?? 0),
    retryBudget: Number(json.retry_budget ?? 0),
    unknownRetryUsed: Boolean(json.unknown_retry_used),
    startedAt: String(json.started_at ?? ''),
    finishedAt: String(json.finished_at ?? ''),
    startCommit: String(json.start_commit ?? ''),
    attempts,
    review: {
      verdict: verdict as Verdict | null,
      file: review.file == null ? null : String(review.file),
    },
    finalStatus,
    blockedReason: json.blocked_reason == null ? null : String(json.blocked_reason),
  }
}

/** `8 failed, 62 passed in 0.15s` 형태의 집계 줄만 인정한다. */
const PYTEST_SUMMARY = /^\d+ (?:failed|passed|error|errors|skipped)[^\n]*\bin [\d.]+s$/

export function parseTestResult(file: string, text: string): TestResult {
  const status = labeledFirstLine(text, 'STATUS')
  if (status !== 'PASS' && status !== 'FAIL') {
    throw new Error(`${file}: 첫 줄이 'STATUS: PASS' 또는 'STATUS: FAIL' 이 아닙니다.`)
  }
  const attemptMatch = /test-result-(\d+)\.md$/.exec(file)
  const command = sectionValue(text, '실행 명령')
  const summary = text
    .split('\n')
    .map((line) => line.trim())
    .find((line) => PYTEST_SUMMARY.test(line))

  return {
    attempt: attemptMatch ? Number(attemptMatch[1]) : 1,
    status,
    command: command ? stripBackticks(command) : null,
    failureCategory: asFailureCategory(sectionValue(text, '실패 원인 분류')),
    pytestSummary: summary ?? null,
  }
}

export function parseFaultInjection(file: string, text: string): FaultInjection {
  const fromName = /fault-injection-(\d+)\.md$/.exec(file)
  const fromSection = sectionValue(text, '시도 번호')
  const target = sectionValue(text, '대상 파일')

  return {
    file,
    attempt: fromName ? Number(fromName[1]) : fromSection ? Number(fromSection) : 1,
    faultId: sectionValue(text, 'Fault ID') ?? '(미기록)',
    targetFile: target ? stripBackticks(target) : '(미기록)',
    injectedAt: sectionValue(text, '주입 시각'),
    description: sectionValue(text, '결함 내용'),
  }
}

export function parsePlan(file: string, text: string): PlanSnapshot {
  const match = /plan-(\d+)\.md$/.exec(file)
  const body = sectionBody(text, '수정 허용 파일 목록')
  return {
    file,
    attempt: match ? Number(match[1]) : null,
    allowedFiles: body ? leadingBulletPaths(body) : [],
  }
}

export function parseEvalResult(text: string): EvalResult {
  const verdict = labeledFirstLine(text, 'EVAL')
  if (verdict !== 'PASS' && verdict !== 'FAIL') {
    throw new Error("eval-result.md: 첫 줄이 'EVAL: PASS' 또는 'EVAL: FAIL' 이 아닙니다.")
  }

  const tableBody = sectionBody(text, '자동 검증 항목')
  const rows = tableBody ? parseGfmTable(tableBody) : []
  const checks: EvalCheck[] = rows
    .slice(1) // 머리글 행
    .filter((cells) => cells.length >= 4)
    .map((cells) => ({
      no: Number(cells[0]),
      name: cells[1],
      result: cells[2] === 'PASS' ? 'PASS' : 'FAIL',
      evidence: cells[3],
    }))

  const totalLine = sectionValue(text, '종합') ?? ''
  const totalMatch = /(\d+)\s*\/\s*(\d+)/.exec(totalLine)

  return {
    verdict,
    scenarioId: sectionValue(text, '시나리오'),
    judgedAt: sectionValue(text, '판정 시각'),
    transition: sectionBody(text, '검증 대상 전이'),
    checks,
    passed: totalMatch ? Number(totalMatch[1]) : checks.filter((c) => c.result === 'PASS').length,
    total: totalMatch ? Number(totalMatch[2]) : checks.length,
  }
}

// ---------------------------------------------------------------------------
// Artifact 분류
// ---------------------------------------------------------------------------

interface Classified {
  kind: ArtifactKind
  attempt: number | null
  rank: number
}

function classify(file: string): Classified | null {
  let match: RegExpExecArray | null

  if (file === 'plan.md') return { kind: 'plan-final', attempt: null, rank: 0 }
  if ((match = /^plan-(\d+)\.md$/.exec(file))) {
    return { kind: 'plan', attempt: Number(match[1]), rank: 0 }
  }
  if (file === 'fault-injection.md') return { kind: 'fault-injection', attempt: 1, rank: 1 }
  if ((match = /^fault-injection-(\d+)\.md$/.exec(file))) {
    return { kind: 'fault-injection', attempt: Number(match[1]), rank: 1 }
  }
  if ((match = /^change-log-(\d+)\.md$/.exec(file))) {
    return { kind: 'change-log', attempt: Number(match[1]), rank: 2 }
  }
  if ((match = /^test-result-(\d+)\.md$/.exec(file))) {
    return { kind: 'test-result', attempt: Number(match[1]), rank: 3 }
  }
  if (file === 'review.md') return { kind: 'review', attempt: null, rank: 4 }
  if (file === 'report.md') return { kind: 'report', attempt: null, rank: 5 }
  if (file === 'state.json') return { kind: 'state', attempt: null, rank: 6 }
  if (file === 'eval-result.md') return { kind: 'eval-result', attempt: null, rank: 7 }
  return null
}

/**
 * 디렉터리의 산출물 목록을 파이프라인 순서로 정리한다.
 *
 * `plan.md` 는 항상 마지막 `plan-N.md` 와 내용이 같다(4개 대표 결과에서 확인). 별도 항목으로
 * 중복 노출하지 않고 별칭 표시로 처리하려고 동일성을 여기서 판정한다.
 */
export function discoverArtifacts(dir: string): Artifact[] {
  const files = listExampleFiles(dir).filter(
    (file) => file.endsWith('.md') || file.endsWith('.json'),
  )

  const planSnapshots = files.filter((file) => /^plan-\d+\.md$/.test(file)).sort()
  const lastSnapshot = planSnapshots[planSnapshots.length - 1]
  let finalPlanIsAlias = false
  if (lastSnapshot) {
    finalPlanIsAlias = readExampleFile(dir, 'plan.md') === readExampleFile(dir, lastSnapshot)
  }

  const artifacts: Artifact[] = []
  for (const file of files) {
    const classified = classify(file)
    if (!classified) continue
    artifacts.push({
      file,
      slug: file.replace(/\.(md|json)$/, ''),
      kind: classified.kind,
      attempt: classified.attempt,
      isFinalPlanAlias: classified.kind === 'plan-final' && finalPlanIsAlias,
    })
  }

  return artifacts.sort((a, b) => {
    const rankA = classify(a.file)!.rank
    const rankB = classify(b.file)!.rank
    if ((a.attempt ?? 0) !== (b.attempt ?? 0)) return (a.attempt ?? 0) - (b.attempt ?? 0)
    if (rankA !== rankB) return rankA - rankB
    return a.file.localeCompare(b.file)
  })
}
