# HARNESS-EVAL-002 봉사료 포함 정산 시 총액이 유실되는 문제

> 이 문서는 Harness 검증(eval)용 고정 Task다. 운영 태스크가 아니므로 `tasks/` 가 아니라
> `evals/fixtures/` 에 둔다. 대상 모듈도 eval 실행 중에만 `sample-project/` 에 설치되고
> teardown에서 제거된다.

## 상태

OPEN

## 우선순위

High

## 대상 모듈

`sample-project/src/expense/service_charge.py`

## 문제 상황

`split_service_charge(bill, people, charge_percent, unit)` 는 청구 금액에 봉사료를 더하고
그 합계를 정산 화폐 단위에 맞춰 올린 총액을 인원수에 맞게 나눈 1인당 부담액 목록을 반환한다.

그런데 실제로 걷히는 금액의 합계가 걷어야 할 총액보다 작다.
총액이 인원수로 나누어떨어지지 않을 때 증상이 나타나며, 인원이 많을수록 유실 금액이 커진다.

## 재현 절차

```python
from expense.service_charge import split_service_charge

print(split_service_charge(10000, 3, 10, 1))    # [3666, 3666, 3666]
print(split_service_charge(10050, 3, 0, 100))   # [3366, 3366, 3366]
```

## 현재 동작

- `split_service_charge(10000, 3, 10, 1)` → `[3666, 3666, 3666]`
  - 봉사료 1,000원을 포함한 총액은 11,000원이지만 합계는 10,998원이다. 2원이 유실된다.
- `split_service_charge(10050, 3, 0, 100)` → `[3366, 3366, 3366]`
  - 총액은 100원 단위로 올림한 10,100원이지만 합계는 10,098원이다. 2원이 유실된다.
- `split_service_charge(9000, 3, 10, 100)` → `[3300, 3300, 3300]`
  - 총액 9,900원이 정확히 나누어떨어지는 경우에는 정상이다.
- `split_service_charge(10000, 1, 10, 100)` → `[11000]`
  - 인원이 1명인 경우에는 정상이다.

정산 단위 올림 자체는 현재 정상 동작한다. `split_service_charge(10050, 3, 0, 100)` 의
총액은 10,100원으로 올바르게 계산되며, 유실은 그 총액을 인원수로 나누는 과정에서 발생한다.

## 기대 동작

- 반환된 부담액의 합계는 항상 **봉사료를 더한 뒤 정산 단위로 올림한 총액** 과 같아야 한다.
- 봉사료는 청구 금액 전체에 `charge_percent` 를 적용해 내림으로 계산한다. 1원 미만은 청구하지 않는다.
- 총액은 `unit` 단위로 **올림** 한다. 단위에 걸치지 않는 단수 금액은 버리지 않고 올려서 청구한다.
- 반환 목록의 길이는 항상 `people` 과 같아야 한다.
- 사람 간 부담액 차이는 최대 1원이어야 한다.
- 나누어떨어지지 않아 생기는 1원 단위 차이는 앞 사람부터 배분한다.
  - `split_service_charge(10050, 3, 0, 100)` → `[3367, 3367, 3366]`
- 기존 입력값 검증 동작은 유지되어야 한다.
  - `people` 이 1 미만이면 `ValueError`
  - `bill` 이 음수이면 `ValueError`
  - `charge_percent` 가 음수이면 `ValueError`
  - `unit` 이 1 미만이면 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않아야 한다.

## 영향 범위

- 봉사료를 포함한 모든 정산
- 총액이 인원수로 나누어떨어지지 않는 모든 경우

## 검증 방법

```bash
uv run pytest sample-project/tests -q
```

- `sample-project/tests/test_service_charge.py` 의 실패 테스트가 모두 통과해야 한다.
- `sample-project/tests/test_charge_rounding.py` 는 정산 단위 올림 규칙의 계약 테스트다.
  현재 통과하고 있으며, 수정 이후에도 계속 통과해야 한다.
- 기존에 통과하던 테스트가 하나라도 깨지면 수정이 완료된 것으로 보지 않는다.
- 특정 실패 테스트 하나만 통과했다고 작업 완료로 보지 않는다. 전체 테스트가 통과해야 한다.

## 비고

이 문서는 요구사항만 기록한다. 원인 분석과 해결 방법은 Planner Agent가 실제 코드를 확인해 결정한다.
