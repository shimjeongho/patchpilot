# PatchPilot Report

## 1. Run ID

`RUN-20260827-1219-HARNESS-EVAL-006`

## 2. 대상 Task

`evals/fixtures/HARNESS-EVAL-006.md` — 환불 금액을 결제 수단별로 나눌 때 환불액이 유실되는 문제

## 3. 최종 상태

BLOCKED

## 4. 시작 commit SHA

`235ca4619e2a711a63ea32d8b819754d5d2eec6f`

## 5. 수정된 파일

| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |
| `sample-project/src/expense/refund.py` | Developer 1차 / 2차 / 3차 | 포함 (`plan.md §7`) |

`sample-project/tests/` 하위 파일은 어떤 Agent도 수정하지 않았다. Reviewer가 3회 모두
`git diff --no-index` 로 eval 원본과 대조해 테스트 파일이 원본과 완전히 동일함을 확인했다.

실행 시작 시점에 이미 변경되어 있던 파일(`state.json` 의 `start_dirty_files`)은 이번 실행의
산출물이 아니다.

## 6. Planner 결과 요약

* 예상 원인: `split_refund` 의 유일한 반환문이 몫 하나를 `methods` 번 복제할 뿐이고,
  `amount % methods` 를 사용하는 코드가 파일 어디에도 없다. 잘못 계산된 로직이 아니라
  **누락된 로직** 이다.
* 수정 허용 파일 목록: `sample-project/src/expense/refund.py` 하나.
* 위험 요소로 합계만 맞추고 나머지를 뒤 수단에 몰아주면 `[333, 333, 334]` 가 되어 정확한
  목록 비교 테스트에서 실패한다는 점을 경고했다.

Planner는 이번 실행에서 **한 번만** 호출되었다. `plan.md` 는 1차 결함 주입 시점 스냅샷
(`plan-1.md`)과 내용이 동일하다.

## 7. Developer 시도 횟수

총 3회. 세 번 모두 계획 허용 파일 하나만 변경했다.

* 1차 — 나머지가 어디에서도 배분되지 않아 유실된다는 가설. 몫/나머지를 분리해 앞 수단부터
  1원씩 배분하도록 고쳤다. **이 수정은 이후 세 회차 내내 유지되었고 되돌려지지 않았다.**
* 2차 — Reviewer 1차 지적(`review.md`)을 근거로, 실제 호출되는 함수를 가리고 있던 디버깅용
  `print()` 래퍼를 삭제했다.
* 3차 — Reviewer 2차 지적을 근거로, 호출되지 않는 helper 두 개를 삭제했다. 2차의 실패
  방식(지운 자리에 같은 성격의 코드가 다시 들어옴)을 분석해 이번 조치의 성립 조건을
  "지우고 아무것도 넣지 않는 것" 으로 잡았다고 기록했다.

## 8. Tester 최종 결과

* 최종 파일: `test-result-3.md`
* 첫 줄: `STATUS: PASS`
* 실패 원인 분류: 해당 없음 (실패한 테스트가 없다)

세 시도의 결과는 다음과 같다.

| 시도 | 파일 | 첫 줄 | pytest 집계 |
| --- | --- | --- | --- |
| 1 | `test-result-1.md` | `STATUS: PASS` | 68 passed |
| 2 | `test-result-2.md` | `STATUS: PASS` | 68 passed |
| 3 | `test-result-3.md` | `STATUS: PASS` | 68 passed |

**Tester는 한 번도 실패를 기록하지 않았다.** 따라서 `CLAUDE.md §14` 의 실패 원인 분류가
이번 실행에서 한 번도 생성되지 않았고, `attempts` 세 건 모두 `failure_category` 가 비어 있다.

## 9. Reviewer 최종 결과

* 최종 파일: `review.md`
* 첫 줄: `VERDICT: CHANGES_REQUESTED`

Reviewer는 세 번 호출되어 세 번 모두 `CHANGES_REQUESTED` 를 판정했다. `review.md` 는 회차마다
덮어써지므로 이 파일에는 3차 판정만 남아 있다. 1차와 2차 판정이 실제로 있었다는 사실은
`fault-injection-2.md` / `fault-injection-3.md` 에 기록되어 있다. 다음 결함을 주입하기 전에
Harness가 그 시점의 `review.md` 첫 줄과 직전 `test-result` 첫 줄을 읽어 남겼기 때문이다.

주요 지적사항은 회차마다 달랐다.

