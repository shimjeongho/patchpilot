---
description: Harness 통제 계약을 결정론적으로 채점하는 evals/harness_audit.py를 실행하고 결과를 그대로 보고한다
argument-hint: (없음) | --write | --min-score N
allowed-tools: Read, Bash(uv run python evals/harness_audit.py:*)
---

# PatchPilot Harness Audit

너는 이 커맨드에서 **판정자가 아니라 실행자** 다.

점수와 PASS / FAIL 은 `evals/harness_audit.py` 가 이미 결정론적으로 계산한다.
너의 역할은 그것을 실행하고, 나온 결과를 **다시 판단하지 않고** 전달하는 것뿐이다.

전달받은 인자: `$ARGUMENTS`

---

## 0. 절대 규칙

1. **재채점하지 않는다.** 스크립트가 낸 verdict / score / Critical 개수를 네 판단으로
   바꾸거나 보정하지 않는다. "사실상 통과로 볼 수 있다" 같은 문장을 쓰지 않는다.
2. **자동으로 고치지 않는다.** FAIL 한 check 를 이 커맨드 안에서 수정하지 않는다.
   `next_actions` 는 사람에게 보고할 제안이지 네가 실행할 작업 목록이 아니다.
3. **저장소를 수정하지 않는다.** 유일한 예외는 사람이 `--write` 를 직접 지정한
   경우의 `reports/audit/latest.json` 과 `reports/audit/latest.md` 두 파일이며,
   그것도 네가 쓰는 것이 아니라 스크립트가 쓴다.
4. **rubric 을 건드리지 않는다.** 점수가 낮다고 `harness_audit.py` 의 배점,
   Critical 목록, `RUBRIC_DIGEST` 를 조정하지 않는다. 그 순간 감사가 무의미해진다.
5. **없는 수치를 만들지 않는다.** 보고하는 모든 숫자는 실행 출력에 실제로 있어야 한다.

---

## 1. 인자 해석

`$ARGUMENTS` 를 다음 세 가지로만 해석한다.

| 입력 | 실행할 명령 |
| --- | --- |
| 비어 있음 | `uv run python evals/harness_audit.py` |
| `--write` | `uv run python evals/harness_audit.py --write` |
| `--min-score N` (N은 정수) | `uv run python evals/harness_audit.py --min-score N` |

기본은 **읽기 전용** 이다. 인자가 없으면 절대 `--write` 를 덧붙이지 않는다.
대표 결과 갱신은 사람이 명시적으로 요청했을 때만 일어난다.

위 표에 없는 인자가 들어오면 아무 것도 실행하지 말고 이 표를 그대로 보여준 뒤 중단한다.
인자를 추측해서 보정하지 않는다.

`--format json` / `--format markdown` 은 이 커맨드에서 쓰지 않는다.
기계가 소비할 출력이 필요하면 사람이 셸에서 직접 실행한다.

---

## 2. 실행

해석한 명령을 `Bash` 로 **한 번만** 실행한다.

실패했다고 다른 인자로 재실행하지 않는다. 종료 코드 자체가 결과다.

---

## 3. 종료 코드 해석

스크립트의 종료 코드는 세 가지뿐이며, 의미가 서로 다르다.

| 종료 코드 | 의미 | 보고 방식 |
| --- | --- | --- |
| `0` | Audit PASS | 결과를 그대로 보고한다 |
| `1` | Audit FAIL (Critical 존재 또는 `--min-score` 미달) | 결과를 그대로 보고한다 |
| `2` | **Audit 을 수행하지 못함** | 감사 결과가 아니라 **도구 고장** 으로 보고한다 |

`2` 를 FAIL 로 보고하지 않는다. 둘을 섞으면 "감사 도구가 깨졌다" 가
"감사 결과가 불합격이다" 로 오독된다. `2` 인 경우 점수를 인용하지 말고
stderr 의 `ERROR:` 줄을 그대로 옮긴 뒤 중단한다.

`--min-score` 미달로 `1` 이 된 경우, `Critical: 0` 이면 **Critical 은 0건이 맞다.**
임계값 미달을 Critical 로 바꿔 말하지 않는다.

---

## 4. 보고 형식

출력을 요약할 때 다음 순서를 지킨다. **Critical 이 항상 먼저다.**

1. 첫 줄 판정 (`AUDIT: PASS` / `AUDIT: FAIL`) 과 종료 코드
2. Critical Hard Gate — 있으면 게이트 이름과 check id 를 전부, 없으면 "없음"
3. Score / Critical 개수 / rubric_version / rubric_digest
4. Category 요약
5. FAIL 한 check 목록
6. 다음 행동 (스크립트의 `Next actions` 를 그대로. 순서를 바꾸지 않는다)
7. 경고 — 점수에 반영되지 않는 관측치임을 명시한다
8. `--write` 를 실행했다면 갱신된 두 파일 경로

점수를 해석해서 등급을 붙이거나 "훌륭하다" 같은 평가를 덧붙이지 않는다.
숫자는 같은 `rubric_version` 안에서만 비교 가능하다는 사실을 잊지 않는다.

마지막에 다음 한 줄을 반드시 덧붙인다.

> 이 점수는 저장소의 **정지 상태 계약 정합성** 이며 Harness 의 실행 효과가 아니다.
> 검사 범위 밖 항목은 `--format markdown` 의 "Audit이 검사하지 않는 것" 절에 있다.

---

## 5. 금지 사항

* 점수 재계산 또는 보정
* FAIL 한 check 자동 수정
* `harness_audit.py`, `CLAUDE.md`, `.claude/`, `evals/` 수정
* 인자 없이 `--write` 실행
* 종료 코드 `2` 를 FAIL 로 보고
* 실행 출력에 없는 수치 인용
* `reports/audit/latest.*` 외 파일 생성 (날짜별 audit 파일, history/, archive/ 포함)
