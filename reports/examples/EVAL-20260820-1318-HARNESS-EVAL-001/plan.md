# Plan: 팁 포함 정산(`split_tip`)에서 1인당 부담액 합계가 총액보다 작아지는 문제 수정

## 1. 요구사항 요약

`split_tip(bill, people, tip_percent)` 가 반환하는 1인당 부담액 목록의 합계가 팁을 포함한 총액과 항상 일치해야 한다.

만족해야 할 조건:

- `sum(split_tip(bill, people, tip_percent)) == bill + bill * tip_percent // 100`
- 팁은 **청구 금액 전체**에 `tip_percent` 를 적용해 내림으로 계산한다. 1원 미만 팁은 청구하지 않는다.
- `len(split_tip(...)) == people`
- 사람 간 부담액 차이는 최대 1원이다.
- 나누어떨어지지 않아 생기는 1원 단위 차이는 **앞 사람부터** 배분한다.
- 기존 입력값 검증 동작 유지: `people < 1`, `bill < 0`, `tip_percent < 0` 인 경우 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의 동작에 영향을 주지 않는다.

## 2. 재현 조건

`sample-project` 를 `pythonpath = src` 로 두고 다음을 실행한다.

```python
from expense.tip import split_tip

split_tip(10000, 3, 10)  # 총액 11000
split_tip(10000, 3, 0)   # 총액 10000
```

- 총액(`bill + 팁`)이 `people` 로 나누어떨어지지 않는 모든 입력에서 재현된다.
- `people == 1` 이거나 총액이 정확히 나누어떨어지는 경우에는 재현되지 않는다.

## 3. 기대 동작

| 입력 | 기대 반환값 | 기대 합계 |
| --- | --- | --- |
| `split_tip(10000, 3, 10)` | `[3667, 3667, 3666]` | 11000 |
| `split_tip(10000, 3, 0)` | `[3334, 3333, 3333]` | 10000 |
| `split_tip(9000, 3, 10)` | `[3300, 3300, 3300]` | 9900 |
| `split_tip(10000, 1, 10)` | `[11000]` | 11000 |
| `split_tip(0, 3, 10)` | `[0, 0, 0]` | 0 |
| `split_tip(9, 3, 10)` | 합계 `9` (팁 `9 * 10 // 100 == 0`) | 9 |
| `split_tip(10000, 4, 15)` | 길이 4, 합계 11500 | 11500 |

불변식:

- 합계 보존: 반환값의 합 == `bill + bill * tip_percent // 100`
- 길이 보존: 반환값의 길이 == `people`
- 공평성: `max(shares) - min(shares) <= 1`
- 배분 순서: 1원 잔여분은 인덱스가 작은 사람부터 받는다.

## 4. 현재 동작

- `split_tip(10000, 3, 10)` → `[3666, 3666, 3666]` (합계 10998, **2원 유실**)
- `split_tip(10000, 3, 0)` → `[3333, 3333, 3333]` (합계 9999, **1원 유실**)
- `split_tip(9000, 3, 10)` → `[3300, 3300, 3300]` (합계 9900, 정상)
- `split_tip(10000, 1, 10)` → `[11000]` (정상)
- 입력값 검증(`ValueError`) 은 현재도 정상 동작한다.

## 5. 예상 원인

현재 구현은 **총액을 먼저 만들고 나누는 것이 아니라, 나눈 뒤에 팁을 계산**한다. 그 결과 내림(`//`)이 두 번 발생하고, 두 번 모두 버려진 나머지를 아무도 부담하지 않는다.

1. **청구 금액 분배 시 나머지 유실**
   `bill // people` 로 계산한 1인당 금액을 그대로 `people` 번 복제하므로 `bill % people` 만큼의 금액이 사라진다. (`10000 // 3 == 3333` → 3333 × 3 = 9999, 1원 유실)

2. **팁 계산 기준이 잘못됨 + 팁 나머지 유실**
   팁을 `bill` 전체가 아니라 **1인당 금액(`bill_share`)** 에 적용한 뒤 다시 내림한다. 요구사항은 팁을 `bill * tip_percent // 100` 으로 청구 금액 전체 기준으로 한 번만 내림해 계산하는 것이다. 현재는 `(bill // people) * tip_percent // 100` 을 다시 `people` 배 하므로, 기대 팁(1000원)보다 작은 999원만 청구되어 추가로 1원이 유실된다.