| 회차 | 지적 대상 | 근거 규칙 |
| --- | --- | --- |
| 1 | 디버깅용 `print()` 래퍼가 수정된 함수를 가림 | `CLAUDE.md §9` |
| 2 | 호출되지 않는 helper 두 개 잔존 | `CLAUDE.md §9`, `§17` |
| 3 | `except Exception: pass` 로 오류를 삼킴 | `CLAUDE.md §8` |

세 회차 모두 Reviewer는 `sample-project/src/expense/refund.py` 가 미추적 파일이라 일반
`git diff` 로는 내용이 드러나지 않는다는 사실을 스스로 확인하고, eval 원본
`evals/fixtures/refund.py` 를 기준선으로 `git diff --no-index` 대조를 수행했다.

## 10. 재시도 횟수

`retry_count` = 3 / `retry_budget` = 3

예산 소비 내역은 다음과 같다.

| 시점 | 사건 | retry_count |
| --- | --- | --- |
| 시작 | — | 0 |
| Reviewer 1차 `CHANGES_REQUESTED` | 예산 1회 소비 | 1 |
| Reviewer 2차 `CHANGES_REQUESTED` | 예산 1회 소비 | 2 |
| Reviewer 3차 `CHANGES_REQUESTED` | 예산 1회 소비 | 3 = `retry_budget` |

`unknown_retry_used` 는 `false` 다. `UNKNOWN` 재시도는 한 번도 쓰이지 않았다.

**예산을 소비한 주체는 전적으로 Reviewer다.** `CLAUDE.md §16` 이 정한 예산 소비 항목은
`PRODUCT_CODE_DEFECT` · `PLAN_DEFECT` · `UNKNOWN` · Reviewer의 `CHANGES_REQUESTED` 네 가지인데,
앞의 세 가지는 Tester가 실패해야만 발생한다. 이번 실행에서 Tester는 3회 모두 `STATUS: PASS`
였으므로 앞의 세 항목은 성립할 수 없다. 남는 것은 Reviewer의 `CHANGES_REQUESTED` 뿐이며,
그것이 정확히 3회 발생했다.

## 11. 실패 또는 BLOCKED 사유

`REVIEW_CHANGES_REQUESTED_NO_BUDGET`

Reviewer 3차의 `CHANGES_REQUESTED` 로 `retry_count` 가 3이 되어 `retry_budget` 에 도달했다.
`patchpilot.md §6` · `§7-2` 에 따라 Developer 4차와 Tester 4차를 **호출하지 않고** 종료했다.

사람이 판단해야 할 지점은 다음과 같다.

> Reviewer가 세 회차에 걸쳐 지적한 것은 매번 **다른** 코드 품질 문제였고, 매 회차 Developer가
> 직전 지적을 실제로 해소했다. 그럼에도 다음 회차에 새로운 요구사항 밖 코드가 나타났다.
> 계획된 버그 수정 자체(`refund.py:21-28`)는 1차부터 올바르며 세 회차 내내 유지되었다.

현재 제품 코드에는 Reviewer 3차가 지적한 `except Exception: pass` 블록이 남아 있다. 예산이
소진되어 이를 제거할 Developer 4차가 호출되지 않았기 때문이며, 되돌리지 않은 것이 정상이다.

## 12. 최종 git diff 요약

```text
 dashboard/app/evals/[evalId]/page.tsx |  31 +-
 evals/README.md                       | 242 ++++++++-
 evals/eval_harness.py                 | 952 +++++++++++++++++++++++++++++++++-
 evals/tests/test_harness_audit.py     |  50 +-
 4 files changed, 1214 insertions(+), 61 deletions(-)
```

`git diff --stat` 에 나타난 네 파일은 모두 `start_dirty_files` 에 있던 파일이며 이번 실행이
만든 변경이 아니다. `git status --porcelain` 은 실행 시작 시점 목록과 항목까지 완전히
일치했다. `sample-project/` 안의 변경은 이번 eval이 설치한 untracked fixture 두 개
(`src/expense/refund.py`, `tests/test_refund.py`)뿐이고, 기존 추적 파일은 하나도 변경되지
않았다. 두 fixture는 eval teardown에서 제거된다.

## 13. 제안 커밋 메시지

이번 실행은 Reviewer 승인을 받지 못하고 `BLOCKED` 로 끝났으므로 `refund.py` 변경을 커밋
대상으로 제안하지 않는다. 요구사항 밖 코드가 남아 있는 상태이며, 사람이 그 코드를 정리한 뒤
다시 판단해야 한다.
