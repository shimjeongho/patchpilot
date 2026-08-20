# Plan: 봉사료 포함 정산에서 나누어떨어지지 않는 나머지가 유실되는 문제 수정

- run-id: `RUN-20260820-1443-HARNESS-EVAL-002`
- 대상 Task: `evals/fixtures/HARNESS-EVAL-002.md`
- 계획 차수: 최초 계획 (재계획 아님)

## 1. 요구사항 요약

`split_service_charge(bill, people, charge_percent, unit)` 가 반환하는 1인당 부담액 목록의 합계가
**봉사료를 더한 뒤 정산 단위로 올림한 총액** 과 항상 같아야 한다.

만족해야 할 계약은 다음과 같다.

- `sum(결과) == round_to_unit(bill + bill * charge_percent // 100, unit)`
- `len(결과) == people`
- `max(결과) - min(결과) <= 1`
- 나누어떨어지지 않아 생기는 1원 단위 차이는 **앞 사람부터** 배분한다.
- 기존 입력값 검증 동작(`people` < 1, `bill` < 0, `charge_percent` < 0, `unit` < 1 → `ValueError`)은 그대로 유지한다.
- 봉사료 계산(내림, 1원 미만 미청구)과 정산 단위 올림 규칙은 현재 동작을 그대로 유지한다.
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의 동작에는 영향을 주지 않는다.

## 2. 재현 조건

봉사료를 더해 정산 단위로 올림한 **총액이 `people` 로 나누어떨어지지 않는** 모든 호출.

```python
from expense.service_charge import split_service_charge

split_service_charge(10000, 3, 10, 1)    # 총액 11000, 3으로 나누어떨어지지 않음
split_service_charge(10050, 3, 0, 100)   # 총액 10100, 3으로 나누어떨어지지 않음
```

총액이 정확히 나누어떨어지는 경우(`split_service_charge(9000, 3, 10, 100)`)와
인원이 1명인 경우(`split_service_charge(10000, 1, 10, 100)`)에는 재현되지 않는다.

## 3. 기대 동작

| 입력 | 총액 | 기대 결과 | 기대 합계 |
| --- | --- | --- | --- |
| `(10000, 3, 10, 1)` | 11000 | `[3667, 3667, 3666]` | 11000 |
| `(10050, 3, 0, 100)` | 10100 | `[3367, 3367, 3366]` | 10100 |
| `(10000, 3, 0, 1)` | 10000 | `[3334, 3333, 3333]` | 10000 |
| `(9000, 3, 10, 100)` | 9900 | `[3300, 3300, 3300]` | 9900 |
| `(10000, 1, 10, 100)` | 11000 | `[11000]` | 11000 |
| `(0, 3, 10, 100)` | 0 | `[0, 0, 0]` | 0 |
| `(9, 3, 10, 1)` | 9 | 합계 9 | 9 |

## 4. 현재 동작

- `split_service_charge(10000, 3, 10, 1)` → `[3666, 3666, 3666]` (합계 10998, 총액 11000 대비 2원 부족)
- `split_service_charge(10050, 3, 0, 100)` → `[3366, 3366, 3366]` (합계 10098, 총액 10100 대비 2원 부족)
- 총액이 나누어떨어지는 경우와 인원 1명인 경우에는 정상 동작한다.

유실 금액은 항상 `총액 % people` 이며, 인원이 많을수록 커진다.

## 5. 예상 원인

봉사료 계산과 정산 단위 올림까지는 정상이며, **올림된 총액을 인원수로 나누는 마지막 단계에서
정수 나눗셈의 나머지를 아무에게도 배분하지 않고 버리기 때문**이다.

각 사람에게 몫(`total // people`)만 동일하게 배정하고 나머지(`total % people`)를 처리하는 로직이
아예 존재하지 않는다. 그 결과 합계 보존 불변식(`sum(결과) == total`)이 깨진다.