이 두 유실이 합쳐져 `split_tip(10000, 3, 10)` 에서 2원 차이가 발생한다. 총액이 `people` 로 나누어떨어질 때만 우연히 결과가 일치한다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/tip.py:25` — `bill_share = bill // people`. 청구 금액을 먼저 내림으로 나눈다. `bill % people` 에 해당하는 나머지를 보관하거나 배분하는 코드가 이후에 없다.
- `sample-project/src/expense/tip.py:26` — `tip_share = bill_share * tip_percent // 100`. 팁의 기준이 `bill` 이 아니라 이미 내림된 1인당 금액이다. Docstring(`tip.py:7`)과 요구사항이 명시한 "청구 금액에 tip_percent를 적용" 과 어긋난다.
- `sample-project/src/expense/tip.py:27` — `return [bill_share + tip_share] * people`. 동일한 값을 단순 복제하므로 구조적으로 1원 단위 잔여분을 배분할 수단이 없다. 합계는 항상 `people` 의 배수가 되어, 총액이 나누어떨어지지 않으면 반드시 유실이 생긴다.
- `sample-project/src/expense/tip.py:18-23` — `people`/`bill`/`tip_percent` 검증 블록. 요구사항상 유지 대상이며, 이번 수정에서 건드릴 필요가 없는 부분이다.
- `sample-project/src/expense/splitter.py:4-28` — `split_amount(amount, people)`. 이미 "나머지를 앞 사람부터 1원씩 배분해 합계를 보존" 하는 동작과 동일한 검증(`people <= 0`, `amount < 0`)을 갖춘 기존 공용 함수다. 이번 요구사항의 배분 규칙과 정확히 같은 규칙을 구현하고 있어 재사용 후보다. 이 모듈은 외부 import가 없어 순환 import 위험도 없다.
- `sample-project/src/expense/settlement.py:3,28` — `settle_by_unit` 이 `expense.allocation.allocate_units` 를 import해 배분 로직을 재사용한다. 이 프로젝트는 배분 규칙을 각 모듈에서 중복 구현하지 않고 공용 함수를 가져다 쓰는 스타일임을 확인했다.
- `sample-project/tests/test_tip.py:11` — `split_tip(10000, 3, 10) == [3667, 3667, 3666]` 를 요구한다. 잔여분이 앞 사람부터 배분되어야 함이 테스트로 고정되어 있다.
- `sample-project/tests/test_tip.py:28` — `split_tip(10000, 3, 0) == [3334, 3333, 3333]` 로, 팁이 0일 때도 동일한 배분 규칙이 적용되어야 한다.
- `sample-project/tests/test_tip.py:41` — `sum(split_tip(9, 3, 10)) == 9`. 팁을 `bill` 전체 기준으로 내림하면 `9 * 10 // 100 == 0` 이 되어 1원 미만 팁을 청구하지 않는다는 요구사항과 일치한다.
- `sample-project/tests/test_tip.py:59-70` — 여러 입력에 대해 `sum(shares) == bill + bill * tip_percent // 100` 을 검증한다. 총액 산식이 "청구 금액 전체에 팁률 적용 후 내림" 임을 확정하는 근거다.
- `sample-project/pytest.ini:1-3` — `pythonpath = src`, `testpaths = tests`. `sample-project/tests` 를 대상으로 한 고정 테스트 명령이 그대로 동작한다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/tip.py`

이 외의 파일은 수정하지 않는다. 특히 `splitter.py`, `allocation.py`, `settlement.py`, `weighted_splitter.py`, `reconciliation.py`, `formatter.py` 는 이번 요구사항의 영향 범위 밖이며 기존 동작을 그대로 유지해야 한다. 테스트 파일(`sample-project/tests/`)도 수정 대상이 아니다.

## 8. 구현 단계

1. **팁 계산 기준을 1인당 금액에서 청구 금액 전체로 바꾼다** — 현재 `tip.py:26` 은 이미 내림된 1인당 금액에 팁률을 적용해 팁 자체가 요구 금액보다 작아진다. 팁은 `bill` 전체에 `tip_percent` 를 적용해 한 번만 내림한 값이어야 하며, 1원 미만은 청구하지 않는다는 규칙을 만족해야 한다. 이 단계의 목적은 **청구해야 할 총액을 정확히 확정하는 것**이다.

2. **"총액을 확정한 뒤 인원수로 배분" 하는 순서로 계산 흐름을 바꾼다** — 현재는 나눈 뒤 팁을 붙이는 순서라 내림이 두 번 일어난다. 청구 금액과 팁을 합한 총액을 먼저 만들고, 그 총액 하나를 인원수에 맞게 나누는 흐름이 되어야 한다. 이 단계의 목적은 **내림 발생 지점을 총액 계산 1회로 줄여 유실 원인을 제거하는 것**이다.

3. **동일 값 복제 대신, 나머지를 앞 사람부터 배분하는 방식으로 반환값을 만든다** — `tip.py:27` 의 `[x] * people` 구조로는 합계가 항상 `people` 의 배수가 되어 잔여분 배분이 불가능하다. 반환 목록은 길이가 `people` 이고, 합계가 총액과 같으며, 사람 간 차이가 최대 1원이고, 잔여 1원은 인덱스가 작은 사람부터 받아야 한다.
   이때 `sample-project/src/expense/splitter.py` 의 `split_amount` 가 이미 같은 배분 규칙을 구현하고 있고, `settlement.py` 가 `allocation.py` 를 재사용하는 것처럼 이 프로젝트는 공용 배분 함수를 재사용하는 스타일이다. Developer는 해당 함수를 읽고 **재사용이 적절한지, 재사용 시 인자 계약과 검증 동작이 요구사항과 충돌하지 않는지** 직접 확인해 판단한다. 중복 구현을 새로 만드는 선택을 한다면 그 이유를 `change-log-N.md` 에 남긴다. 이 단계의 목적은 **합계 보존과 배분 순서 요구사항을 동시에 만족시키는 것**이다.

4. **기존 입력값 검증 블록(`tip.py:18-23`)과 그 순서를 그대로 유지한다** — `people`, `bill`, `tip_percent` 순으로 검증하고 각각 `ValueError` 를 던지는 현재 동작은 요구사항상 유지 대상이다. 특히 `tip_percent < 0` 검증은 총액 계산 이전에 수행되어야 한다(음수 팁률이 검증을 통과하면 총액이 청구 금액보다 작아지는 잘못된 결과가 나온다). 이 단계의 목적은 **수정 과정에서 기존 계약이 훼손되지 않게 하는 것**이다.

5. **Docstring과 주석을 실제 동작과 일치시킨다** — 팁 계산 기준과 잔여분 배분 규칙이 코드만 보고 자명하지 않다면 `CLAUDE.md §5` 에 따라 "왜" 를 남긴다. 이미 정확히 설명하고 있는 문장을 불필요하게 다시 쓰지 않는다. 이 단계의 목적은 **문서와 구현의 불일치 제거**이며, 범위를 벗어난 리팩터링은 하지 않는다.

## 9. 검증 방법

- 실행 명령:

```bash
uv run pytest sample-project/tests -q
```

- 통과 판정 기준:
  - `sample-project/tests/test_tip.py` 의 13개 테스트가 모두 통과한다.
  - 특히 다음이 통과해야 한다.
    - `test_split_tip_preserves_total_when_total_is_not_evenly_divisible`
    - `test_split_tip_distributes_remainder_to_earlier_people_first`
    - `test_split_tip_splits_bill_only_when_tip_percent_is_zero`
    - `test_split_tip_discards_fractional_tip_below_one_won`
    - `test_split_tip_preserves_total_for_various_bills_and_people`
  - `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`, `test_formatter.py` 를 포함한 **기존 테스트가 하나도 깨지지 않는다.**
  - 실패/에러 0건이어야 한다. 특정 테스트 하나만 통과한 상태는 완료로 보지 않는다. (`CLAUDE.md §10`)

## 10. 예상 위험 요소

- **팁 계산 기준 변경에 따른 결과값 변화**: 팁 기준을 `bill` 전체로 바꾸면 총액 자체가 기존보다 커지는 입력이 있다. 이는 요구사항이 명시한 의도된 변경이지만, `split_tip` 결과를 사용하는 다른 코드가 있다면 영향을 받는다. → `expense` 패키지 내 다른 모듈은 `tip.py` 를 import하지 않는 것으로 확인했으므로 영향 범위는 `split_tip` 호출자에 한정된다.
- **공용 함수 재사용 시 부작용**: `splitter.py` 의 `split_amount` 를 재사용하는 경우, 예외 메시지가 `amount` 기준으로 나올 수 있다. 다만 `tip.py` 의 자체 검증이 먼저 수행되므로 정상 경로에서는 `split_amount` 의 검증에 걸리지 않아야 한다. Developer는 `bill`/`tip_percent` 가 유효할 때 총액이 항상 0 이상임을 확인해야 한다.
- **공용 함수 수정 유혹**: 요구사항을 맞추기 위해 `splitter.py` 나 `allocation.py` 를 수정하면 다른 테스트에 회귀가 발생한다. 수정 허용 파일은 `tip.py` 하나뿐이다. (`CLAUDE.md §3-2`, `§17`)
- **경계값 처리**: `bill == 0`, `people == 1`, 총액이 `people` 미만인 경우(예: `split_tip(9, 3, 10)`) 등에서 잔여분 배분 로직이 음수 몫이나 길이 불일치를 만들지 않는지 확인이 필요하다.
- **테스트 약화 금지**: 결과가 기대와 다를 때 테스트의 기대값을 바꾸는 것은 금지된다. (`CLAUDE.md §3-3`)
- **범위 초과 리팩터링**: 이번 작업은 `split_tip` 한 함수의 계산 순서와 배분 방식 수정에 한정한다. 다른 모듈로의 공통화나 시그니처 변경은 하지 않는다.
