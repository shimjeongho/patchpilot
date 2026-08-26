/**
 * Harness Audit 대표 결과(`reports/audit/latest.json`) 읽기.
 *
 * `parse.ts` 와 **의도적으로 분리**되어 있다. Eval 과 Audit 은 검증하는 대상도, 데이터
 * 계약도, 없을 때의 처리도 다르다.
 *
 * |            | Eval (`parse.ts`)                | Audit (이 파일)                  |
 * | ---------- | -------------------------------- | -------------------------------- |
 * | 검증 대상  | 실행된 상태 전이                  | 정지 상태 구조 계약               |
 * | 데이터 원천 | `reports/examples/` 디렉터리 다수 | `reports/audit/latest.json` 하나  |
 * | 생산자     | `evals/eval_harness.py`          | `evals/harness_audit.py`         |
 * | 부재 시    | 빌드 실패 (필수)                  | `null` (선택)                    |
 *
 * 억지로 한 파서로 합치면 한쪽 계약이 바뀔 때 다른 쪽이 깨진다. 공유하는 것은
 * "저장소에 대해 읽기 전용" 이라는 규율뿐이다. 쓰기 계열 fs 함수는 import 하지 않는다.
 *
 * ## 부재와 손상을 다르게 처리하는 이유
 *
 * 파일이 **없는 것** 은 정상이다. Audit 은 Dashboard 의 선택적 데이터이고, 아직 한 번도
 * 대표 결과를 만들지 않은 저장소에서도 Dashboard 는 빌드되어야 한다.
 *
 * 파일이 **있는데 깨진 것** 은 정상이 아니다. 그것을 "Audit 없음" 으로 갈음하면 손상된
 * 증거가 화면에서 조용히 사라진다. 증거 문제를 은폐하는 실패 모드이므로 빌드를 세운다.
 * `parse.ts` 가 `state.json` 결손에 대해 취하는 태도와 같은 규율이다.
 */
import { readFileSync, statSync } from 'node:fs'
import path from 'node:path'

import type {
  AuditCategory,
  AuditCheck,
  AuditCriticalFailure,
  AuditNextAction,
  AuditWarning,
  HarnessAudit,
} from './types'

/** `dashboard/` 는 저장소 루트 바로 아래에 있다. 빌드 타임에 1회만 평가된다. */
const REPO_ROOT = path.resolve(process.cwd(), '..')

/**
 * 읽는 파일은 이 하나뿐이다.
 *
 * slug 나 디렉터리 이름 같은 **외부 입력을 경로에 섞지 않는다.** 받을 입력이 없으므로
 * 경로 탈출을 막을 검사도 필요 없다. `parse.ts` 가 `[slug]` 때문에 `resolveInsideExamples()`
 * 를 두는 것과 대비되는 지점이며, 경계를 좁혀서 얻은 결과지 빠뜨린 것이 아니다.
 */
const AUDIT_FILE = path.join(REPO_ROOT, 'reports', 'audit', 'latest.json')

/** 화면에 보여줄 때 쓰는 상대 경로. 절대 경로를 UI 로 내보내지 않는다. */
export const AUDIT_SOURCE = 'reports/audit/latest.json'

/**
 * Dashboard 가 이해하는 봉투 버전.
 *
 * `harness_audit.py` 의 `SCHEMA_VERSION` 과 짝이다. 생산자가 봉투를 바꾸면서 이 값을
 * 올리면 Dashboard 는 조용히 오해하는 대신 빌드를 세운다.
 */
const SUPPORTED_SCHEMA_VERSION = 1

class AuditDataError extends Error {
  constructor(message: string) {
    super(`${AUDIT_SOURCE}: ${message}`)
    this.name = 'AuditDataError'
  }
}

// ---------------------------------------------------------------------------
// 검증 도우미
//
// 값을 보정하지 않는다. 기대와 다르면 기본값으로 눌러 담는 대신 오류를 던진다.
// 보정은 손상된 증거를 정상으로 보이게 만드는 가장 흔한 경로다.
// ---------------------------------------------------------------------------

function asRecord(value: unknown, where: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new AuditDataError(`${where} 가 객체가 아닙니다`)
  }
  return value as Record<string, unknown>
}

function asString(value: unknown, where: string): string {
  if (typeof value !== 'string') throw new AuditDataError(`${where} 가 문자열이 아닙니다`)
  return value
}

function asNumber(value: unknown, where: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new AuditDataError(`${where} 가 숫자가 아닙니다`)
  }
  return value
}

function asBoolean(value: unknown, where: string): boolean {
  if (typeof value !== 'boolean') throw new AuditDataError(`${where} 가 boolean 이 아닙니다`)
  return value
}

function asArray(value: unknown, where: string): unknown[] {
  if (!Array.isArray(value)) throw new AuditDataError(`${where} 가 배열이 아닙니다`)
  return value
}

function asStringArray(value: unknown, where: string): string[] {
  return asArray(value, where).map((item, index) => asString(item, `${where}[${index}]`))
}

function asVerdict(value: unknown, where: string): 'PASS' | 'FAIL' {
  const token = asString(value, where)
  if (token !== 'PASS' && token !== 'FAIL') {
    throw new AuditDataError(`${where} 가 PASS / FAIL 이 아닙니다: ${token}`)
  }
  return token
}

// ---------------------------------------------------------------------------
// 파싱
// ---------------------------------------------------------------------------

