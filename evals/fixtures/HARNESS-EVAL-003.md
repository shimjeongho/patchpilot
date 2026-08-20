# HARNESS-EVAL-003 팁 포함 정산 시 총액이 유실되는 문제

> 이 문서는 Harness 검증(eval)용 고정 Task다. 운영 태스크가 아니므로 `tasks/` 가 아니라
> `evals/fixtures/` 에 둔다. 대상 모듈도 eval 실행 중에만 `sample-project/` 에 설치되고
> teardown에서 제거된다.
>
> 요구사항 자체는 `HARNESS-EVAL-001` 과 동일한 제품 버그를 쓴다. `harness-eval-003` 이
> 검증하는 대상은 제품 버그가 아니라 **실행 환경 오류가 발생했을 때의 라우팅**
> (`ENVIRONMENT_ERROR` -> 재시도 없이 즉시 `BLOCKED`)이므로, 제품 버그는 이미 검증된 것을
> 그대로 재사용해 변수를 하나로 줄인다.

## 상태

OPEN

## 우선순위

High

## 대상 모듈

`sample-project/src/expense/tip.py`

## 문제 상황

`split_tip(bill, people, tip_percent)` 는 청구 금액에 팁을 더한 총액을 인원수에 맞게 나눈
1인당 부담액 목록을 반환한다.

그런데 실제로 걷히는 금액의 합계가 청구 금액과 팁을 더한 총액보다 작다.
인원수로 나누어떨어지지 않는 금액에서 증상이 나타나며, 인원이 많을수록 유실 금액이 커진다.

## 재현 절차

```python
from expense.tip import split_tip

print(split_tip(10000, 3, 10))  # [3666, 3666, 3666]
print(split_tip(10000, 3, 0))   # [3333, 3333, 3333]
```

## 현재 동작

- `split_tip(10000, 3, 10)` → `[3666, 3666, 3666]`
  - 팁 1,000원을 포함한 총액은 11,000원이지만 합계는 10,998원이다. 2원이 유실된다.
- `split_tip(10000, 3, 0)` → `[3333, 3333, 3333]`
  - 팁이 없을 때도 합계가 9,999원으로 1원이 유실된다.
- `split_tip(9000, 3, 10)` → `[3300, 3300, 3300]`
  - 총액 9,900원이 정확히 나누어떨어지는 경우에는 정상이다.
- `split_tip(10000, 1, 10)` → `[11000]`
  - 인원이 1명인 경우에는 정상이다.

## 기대 동작

- 반환된 부담액의 합계는 항상 `bill + bill * tip_percent // 100` 과 같아야 한다.
- 팁은 청구 금액 전체에 `tip_percent` 를 적용해 내림으로 계산한다. 1원 미만은 청구하지 않는다.
- 반환 목록의 길이는 항상 `people` 과 같아야 한다.
- 사람 간 부담액 차이는 최대 1원이어야 한다.
- 나누어떨어지지 않아 생기는 1원 단위 차이는 앞 사람부터 배분한다.
  - `split_tip(10000, 3, 10)` → `[3667, 3667, 3666]`
- 기존 입력값 검증 동작은 유지되어야 한다.
  - `people` 이 1 미만이면 `ValueError`
  - `bill` 이 음수이면 `ValueError`
  - `tip_percent` 가 음수이면 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않아야 한다.

## 영향 범위

- 팁을 포함한 모든 정산
- 총액이 인원수로 나누어떨어지지 않는 모든 경우

## 검증 방법

```bash
uv run pytest sample-project/tests -q
```

- `sample-project/tests/test_tip.py` 의 실패 테스트가 모두 통과해야 한다.
- 기존에 통과하던 테스트가 하나라도 깨지면 수정이 완료된 것으로 보지 않는다.
- 특정 실패 테스트 하나만 통과했다고 작업 완료로 보지 않는다. 전체 테스트가 통과해야 한다.

## 비고

이 문서는 요구사항만 기록한다. 원인 분석과 해결 방법은 Planner Agent가 실제 코드를 확인해 결정한다.
