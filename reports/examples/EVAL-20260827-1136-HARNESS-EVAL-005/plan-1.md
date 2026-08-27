# Plan: 쿠폰 할인액 분배 시 나머지 금액이 유실되는 문제 수정

## 1. 요구사항 요약

`apply_coupon(discount, items)` 가 반환하는 항목별 할인액 목록에서, 항목 수로 나누어떨어지지
않는 나머지 금액이 버려져 합계가 `discount` 보다 작아진다. 나머지를 **앞 항목부터 순서대로**
배분해 합계를 보존하도록 수정한다.

대상: `sample-project/src/expense/coupon.py` 의 `apply_coupon`

## 2. 재현 조건

- `discount` 가 `items` 로 나누어떨어지지 않는 모든 입력.
- 유실 금액은 `discount % items` 이며, 항목 수가 많을수록 커진다.

```python
from expense.coupon import apply_coupon

apply_coupon(1000, 3)  # 합계 999 (1원 유실)
apply_coupon(1001, 3)  # 합계 999 (2원 유실)
```

## 3. 기대 동작

다음 불변식을 모두 만족해야 한다.

- `sum(apply_coupon(discount, items)) == discount` (항상)
- `len(apply_coupon(discount, items)) == items` (항상)
- `max(shares) - min(shares) <= 1`
- 나머지(`discount % items`)는 **앞 항목부터** 1원씩 배분한다. 뒤 항목에 몰아주는 방식은
  요구사항 위반이다.
  - `apply_coupon(1000, 3)` → `[334, 333, 333]`
  - `apply_coupon(1001, 3)` → `[334, 334, 333]`
- 기존 동작으로 유지해야 하는 것:
  - `apply_coupon(900, 3)` → `[300, 300, 300]` (나누어떨어지는 경우)
  - `apply_coupon(1000, 1)` → `[1000]`
  - `apply_coupon(0, 3)` → `[0, 0, 0]`
  - `items` 가 1 미만이면 `ValueError`
  - `discount` 가 음수이면 `ValueError`
  - 위 두 `ValueError` 의 메시지 형식도 그대로 유지한다.

## 4. 현재 동작

- `apply_coupon(1000, 3)` → `[333, 333, 333]` (합계 999)
- `apply_coupon(1001, 3)` → `[333, 333, 333]` (합계 999)
- `apply_coupon(900, 3)` → `[300, 300, 300]` (정상)
- `apply_coupon(1000, 1)` → `[1000]` (정상)
- 입력값 검증은 현재도 정상 동작한다.

## 5. 예상 원인