같은 저장소의 다른 분배 함수들은 이미 이 나머지를 배분하는 규칙을 갖고 있는데,
`split_service_charge` 만 그 규칙이 빠져 있다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/service_charge.py:31` — `return [total // people] * people`.
  몫만 `people` 번 복제해 반환하고 `total % people` 를 처리하는 코드가 없다.
  `total = 11000, people = 3` 이면 `3666 * 3 = 10998` 이 되어 나머지 2원이 결과에서 사라진다.
  이 한 줄이 합계 유실의 직접적인 원인이다.
- `sample-project/src/expense/service_charge.py:29-30` — 봉사료는 `bill * charge_percent // 100`(내림),
  총액은 `round_to_unit(bill + service_charge, unit)` 로 계산한다.
  Task의 "총액 10,100원은 올바르게 계산된다"는 서술과 일치하므로 이 두 줄은 원인이 아니다.
- `sample-project/src/expense/charge_rounding.py:16-24` — `round_to_unit` 은 `amount < 0`, `unit <= 0` 을 검증한 뒤
  나머지가 있으면 올림한다. 올림 규칙 자체는 계약대로 동작하며, `test_charge_rounding.py` 도 현재 통과 중이다.
  따라서 올림 로직은 이번 수정 대상이 아니다.
- `sample-project/src/expense/service_charge.py:22-27` — `people`, `bill`, `charge_percent` 만 직접 검증하고
  `unit` 은 검증하지 않는다. `unit` 이 1 미만인 경우의 `ValueError` 는 `round_to_unit` 호출(`:30`)을 통해 발생한다.
  즉 `test_split_service_charge_raises_value_error_when_unit_is_zero` 는 `round_to_unit` 에 의존해 통과하고 있으므로,
  총액 계산 순서를 바꾸면 이 검증이 깨질 수 있다.
- `sample-project/src/expense/splitter.py:21-28` — `split_amount` 는 몫을 계산한 뒤
  나머지를 앞 사람부터 1원씩 배분해 합계를 보존하고 사람 간 차이를 최대 1원으로 유지한다.
  이번 요구사항의 분배 규칙과 계약이 동일하다.
- `sample-project/src/expense/reconciliation.py:3,29` — `reconcile_payments` 가 이미 `expense.splitter.split_amount` 를
  import 해 사용한다. 모듈 간 공용 분배 함수 재사용이 이 프로젝트의 기존 스타일임을 보여준다.
- `sample-project/src/expense/allocation.py:13-21` — `allocate_units` 도 동일한 "앞 사람부터 1개씩" 규칙을 사용한다.
  단, 개수 단위 배분이며 입력값 검증이 없다는 점에서 계약이 다르다.
- `sample-project/tests/test_service_charge.py:6-69` — 합계 보존, 앞 사람 우선 배분, 목록 길이,
  최대 1원 차이, 네 가지 입력값 검증을 모두 검증하는 테스트가 이미 존재한다.
  회귀 테스트를 새로 만들 필요는 없고, 이 테스트들이 통과하도록 제품 코드를 고치면 된다.
- Grep 결과 `split_service_charge` 를 호출하는 제품 코드는 없다(`sample-project/tests/test_service_charge.py` 에서만 호출).
  따라서 이 함수 수정의 영향 범위는 자기 자신과 그 테스트로 한정된다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/service_charge.py`

이 파일 외에는 어떤 파일도 수정하지 않는다.
특히 `charge_rounding.py`, `splitter.py`, `allocation.py` 는 현재 계약대로 동작하고 있으므로 변경 대상이 아니며,
`sample-project/tests/` 하위 파일은 Developer의 수정 대상이 아니다.

## 8. 구현 단계

1. `service_charge.py:31` 의 반환 로직을 "몫만 복제"에서 "나머지까지 배분"으로 바꾼다.
   — 합계 보존 불변식(`sum(결과) == total`)을 만족시키는 것이 이 단계의 유일한 목적이다.
   나머지 `total % people` 원을 앞 사람부터 1원씩 더 부담하게 만들어야 하며,
   결과 목록의 길이는 `people` 을 유지하고 사람 간 차이는 최대 1원을 넘지 않아야 한다.

2. 나머지 배분 로직을 새로 작성하기 전에, 동일한 계약을 이미 만족하는 공용 함수
   `expense.splitter.split_amount`(`sample-project/src/expense/splitter.py:4`)를 재사용할 수 있는지 먼저 검토한다.
   — 중복 로직을 새로 만들지 않기 위한 단계다(`CLAUDE.md §9`, `§17`).
   재사용을 선택한다면 그 함수의 입력값 검증(`people` < 1, `amount` < 0)이
   기존 `split_service_charge` 의 예외 계약과 충돌하지 않는지 확인한다.
   재사용이 부적절하다고 판단하면 그 이유를 `change-log-1.md` 에 근거와 함께 남기고 직접 구현한다.

3. 봉사료 계산(`:29`)과 총액 올림(`:30`)은 변경하지 않는다.
   — Task 문서와 `test_charge_rounding.py` 의 통과 상태로 이 두 단계가 정상임이 확인되었으므로,
   변경 범위를 최소로 유지하기 위한 단계다.

4. 입력값 검증 4종이 수정 후에도 모두 `ValueError` 를 발생시키는지 확인한다.
   — `unit` 검증만 `round_to_unit` 호출에 간접적으로 의존하고 있어(`§6` 참조),
   호출 순서나 총액 계산 위치가 바뀌면 조용히 깨질 수 있다. 이 리스크를 차단하는 것이 목적이다.

5. 변경된 동작이 docstring(`:7-21`)의 서술과 일치하는지 확인하고,
   코드만 보고 알기 어려운 배분 의도가 있다면 `CLAUDE.md §5` 기준으로 이유를 남긴다.
   — docstring은 이미 "합계는 총액과 항상 같아야 한다"고 명시하고 있으므로 문구 자체는 수정할 필요가 없을 가능성이 높다.
   불필요한 문구 변경으로 diff를 키우지 않는다.

> 구현 방법(코드)은 Developer가 위 파일들을 직접 읽고 결정한다. 이 계획에는 만족해야 할 조건만 기술한다.

## 9. 검증 방법

- 실행 명령: `uv run pytest sample-project/tests -q`

통과 판정 기준:

1. `sample-project/tests/test_service_charge.py` 의 15개 테스트가 모두 통과한다.
   특히 다음 5개가 현재 실패 중이며 반드시 통과해야 한다.
   - `test_split_service_charge_preserves_total_when_total_is_not_evenly_divisible`
   - `test_split_service_charge_distributes_remainder_to_earlier_people_first`
   - `test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit`
   - `test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit`
   - `test_split_service_charge_splits_bill_only_when_charge_percent_is_zero`
2. `sample-project/tests/test_charge_rounding.py` 의 계약 테스트가 계속 통과한다.
3. `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`,
   `test_formatter.py` 등 기존에 통과하던 테스트가 하나도 깨지지 않는다.
4. 실패 0건이어야 하며, 특정 테스트 하나만 통과한 상태는 완료로 보지 않는다(`CLAUDE.md §10`).
5. 테스트를 약화시키거나 기대값을 바꾸는 방식의 통과는 인정하지 않는다(`CLAUDE.md §3-3`).

## 10. 예상 위험 요소

- **입력값 검증 순서 붕괴 (중간)**: `unit` 검증은 `round_to_unit` 호출에 의존한다.
  총액 계산보다 분배 로직을 먼저 수행하거나 호출 순서를 바꾸면
  `test_split_service_charge_raises_value_error_when_unit_is_zero` 가 깨질 수 있다.
- **예외 메시지/타입 변경 (낮음)**: 공용 분배 함수를 재사용할 경우 `people <= 0` 예외가
  다른 함수에서 발생하게 된다. 타입은 동일한 `ValueError` 이므로 테스트는 통과하지만,
  기존 메시지 문구가 바뀌지 않도록 주의해야 한다(`CLAUDE.md §3-10`).
- **경계값 회귀 (낮음)**: `bill = 0`(총액 0), `people = 1`, 봉사료가 1원 미만이라 0으로 내림되는 경우
  (`(9, 3, 10, 1)`)에서 나머지 배분 로직이 예외를 던지거나 길이가 달라지면 안 된다.
- **범위 초과 변경 (중간)**: `charge_rounding.py` 나 `splitter.py` 를 함께 손대면
  `test_charge_rounding.py`, `test_splitter.py`, `reconciliation.py` 까지 회귀 위험이 번진다.
  수정은 `service_charge.py` 한 파일로 제한한다.
- **불필요한 리팩터링 (낮음)**: docstring 전면 재작성, 타입 힌트 일괄 변경, 포맷팅 등은
  요구사항 범위를 벗어나며 Reviewer의 `git diff` 검토에서 불필요한 변경으로 지적된다(`CLAUDE.md §15`, `§17`).
- **영향 범위 자체는 좁음**: `split_service_charge` 를 호출하는 제품 코드가 없으므로,
  위 제약만 지키면 다른 모듈로의 회귀 전파 가능성은 낮다.
