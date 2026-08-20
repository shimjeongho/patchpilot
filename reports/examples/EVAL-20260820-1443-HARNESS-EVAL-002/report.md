# PatchPilot Report

## 1. Run ID

`RUN-20260820-1443-HARNESS-EVAL-002`

## 2. 대상 Task

`evals/fixtures/HARNESS-EVAL-002.md` — 봉사료 포함 정산 시 총액이 유실되는 문제

Harness Eval `harness-eval-002` (PLAN_DEFECT 재계획 라우팅 검증) 실행이다.

## 3. 최종 상태

SUCCESS

근거: 최종 `test-result-2.md` 첫 줄이 `STATUS: PASS`, `review.md` 첫 줄이 `VERDICT: APPROVED`. (`CLAUDE.md §19`)

## 4. 시작 commit SHA

`c32e097052b4c3f4844d74a6f74b848554e9c859`

시작 시점 미추적 파일 4건(eval fixture 설치분):
`sample-project/src/expense/charge_rounding.py`, `sample-project/src/expense/service_charge.py`,
`sample-project/tests/test_charge_rounding.py`, `sample-project/tests/test_service_charge.py`

## 5. 수정된 파일

| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |
| `sample-project/src/expense/service_charge.py` | Developer (1차) | 포함 (plan 1차 §7 / plan 2차 §7) |
| `sample-project/src/expense/charge_rounding.py` | Developer (2차) | 포함 (plan 2차 §7에서 추가) |

테스트 파일은 어느 Agent도 수정하지 않았다. Tester는 회귀 테스트를 추가하지 않았다(기존 계약 테스트가 두 결함을 모두 직접 검증).

## 6. Planner 결과 요약

### Planner 1차 (`plan-1.md`)

- 예상 원인: `service_charge.py:31` 의 `return [total // people] * people` 가 몫만 복제해 `total % people` 이 유실됨
- 수정 허용 파일 목록: `sample-project/src/expense/service_charge.py` 1개
- 이 시점의 `charge_rounding.py` 는 정상 동작했으므로 최소 변경 원칙상 옳은 범위였다.

### Planner 2차 (`plan-2.md`, PLAN_DEFECT 재계획)

- 예상 원인: `charge_rounding.py` 하단에서 `round_to_unit` 이 재정의되어 상단 올림 구현을 섀도잉, 결과적으로 내림 동작이 노출됨
- 1차 계획의 오판 명시: "`round_to_unit` 은 계약대로 동작한다", "`test_charge_rounding.py` 는 통과 중" 이라는 전제가 현재 코드 기준으로 사실이 아님
- 수정 허용 파일 목록: `charge_rounding.py`(추가) + `service_charge.py`(1차 유지)
- 재계획 근거로 `test-result-1.md` 를 명시 참조

## 7. Developer 시도 횟수

총 2회.

- 1차 가설: 분배 단계의 나머지 유실. `split_amount(total, people)` 재사용으로 합계 보존 (`change-log-1.md`)
- 2차 가설: 총액 계산 단계의 `round_to_unit` 섀도잉. 재정의 블록 삭제로 상단 올림 구현 복원 (`change-log-2.md`). 1차 수정은 유효하므로 원복하지 않음

## 8. Tester 최종 결과

- 최종 파일: `test-result-2.md`
- 첫 줄: `STATUS: PASS`
- 실행 결과: `82 passed in 0.08s`
- 1차 결과: `test-result-1.md` — `STATUS: FAIL`, `6 failed, 76 passed in 0.16s`, 실패 원인 분류 `PLAN_DEFECT`

## 9. Reviewer 최종 결과

- 최종 파일: `review.md`
- 첫 줄: `VERDICT: APPROVED`
- 주요 지적사항: 차단 사유 없음. 비차단 노트 2건 — (1) 대상 파일이 eval 설치 미추적 파일이라 일반 `git diff` 에 변경이 드러나지 않으므로 `evals/fixtures/` 원본과 대조해 검토함, (2) `service_charge.py` 주석 일부가 제거된 구현을 서술함

## 10. 재시도 횟수

`retry_count = 1` / `retry_budget = 3`

소비 내역: `PLAN_DEFECT` 로 인한 Planner 재계획 1회 (`CLAUDE.md §16`, §20)

## 11. 실패 또는 BLOCKED 사유

없음

## 12. 최종 git diff 요약

```text
(git diff --stat: 출력 없음 — 변경된 추적 파일 없음)

git status --porcelain:
?? sample-project/src/expense/charge_rounding.py
?? sample-project/src/expense/service_charge.py
?? sample-project/tests/test_charge_rounding.py
?? sample-project/tests/test_service_charge.py
```

이번 실행의 제품 코드 변경은 모두 eval이 설치한 미추적 파일 안에서 일어났고, 기존 추적 파일은 하나도 변경되지 않았다. 해당 파일들은 teardown에서 제거된다.

## 13. 제안 커밋 메시지

이 실행은 eval 산출물만 남기므로 제품 코드 커밋 대상이 없다. 결과 보존이 필요한 경우:

```text
test: PLAN_DEFECT 재계획 라우팅 eval 실행 결과 추가
```