`apply_coupon` 이 몫(`discount // items`)만 계산해 그 값을 항목 수만큼 복제한 리스트를 그대로
반환한다. 나머지(`discount % items`)를 계산하지도, 배분하지도 않으므로 정확히 나머지만큼의
금액이 유실된다. 나누어떨어지는 경우에는 나머지가 0이라 증상이 드러나지 않고, 항목이 1개일
때도 `discount // 1 == discount` 라서 정상으로 보인다. 이는 관찰된 현재 동작 4가지와 모두
일치한다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/coupon.py:21` — 함수의 반환문이
  `return [discount // items] * items` 한 줄이다. 몫만 사용하고 나머지를 다루는 코드가 함수
  전체에 존재하지 않는다. 이것이 합계 유실의 직접 원인이다.
- `sample-project/src/expense/coupon.py:16-19` — `items <= 0` 과 `discount < 0` 에 대한
  `ValueError` 검증은 이미 올바르게 구현되어 있다. 따라서 검증 로직은 이번 수정 대상이
  아니며 그대로 보존해야 한다.
- `sample-project/src/expense/coupon.py:7` — Docstring이 이미 "반환된 항목별 할인액의 합계는
  쿠폰 할인액과 항상 같아야 한다" 고 선언하고 있다. 즉 문서가 의도한 계약과 구현이 어긋난
  상태이며, 고쳐야 할 쪽은 구현이다.
- `sample-project/src/expense/splitter.py:21-28` — 같은 저장소의 `split_amount` 가 동일한
  "나머지를 앞 사람부터 1원씩 배분" 규칙을 이미 구현하고 있고, 그 의도를 주석으로 남기는
  스타일을 쓴다.
- `sample-project/src/expense/allocation.py:4-21` — `allocate_units` 도 같은 규칙을 공용
  helper 형태로 구현해 두었으며, `sample-project/src/expense/settlement.py:3,28` 에서 이를
  import해 재사용한다. 즉 이 저장소에는 동일 규칙에 대한 선례가 두 가지 형태로 존재한다.
  어느 쪽 스타일을 따를지는 Developer가 판단한다.
- `apply_coupon` 전체 검색 결과 제품 코드 내 호출자는 없고
  `sample-project/tests/test_coupon.py` 만 이 함수를 사용한다. 변경의 파급 범위가 이 함수
  하나로 한정된다는 근거다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/coupon.py`

이 파일 외에는 어떤 파일도 수정하지 않는다. 특히 `sample-project/tests/` 하위는 수정
대상이 아니다.

## 8. 구현 단계

1. `apply_coupon` 의 반환 로직이 나머지 금액을 반영하도록 바꾼다 — 현재는 몫만 복제하고
   있으므로, 나누어떨어지지 않을 때 남는 금액이 결과에 포함되지 않는다. 이 단계의 목적은
   §3의 합계 보존 불변식(`sum(result) == discount`)을 만족시키는 것이다.
   배분 순서는 앞 항목 우선이어야 하며, 결과 길이는 `items` 와 같아야 하고 항목 간 차이는
   1원을 넘지 않아야 한다.
   구현 방식(공용 helper `allocate_units` 재사용, `split_amount` 와 같은 인라인 방식 중
   무엇을 쓸지)은 Developer가 두 선례를 읽고 §17 최소 변경 원칙에 맞게 선택한다.

2. 기존 입력값 검증 분기와 그 에러 메시지를 그대로 유지한다 — 검증은 결함이 아니므로
   건드릴 이유가 없다. 이 단계의 목적은 §3-10(명시되지 않은 기존 동작 유지) 보장이다.

3. 나머지 배분 규칙의 의도를 코드에 남긴다 — "왜 앞 항목부터 배분하는가"는 비즈니스 규칙이며
   코드만 봐서는 알기 어렵다. `CLAUDE.md §5` 기준에 맞는 주석 한 줄이면 충분하고, 동작을
   그대로 옮겨 쓰는 주석은 달지 않는다. 기존 Docstring은 이미 계약을 올바르게 서술하고
   있으므로 그대로 두거나 최소한으로만 손댄다.

## 9. 검증 방법

- 실행 명령: `uv run pytest sample-project/tests -q`
- 통과 판정 기준:
  - `sample-project/tests/test_coupon.py` 의 12개 테스트가 모두 통과한다.
    특히 `test_apply_coupon_distributes_remainder_to_earlier_items_first`,
    `test_apply_coupon_spreads_remainder_across_leading_items`,
    `test_apply_coupon_preserves_total_for_various_discounts_and_items` 가 통과해야 한다.
  - `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`,
    `test_reconciliation.py`, `test_formatter.py` 등 기존에 통과하던 테스트가 하나도
    깨지지 않는다.
  - 실패 0건이어야 한다. 특정 테스트 하나만 통과한 상태는 완료로 보지 않는다. (`CLAUDE.md §10`)

## 10. 예상 위험 요소

- **배분 방향 오류**: 나머지를 뒤 항목부터 배분해도 합계 보존과 최대 1원 차이 조건은
  만족하므로 `sum` 검증 테스트는 통과한다. 그러나 `[334, 333, 333]` 을 정확히 요구하는
  테스트에서 실패한다. 합계만 맞추고 끝내면 안 된다.
- **공용 helper 수정으로 인한 회귀**: `allocate_units` 를 재사용하기로 했더라도 그 함수 자체를
  고쳐서는 안 된다. `settlement.py` 가 이미 의존하고 있어 `test_settlement.py` 회귀로
  이어진다. 허용된 수정 파일은 `coupon.py` 하나뿐이다.
- **경계 입력 회귀**: `discount == 0`, `items == 1` 은 현재 정상 동작한다. 새 로직에서도
  각각 `[0, 0, 0]`, `[1000]` 을 유지하는지 확인해야 한다.
- **검증 로직 훼손**: 반환 로직을 고치면서 `ValueError` 분기나 메시지를 건드리면
  `test_apply_coupon_raises_value_error_*` 두 테스트가 깨진다.
- **범위 초과 변경**: 다른 모듈로 로직을 옮기거나 새 추상화를 만드는 것은 `CLAUDE.md §17`
  위반이다. 영향 범위는 `apply_coupon` 함수 내부로 한정된다.
