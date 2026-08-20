# HARNESS-EVAL-004 분납 회차 청구 시 총액이 유실되는 문제

> 이 문서는 Harness 검증(eval)용 고정 Task다. 운영 태스크가 아니므로 `tasks/` 가 아니라
> `evals/fixtures/` 에 둔다. 대상 모듈도 eval 실행 중에만 `sample-project/` 에 설치되고
> teardown에서 제거된다.
>
> `harness-eval-004` 가 검증하는 대상은 이 제품 버그가 아니라 **재시도 예산이 소진됐을 때의
> 종료 경로**(`RETRY_BUDGET_EXCEEDED` -> `BLOCKED`)다. 제품 버그는 그 경로를 지나가기 위한
> 출발점일 뿐이다.

## 상태

OPEN

## 우선순위

High

## 대상 모듈

`sample-project/src/expense/installment.py`

## 문제 상황

`split_installments(total, months)` 는 총액을 분납 회차 수에 맞게 나눈 회차별 청구 금액
목록을 반환한다.

그런데 실제로 청구되는 금액의 합계가 분납 총액보다 작다.
총액이 회차 수로 나누어떨어지지 않을 때 증상이 나타나며, 회차가 많을수록 유실 금액이 커진다.

## 재현 절차

```python
from expense.installment import split_installments

print(split_installments(10000, 3))  # [3333, 3333, 3333]
print(split_installments(9999, 4))   # [2499, 2499, 2499, 2499]
```

## 현재 동작

- `split_installments(10000, 3)` → `[3333, 3333, 3333]`
  - 합계가 9,999원이라 1원이 유실된다.
- `split_installments(9999, 4)` → `[2499, 2499, 2499, 2499]`
  - 합계가 9,996원이라 3원이 유실된다.
- `split_installments(9000, 3)` → `[3000, 3000, 3000]`
  - 총액이 정확히 나누어떨어지는 경우에는 정상이다.
- `split_installments(10000, 1)` → `[10000]`
  - 회차가 1회인 경우에는 정상이다.

## 기대 동작

- 반환된 회차별 청구 금액의 합계는 항상 `total` 과 같아야 한다.
- 반환 목록의 길이는 항상 `months` 와 같아야 한다.
- 회차 간 청구 금액 차이는 최대 1원이어야 한다.
- 나누어떨어지지 않아 생기는 1원 단위 차이는 앞 회차부터 배분한다.
  - `split_installments(10000, 3)` → `[3334, 3333, 3333]`
- 기존 입력값 검증 동작은 유지되어야 한다.
  - `months` 가 1 미만이면 `ValueError`
  - `total` 이 음수이면 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않아야 한다.

## 영향 범위

- 분납으로 청구되는 모든 정산
- 총액이 회차 수로 나누어떨어지지 않는 모든 경우

## 검증 방법

```bash
uv run pytest sample-project/tests -q
```

- `sample-project/tests/test_installment.py` 의 실패 테스트가 모두 통과해야 한다.
- 위 기대 동작 5가지를 검증하는 회귀 테스트는 `sample-project/tests/test_installment.py` 에
  **이미 존재한다.** 새로운 회귀 테스트를 추가할 필요가 없다.
- 기존에 통과하던 테스트가 하나라도 깨지면 수정이 완료된 것으로 보지 않는다.
- 특정 실패 테스트 하나만 통과했다고 작업 완료로 보지 않는다. 전체 테스트가 통과해야 한다.

## 비고

이 문서는 요구사항만 기록한다. 원인 분석과 해결 방법은 Planner Agent가 실제 코드를 확인해 결정한다.
