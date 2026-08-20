# PatchPilot Report

## 1. Run ID

`RUN-20260820-1318-HARNESS-EVAL-001`

Harness 재시도 루프를 검증하는 eval 실행이다. 실행 절차는 `evals/README.md §4`,
상태 머신과 판정 규칙은 `.claude/commands/patchpilot.md` 를 그대로 사용했다.

## 2. 대상 Task

`evals/fixtures/HARNESS-EVAL-001.md` — 팁 포함 정산 시 총액이 유실되는 문제

## 3. 최종 상태

SUCCESS

판정 근거 (`CLAUDE.md §19`):

- 최종 `test-result-2.md` 첫 줄이 `STATUS: PASS`
- `review.md` 첫 줄이 `VERDICT: APPROVED`

## 4. 시작 commit SHA

`3d5f7c31fd1ca711bb9f2368a096aa2700ad6355`

실행 시작 시점에 이미 변경되어 있던 파일 (`start_dirty_files`):

```text
?? sample-project/src/expense/tip.py
?? sample-project/tests/test_tip.py
```

두 파일은 `eval_harness.py setup` 이 설치한 eval fixture이며 추적되지 않은 상태로 시작했다.
따라서 `git diff` 에는 잡히지 않고, 이번 실행이 만든 변경은 `tip.py` 의 현재 내용 자체다.

## 5. 수정된 파일

| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |
| `sample-project/src/expense/tip.py` | Developer 1차, Developer 2차 | 포함 (`plan.md §7` 유일한 허용 파일) |

계획 밖 파일 수정은 없다. `sample-project/tests/` 하위는 실행 중 한 번도 변경되지 않았다.
Reviewer가 `diff evals/fixtures/test_tip.py sample-project/tests/test_tip.py` 로 차이 0을 확인했고,
`git diff --stat` 은 비어 있어 추적 파일도 무변경이다.

## 6. Planner 결과 요약

`plan.md` 는 `split_tip` 계산부에서 **내림(`//`)이 두 번 발생하며 두 나머지가 모두 유실**되는 것을
원인으로 진단했다.

- `tip.py:25` — `bill // people` 의 나머지 `bill % people` 를 아무에게도 배분하지 않는다.
- `tip.py:26` — 팁 기준이 `bill` 전체가 아니라 이미 내림된 1인당 금액이라 내림이 한 번 더 발생한다.
  `10000, 3, 10` 에서 팁이 1000원이 아닌 999원이 된다.
- `tip.py:27` — `[x] * people` 복제 구조라 합계가 항상 `people` 의 배수가 되어 잔여분 배분이 불가능하다.

수정 허용 파일 목록: `sample-project/src/expense/tip.py` 1개.
검증 방법: `uv run pytest sample-project/tests -q`

## 7. Developer 시도 횟수

총 2회.

| 시도 | 가설 요약 | 산출물 |
| --- | --- | --- |
| 1차 | 계산부의 두 내림 유실을 함께 제거. 팁을 `bill` 전체 기준으로 한 번만 내림하고 `split_amount(bill + tip, people)` 로 총액 하나만 배분 | `change-log-1.md` |
| 2차 | 계산식이 아니라 파일 하단에서 `split_tip` 을 재정의(shadowing)하는 후처리 블록이 원인이라고 재진단. 해당 블록만 삭제 | `change-log-2.md` |

2차가 1차와 다른 근거로 삼은 것은 `test-result-1.md` 의 세 가지 사실이다.

- 실패 8건이 모두 마지막 원소만 0인 동일 패턴이고 앞쪽 값은 기대값과 정확히 일치했다.
- `split_tip(10000, 1, 10)` 이 `[0]` 을 반환했다. 나머지 배분 계산으로는 유일한 사람 몫이 0이 될 수 없다.
- 총액이 나누어떨어지는 `split_tip(9000, 3, 10)` 까지 실패했다. `plan.md §2` 는 이 경우 원래 버그가
  재현되지 않는다고 명시하므로 원래 버그와 다른 결함이다.

## 8. Tester 최종 결과

- 최종 파일: `test-result-2.md`
- 첫 줄: `STATUS: PASS`
- 실행 결과: `70 passed in 0.08s` (`uv run pytest sample-project/tests -q`)
- 추가한 회귀 테스트: 없음. `test_tip.py` 의 기존 13개가 1차에서 실제로 결함을 검출했으므로 검출력이
  실증되었다고 판단

1차 결과는 `test-result-1.md`, 첫 줄 `STATUS: FAIL`, `8 failed, 62 passed`,
실패 원인 분류는 `PRODUCT_CODE_DEFECT` 였다.

## 9. Reviewer 최종 결과

- 최종 파일: `review.md`
- 첫 줄: `VERDICT: APPROVED`
- 주요 확인 사항
  - `grep -rn "patchpilot-eval\|_split_tip_before_last_person_rule" sample-project/` 매치 0건.
    `split_tip` 정의가 1개뿐이라 이름 shadowing 없음
  - `diff evals/fixtures/test_tip.py sample-project/tests/test_tip.py` 차이 0 — 테스트 무력화 없음
  - 테스트 수 교차 검증: 전체 70건 / `test_tip.py` 13건, skip·xfail 마커 없음
  - 계획 밖 파일 수정 0건, 새 의존성 0건, `print()`·미사용 import 0건
  - 검증 블록·Docstring·시그니처는 원본과 동일하게 유지됨
- 비블로킹 참고: 작업 트리의 `tip.py` 만 CRLF. `core.autocrlf=true` 이고 `git hash-object --path` 가
  LF 정규화 blob 해시와 동일해 커밋 diff에는 영향 없음

## 10. 재시도 횟수

`retry_count = 1` / `retry_budget = 3`

`test-result-1.md` 의 `PRODUCT_CODE_DEFECT` 분류에 따라 `CLAUDE.md §20` 라우팅으로
Developer를 1회 재호출하며 예산 1회를 소비했다.

## 11. 실패 또는 BLOCKED 사유

없음

## 12. 최종 git diff 요약

```text
(git diff --stat 출력 없음)
```

`sample-project/src/expense/tip.py` 와 `sample-project/tests/test_tip.py` 는 eval fixture로 설치된
추적되지 않은 파일이므로 `git diff` 에 나타나지 않는다. `git status --porcelain` 기준:

```text
?? sample-project/src/expense/tip.py
?? sample-project/tests/test_tip.py
```

두 파일은 실행 종료 후 `eval_harness.py finish` 의 teardown 단계에서 제거된다.

## 13. 제안 커밋 메시지

이번 실행의 변경 대상은 eval 실행 중에만 존재하는 fixture이므로 제품 코드 커밋 대상이 없다.
대표 결과를 승격해 커밋하는 경우에만 다음을 사용한다.

```text
test: Harness 재시도 상태 전이 eval 대표 실행 결과 추가
```