function parseCheck(raw: unknown, where: string): AuditCheck {
  const record = asRecord(raw, where)
  return {
    id: asString(record.id, `${where}.id`),
    title: asString(record.title, `${where}.title`),
    result: asVerdict(record.result, `${where}.result`),
    score: asNumber(record.score, `${where}.score`),
    maxScore: asNumber(record.max_score, `${where}.max_score`),
    critical: asBoolean(record.critical, `${where}.critical`),
    contract: asString(record.contract, `${where}.contract`),
    evidence: asStringArray(record.evidence, `${where}.evidence`),
    remediation: asString(record.remediation, `${where}.remediation`),
  }
}

function parseCategory(raw: unknown, where: string): AuditCategory {
  const record = asRecord(raw, where)
  return {
    id: asString(record.id, `${where}.id`),
    title: asString(record.title, `${where}.title`),
    score: asNumber(record.score, `${where}.score`),
    maxScore: asNumber(record.max_score, `${where}.max_score`),
    checks: asArray(record.checks, `${where}.checks`).map((item, index) =>
      parseCheck(item, `${where}.checks[${index}]`),
    ),
  }
}

function parseCriticalFailure(raw: unknown, where: string): AuditCriticalFailure {
  const record = asRecord(raw, where)
  return {
    gate: asString(record.gate, `${where}.gate`),
    checkId: asString(record.check_id, `${where}.check_id`),
    summary: asString(record.summary, `${where}.summary`),
    evidence: asStringArray(record.evidence, `${where}.evidence`),
  }
}

function parseWarning(raw: unknown, where: string): AuditWarning {
  const record = asRecord(raw, where)
  return {
    id: asString(record.id, `${where}.id`),
    summary: asString(record.summary, `${where}.summary`),
    detail: asStringArray(record.detail, `${where}.detail`),
  }
}

function parseNextAction(raw: unknown, where: string): AuditNextAction {
  const record = asRecord(raw, where)
  return {
    checkId: asString(record.check_id, `${where}.check_id`),
    category: asString(record.category, `${where}.category`),
    critical: asBoolean(record.critical, `${where}.critical`),
    maxScore: asNumber(record.max_score, `${where}.max_score`),
    action: asString(record.action, `${where}.action`),
  }
}

/** 파일 내용을 도메인 타입으로. 손상이면 던진다. */
export function parseAudit(text: string): HarnessAudit {
  let document: unknown
  try {
    document = JSON.parse(text)
  } catch (error) {
    throw new AuditDataError(
      `JSON 파싱에 실패했습니다 (${error instanceof Error ? error.message : String(error)})`,
    )
  }

  const root = asRecord(document, '최상위')
  const schemaVersion = asNumber(root.schema_version, 'schema_version')
  if (schemaVersion !== SUPPORTED_SCHEMA_VERSION) {
    throw new AuditDataError(
      `Dashboard 가 모르는 schema_version 입니다: ${schemaVersion} ` +
        `(지원 ${SUPPORTED_SCHEMA_VERSION})`,
    )
  }

  return {
    schemaVersion,
    auditVersion: asString(root.audit_version, 'audit_version'),
    rubricVersion: asString(root.rubric_version, 'rubric_version'),
    rubricDigest: asString(root.rubric_digest, 'rubric_digest'),
    verdict: asVerdict(root.verdict, 'verdict'),
    score: asNumber(root.score, 'score'),
    maxScore: asNumber(root.max_score, 'max_score'),
    categories: asArray(root.categories, 'categories').map((item, index) =>
      parseCategory(item, `categories[${index}]`),
    ),
    criticalFailures: asArray(root.critical_failures, 'critical_failures').map((item, index) =>
      parseCriticalFailure(item, `critical_failures[${index}]`),
    ),
    warnings: asArray(root.warnings, 'warnings').map((item, index) =>
      parseWarning(item, `warnings[${index}]`),
    ),
    nextActions: asArray(root.next_actions, 'next_actions').map((item, index) =>
      parseNextAction(item, `next_actions[${index}]`),
    ),
  }
}

// ---------------------------------------------------------------------------
// 공개 API
// ---------------------------------------------------------------------------

let cache: HarnessAudit | null | undefined

/**
 * 대표 Audit 결과. 파일이 없으면 `null`.
 *
 * 점수·verdict·정렬 순서를 **다시 계산하지 않는다.** 전부 `harness_audit.py` 가 결정한
 * 값이며 Dashboard 는 표시만 한다. 여기서 한 번이라도 재계산하면 화면의 숫자와
 * `latest.json` 의 숫자가 갈라질 수 있고, 그러면 어느 쪽이 정본인지 알 수 없게 된다.
 */
export function getAudit(): HarnessAudit | null {
  if (cache !== undefined) return cache

  try {
    if (!statSync(AUDIT_FILE).isFile()) {
      cache = null
      return cache
    }
  } catch {
    // 아직 `--write` 를 한 번도 실행하지 않은 저장소. 정상 상태다.
    cache = null
    return cache
  }

  // 여기부터는 파일이 존재한다. 읽거나 해석하지 못하면 숨기지 않고 빌드를 세운다.
  let text: string
  try {
    text = readFileSync(AUDIT_FILE, 'utf8')
  } catch (error) {
    throw new AuditDataError(
      `파일이 존재하는데 읽지 못했습니다 (${error instanceof Error ? error.message : String(error)})`,
    )
  }

  cache = parseAudit(text.replace(/\r\n/g, '\n'))
  return cache
}

/** Category 제목의 `A. ` 같은 정렬용 접두를 뗀다. 표시 전용이며 값은 바꾸지 않는다. */
export function categoryLabel(title: string): string {
  return title.replace(/^[A-G]\.\s+/, '')
}
