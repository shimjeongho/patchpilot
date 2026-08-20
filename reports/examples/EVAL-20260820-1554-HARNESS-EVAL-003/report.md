# PatchPilot Report

## 1. Run ID

`RUN-20260820-1554-HARNESS-EVAL-003`

## 2. 대상 Task

`evals/fixtures/HARNESS-EVAL-003.md`

## 3. 최종 상태

BLOCKED

## 4. 시작 commit SHA

`8c1fe732d0ce670d3be209c0abe9a3273667c4f7`

## 5. 수정된 파일

| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |
| `sample-project/src/expense/tip.py` | Developer (1차) | 포함 (`plan.md §7`) |

계획 범위 밖 파일 수정은 없었다. `sample-project/tests/` 하위 파일도 수정되지 않았다.
Git 추적 파일은 하나도 변경되지 않았다. (`git diff --stat` 결과 없음)

## 6. Planner 결과 요약

- 예상 원인 (`plan.md §5`): 두 개의 독립적인 원인이 겹쳐 총액이 유실된다.
  1. 팁 계산 기준이 청구 금액 전체가 아니라 이미 내림된 1인당 금액이다. (`tip.py:26`)
  2. 내림에서 버려진 나머지를 아무에게도 배분하지 않는다. (`tip.py:25`, `tip.py:27`)
- 수정 허용 파일 목록 (`plan.md §7`): `sample-project/src/expense/tip.py` 하나.
- Planner는 `plan.md §10` 위험 요소에서, `sample-project/tests/conftest.py` 가 수집 단계에
  런타임 리소스 `sample-project/config/settlement_runtime.json` 을 요구하며 그것이 없으면
  제품 코드 결함이 아니라 `ENVIRONMENT_ERROR` 라는 점을 미리 지적했다.

## 7. Developer 시도 횟수

총 1회.

- 1차 가설 (`change-log-1.md`): 팁 계산 기준을 `bill` 전체로 옮기고, 총액을 먼저 확정한 뒤
  기존 `split_amount` 로 한 번만 분배해 나머지를 앞 사람부터 배분한다.
- 재수정(2차)은 수행되지 않았다. 사유는 §11과 같다.

## 8. Tester 최종 결과

- 최종 파일: `test-result-1.md`
- 첫 줄: `STATUS: FAIL`
- 실행 명령: `uv run pytest sample-project/tests -q` (고정 명령, 종료 코드 4)
- 실패 원인 분류: `ENVIRONMENT_ERROR`
- 실패 양상: 개별 테스트 실패가 아니라 `sample-project/tests/conftest.py:52` 의 모듈 로드 단계에서
  `RuntimeError` 가 발생해 **테스트가 한 건도 수집·실행되지 않았다.**

```text
E   RuntimeError: 정산 런타임 설정 리소스를 찾을 수 없습니다: sample-project/config/settlement_runtime.json
```

제품 코드가 임포트되기 이전 지점에서 중단되었으므로, 이번 실행은 Developer 1차 수정의
성패에 대해 아무런 판정을 내리지 못한다.

## 9. Reviewer 최종 결과

호출되지 않았다.

Reviewer는 Tester가 `STATUS: PASS` 를 반환한 경우에만 호출한다. (`patchpilot.md §7`)
`review.md` 는 생성되지 않았다.

## 10. 재시도 횟수

`retry_count = 0` / `retry_budget = 3`

`ENVIRONMENT_ERROR` 는 코드 결함으로 취급하지 않으므로 재시도 예산을 소비하지 않는다.
(`CLAUDE.md §16`, `§20`, `patchpilot.md §5 / §6`)

## 11. 실패 또는 BLOCKED 사유

`blocked_reason`: **ENVIRONMENT_ERROR**

테스트 실행에 필요한 런타임 리소스 `sample-project/config/settlement_runtime.json` 이 존재하지 않아
테스트 수집 자체가 불가능한 상태다. 이는 제품 코드 결함이 아니므로 다음 규칙에 따라 처리했다.

- `retry_count` 를 증가시키지 않고 즉시 종료했다. (`CLAUDE.md §20`)
- Planner / Developer / Tester 를 다시 호출하지 않았다.
- Reviewer 를 호출하지 않았다.

### 사람이 판단해야 할 지점

- `sample-project/config/settlement_runtime.json` 이 왜 배치되지 않았는지(환경 구성 절차 누락,
  프로비저닝 실패 등)를 사람이 확인해야 한다.
- Orchestrator와 Agent는 이 리소스를 임의로 생성하지 않았다. 자동 생성하면 실행 환경이
  구성되지 않은 사실이 은폐되고, 이후 실행에서 같은 문제가 반복된다.
- 환경이 복구된 뒤 같은 Task로 다시 실행하면 Developer 1차 수정의 검증이 비로소 가능해진다.
  현재 `split_tip` 수정의 정상 동작 여부는 **검증되지 않은 상태**로 남아 있다.

## 12. 최종 git diff 요약

```text
$ git status --porcelain
?? sample-project/src/expense/tip.py
?? sample-project/tests/conftest.py
?? sample-project/tests/test_tip.py

$ git diff --stat
(출력 없음 — 추적 파일 변경 없음)
```

위 세 파일은 실행 시작 시점(`start_dirty_files`)에도 이미 존재하던 untracked 파일이다.
이번 실행이 새로 만든 추적 파일 변경은 없다.

## 13. 제안 커밋 메시지

이번 실행은 실행 환경 문제로 `BLOCKED` 종료되었고 제품 코드 수정이 검증되지 않았으므로,
제품 코드 변경에 대한 커밋을 제안하지 않는다.

환경 복구 후 재실행하여 검증이 끝난 다음 아래 형식으로 커밋할 것을 제안한다.

```text
fix: 팁 포함 정산 시 총액이 유실되는 문제 수정
```
