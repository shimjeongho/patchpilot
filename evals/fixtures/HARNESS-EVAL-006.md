# HARNESS-EVAL-006 환불 금액을 결제 수단별로 나눌 때 환불액이 유실되는 문제

> 이 문서는 Harness 검증(eval)용 고정 Task다. 운영 태스크가 아니므로 `tasks/` 가 아니라
> `evals/fixtures/` 에 둔다. 대상 모듈도 eval 실행 중에만 `sample-project/` 에 설치되고
> teardown에서 제거된다.

## 상태

OPEN

## 우선순위

High

## 대상 모듈

`sample-project/src/expense/refund.py`

## 문제 상황

`split_refund(amount, methods)` 는 환불 금액을 결제 수단 수에 맞게 나눈 수단별 환불액 목록을
반환한다.

그런데 실제로 돌려주는 금액의 합계가 환불 금액보다 작다. 결제 수단 수로 나누어떨어지지 않는
금액에서 증상이 나타나며, 수단이 많을수록 유실 금액이 커진다.

## 재현 절차

```python
from expense.refund import split_refund

print(split_refund(1000, 3))  # [333, 333, 333]
print(split_refund(1001, 3))  # [333, 333, 333]
```

## 현재 동작

- `split_refund(1000, 3)` → `[333, 333, 333]`
  - 합계가 999원으로 1원이 유실된다.
- `split_refund(1001, 3)` → `[333, 333, 333]`
  - 합계가 999원으로 2원이 유실된다.
- `split_refund(900, 3)` → `[300, 300, 300]`
  - 정확히 나누어떨어지는 경우에는 정상이다.
- `split_refund(1000, 1)` → `[1000]`
  - 결제 수단이 1개인 경우에는 정상이다.

## 기대 동작

- 반환된 수단별 환불액의 합계는 항상 `amount` 와 같아야 한다.
- 반환 목록의 길이는 항상 `methods` 와 같아야 한다.
- 수단 간 환불액 차이는 최대 1원이어야 한다.
- 나누어떨어지지 않아 생기는 1원 단위 나머지는 앞 수단부터 순서대로 배분한다.
  - `split_refund(1000, 3)` → `[334, 333, 333]`
  - `split_refund(1001, 3)` → `[334, 334, 333]`
- 기존 입력값 검증 동작은 유지되어야 한다.
  - `methods` 가 1 미만이면 `ValueError`
  - `amount` 가 음수이면 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않아야 한다.

## 영향 범위

- 결제 취소가 발생하는 모든 환불
- 환불 금액이 결제 수단 수로 나누어떨어지지 않는 모든 경우

## 검증 방법

```bash
uv run pytest sample-project/tests -q
```

- `sample-project/tests/test_refund.py` 의 실패 테스트가 모두 통과해야 한다.
- 기존에 통과하던 테스트가 하나라도 깨지면 수정이 완료된 것으로 보지 않는다.
- 특정 실패 테스트 하나만 통과했다고 작업 완료로 보지 않는다. 전체 테스트가 통과해야 한다.

## 비고

이 문서는 요구사항만 기록한다. 원인 분석과 해결 방법은 Planner Agent가 실제 코드를 확인해 결정한다.
