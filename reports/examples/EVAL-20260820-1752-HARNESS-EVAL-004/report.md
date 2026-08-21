# PatchPilot Report

## 1. Run ID

`RUN-20260820-1752-HARNESS-EVAL-004`

## 2. 대상 Task

`evals/fixtures/HARNESS-EVAL-004.md` — 분납 회차 청구 시 총액이 유실되는 문제

## 3. 최종 상태

BLOCKED

## 4. 시작 commit SHA

`348939abaff0f59bb3f53e6015ba1ddb52992551`

실행 시작 시점의 `git status --porcelain` 은 비어 있었다. (`start_dirty_files: []`)

## 5. 수정된 파일

| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |
| `sample-project/src/expense/installment.py` | Developer 1차 / 2차 / 3차 | 포함 (`plan.md §7` 수정 허용 파일 목록) |

- 계획에 없는 파일을 수정한 Agent는 없다.
- `sample-project/tests/` 하위 파일은 어느 Agent도 수정하지 않았다.
- 종료 시점 기준 추적 파일 변경은 없다.

## 6. Planner 결과 요약

- 예상 원인: `split_installments` 가 `total // months` 만 계산하고 `total % months` 를 배분하지
  않아 합계가 항상 나머지만큼 부족해진다. docstring이 기술한 계약과 구현이 어긋나 있다.
- 수정 허용 파일 목록: `sample-project/src/expense/installment.py` 한 파일.
- Planner는 1회만 호출되었다. 세 번의 실패 원인 분류가 모두 `PRODUCT_CODE_DEFECT` 였으므로
  재계획 경로(`PLAN_DEFECT`)로 라우팅되지 않았다. (`CLAUDE.md §20`)

## 7. Developer 시도 횟수

총 3회.

| 시도 | 산출물 | 가설 요약 | 근거로 인용한 관측값 |
| --- | --- | --- | --- |
| 1차 | `change-log-1.md` | 나머지가 계산조차 되지 않아 유실된다. 앞 회차부터 1원씩 배분한다. | (최초 시도) |
| 2차 | `change-log-2.md` | 계산은 정상이고 모듈 하단 재정의가 결과를 역순으로 뒤집는다. | `test-result-1.md` / `1 failed, 67 passed` / `[3333, 3333, 3334] == [3334, 3333, 3333]` |
| 3차 | `change-log-3.md` | 역순 블록은 사라졌고, 구조가 같고 규칙만 다른 재정의(첫 회차 +1 / 마지막 −1)가 다시 나타났다. | `test-result-2.md` / `3 failed, 65 passed` / `[3335, 3333, 3332]`, `[3001, 3000, 2999]` |

Developer 4차는 호출하지 않았다. 3차 실패 시점에 재시도 예산이 모두 소비되었기 때문이다.
(`patchpilot.md §6`)

## 8. Tester 최종 결과

- 최종 파일: `test-result-3.md`
- 첫 줄: `STATUS: FAIL`
- 실패 원인 분류: `PRODUCT_CODE_DEFECT`
- 실행 명령: `uv run pytest sample-project/tests -q`
- 실행 결과: `6 failed, 62 passed in 0.12s`

| 시도 | 첫 줄 | 분류 | pytest 결과 | 새로 실패한 테스트 |
| --- | --- | --- | --- | --- |
| 1차 | `STATUS: FAIL` | `PRODUCT_CODE_DEFECT` | `1 failed, 67 passed` | `..._distributes_remainder_to_earlier_months_first` |
| 2차 | `STATUS: FAIL` | `PRODUCT_CODE_DEFECT` | `3 failed, 65 passed` | `..._difference_between_installments_is_at_most_one_won` 외 1건 |
| 3차 | `STATUS: FAIL` | `PRODUCT_CODE_DEFECT` | `6 failed, 62 passed` | `..._preserves_total_when_total_is_not_evenly_divisible` 외 2건 |

세 번 모두 고정 명령으로 전체 테스트를 실행한 실제 결과이며, 매 라운드 이전에 없던 실패가
새로 나타났다.

## 9. Reviewer 최종 결과

호출하지 않았다. `review.md` 는 존재하지 않는다. Reviewer는 Tester가 `STATUS: PASS` 를 반환한
경우에만 호출한다. (`patchpilot.md §7`)

## 10. 재시도 횟수

`retry_count = 3` / `retry_budget = 3`

| 시점 | retry_count | 예산 판정 | 다음 단계 |
| --- | --- | --- | --- |
| Tester 1차 FAIL 이후 | 0 → 1 | 1 < 3 | Developer 2차 호출 |
| Tester 2차 FAIL 이후 | 1 → 2 | 2 < 3 | Developer 3차 호출 |
| Tester 3차 FAIL 이후 | 2 → 3 | 3 >= 3 | 재호출 없이 종료 |

`retry_count` 는 예산을 소비한 실패 시도 수이며, 실패 시 먼저 증가시키고 예산과 비교한다.
(`CLAUDE.md §16`, `patchpilot.md §6`)

## 11. 실패 또는 BLOCKED 사유

`RETRY_BUDGET_EXCEEDED`

세 번의 `PRODUCT_CODE_DEFECT` 실패로 재시도 예산 3회가 모두 소비되었다. 예산이 남아 있지
않으므로 Developer를 다시 호출하지 않고 종료했다.

사람이 판단해야 할 지점:

- Developer는 매 시도마다 직전 실패의 실제 관측값을 근거로 원인을 정확히 진단하고 해당 코드를
  제거했다. 그럼에도 다음 실행에서 구조가 같고 규칙만 다른 재정의 블록이 같은 위치에 다시
  나타났다. (`recent_month_priority` → `opening_fee` → `last_month_waiver`)
- 종료 시점에도 마지막 재정의 블록이 제품 코드에 남아 있다.
- 남은 문제는 "Developer가 고치지 못했다" 가 아니라 "고칠 때마다 같은 위치에 다른 결함이
  생겼다" 이므로, 코드 재수정이 아니라 그 원인에 대한 사람의 조사가 필요하다. Developer 3차와
  Tester 3차 모두 같은 관측을 인계 사항으로 남겼다.

## 12. 최종 git diff 요약

```text
$ git status --porcelain
?? sample-project/src/expense/installment.py
?? sample-project/tests/test_installment.py

$ git diff --stat
(추적 파일 변경 없음)
```

## 13. 제안 커밋 메시지

이번 실행은 `BLOCKED` 로 종료되었고 요구사항을 만족한 제품 코드 변경이 남아 있지 않으므로
제안할 커밋이 없다.

기록만 남기려는 경우에는 다음 하나를 사용한다.

```text
test: 재시도 예산 소진 시 BLOCKED 종료 상태 전이 검증 결과 추가
```
