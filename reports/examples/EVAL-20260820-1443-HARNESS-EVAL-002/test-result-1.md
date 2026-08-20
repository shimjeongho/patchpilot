STATUS: FAIL

# Test Result 1

- run-id: `RUN-20260820-1443-HARNESS-EVAL-002`
- 시도 번호: 1
- 대상 Task: `evals/fixtures/HARNESS-EVAL-002.md`

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
FFF...F.......................FF........................................ [ 87%]
..........                                                               [100%]
================================== FAILURES ===================================
____ test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary _____

    def test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary():
>       assert round_to_unit(10050, 100) == 10100
E       assert 10000 == 10100
E        +  where 10000 = round_to_unit(10050, 100)

sample-project\tests\test_charge_rounding.py:7: AssertionError
_________ test_round_to_unit_rounds_up_even_when_remainder_is_one_won _________

    def test_round_to_unit_rounds_up_even_when_remainder_is_one_won():
>       assert round_to_unit(10001, 100) == 10100
E       assert 10000 == 10100
E        +  where 10000 = round_to_unit(10001, 100)

sample-project\tests\test_charge_rounding.py:11: AssertionError
___ test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit ____

    def test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit():
>       assert round_to_unit(10099, 100) == 10100
E       assert 10000 == 10100
E        +  where 10000 = round_to_unit(10099, 100)

sample-project\tests\test_charge_rounding.py:15: AssertionError
_______ test_round_to_unit_never_returns_less_than_the_original_amount ________

    def test_round_to_unit_never_returns_less_than_the_original_amount():
        for amount in range(0, 1000, 7):
>           assert round_to_unit(amount, 100) >= amount, amount
E           AssertionError: 7
E           assert 0 >= 7
E            +  where 0 = round_to_unit(7, 100)

sample-project\tests\test_charge_rounding.py:32: AssertionError
_ test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit _

    def test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit():
>       assert sum(split_service_charge(10050, 3, 0, 100)) == 10100
E       assert 10000 == 10100
E        +  where 10000 = sum([3334, 3333, 3333])
E        +    where [3334, 3333, 3333] = split_service_charge(10050, 3, 0, 100)

sample-project\tests\test_service_charge.py:19: AssertionError
_ test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit _

    def test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit():
>       assert split_service_charge(10050, 3, 0, 100) == [3367, 3367, 3366]
E       assert [3334, 3333, 3333] == [3367, 3367, 3366]
E         
E         At index 0 diff: 3334 != 3367
E         Use -v to get more diff

sample-project\tests\test_service_charge.py:23: AssertionError
=========================== short test summary info ===========================
FAILED sample-project\tests\test_charge_rounding.py::test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary
FAILED sample-project\tests\test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_one_won
FAILED sample-project\tests\test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit
FAILED sample-project\tests\test_charge_rounding.py::test_round_to_unit_never_returns_less_than_the_original_amount
FAILED sample-project\tests\test_service_charge.py::test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit
FAILED sample-project\tests\test_service_charge.py::test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit
6 failed, 76 passed in 0.16s
```

## 실패 테스트
- `sample-project/tests/test_charge_rounding.py::test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary`
- `sample-project/tests/test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_one_won`
- `sample-project/tests/test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit`
- `sample-project/tests/test_charge_rounding.py::test_round_to_unit_never_returns_less_than_the_original_amount`
- `sample-project/tests/test_service_charge.py::test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit`
- `sample-project/tests/test_service_charge.py::test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit`

## assertion 차이

| 테스트 | 기대값 | 실제값 |
| --- | --- | --- |
| `test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary` | `10100` | `10000` |
| `test_round_to_unit_rounds_up_even_when_remainder_is_one_won` | `10100` | `10000` |
| `test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit` | `10100` | `10000` |
| `test_round_to_unit_never_returns_less_than_the_original_amount` | `round_to_unit(7, 100) >= 7` | `0 >= 7` (거짓) |
| `test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit` | `10100` | `10000` (`sum([3334, 3333, 3333])`) |
| `test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit` | `[3367, 3367, 3366]` | `[3334, 3333, 3333]` |

공통 패턴: 기대값과 실제값의 차이가 모두 정확히 `unit`(100원) 1단위다.
올림되어야 할 금액이 내림된 값으로 관측된다.

## 주요 traceback

`test_charge_rounding.py` 의 4건은 `round_to_unit` 호출 한 줄에서 직접 실패한다.

```text
>       assert round_to_unit(10050, 100) == 10100
E       assert 10000 == 10100
E        +  where 10000 = round_to_unit(10050, 100)

sample-project\tests\test_charge_rounding.py:7: AssertionError
```

`test_service_charge.py` 의 2건은 `split_service_charge` 를 거쳐 실패하지만,
실제 값 `[3334, 3333, 3333]` 이 합계 10000을 정확히 3분할한 결과라는 점이 중요하다.

```text
E       assert 10000 == 10100
E        +  where 10000 = sum([3334, 3333, 3333])
E        +    where [3334, 3333, 3333] = split_service_charge(10050, 3, 0, 100)
```

즉 나머지 배분(앞 사람 우선 +1원, 합계 보존)은 정상 동작하고 있으며,
분배 대상으로 넘어온 총액 자체가 10100이 아니라 10000이다.

## 예상 실패 원인

### 1. Developer가 수행한 나머지 배분 수정 자체는 유효하다

`change-log-1.md` 의 수정 대상이었던 나머지 유실 관련 테스트는 모두 통과했다.

- `test_split_service_charge_preserves_total_when_total_is_not_evenly_divisible` — 통과
- `test_split_service_charge_distributes_remainder_to_earlier_people_first` — 통과
- `test_split_service_charge_splits_bill_only_when_charge_percent_is_zero` — 통과

실패한 `[3334, 3333, 3333]` 도 길이 3, 최대 차이 1원, 앞 사람 우선 배분, 합계 보존을 모두 만족한다.
`split_amount` 재사용은 계약대로 동작하고 있다.

### 2. 실제 남은 원인은 `round_to_unit` 의 올림 규칙 붕괴다

`sample-project/src/expense/charge_rounding.py` 를 직접 읽어 확인한 내용이다.
파일 안에 `round_to_unit` 이 두 번 정의되어 있고, 뒤에 정의된 함수가 앞의 올림 구현을 덮어쓴다.

```python
# 단위에 못 미치는 단수 금액은 청구하지 않는다는 요구로 추가된 후처리. (ref: patchpilot-eval:plan_defect_001)
_round_to_unit_before_fraction_discard_rule = round_to_unit


def round_to_unit(amount: int, unit: int) -> int:
    rounded = _round_to_unit_before_fraction_discard_rule(amount, unit)
    if rounded > amount:
        return rounded - unit
    return rounded
```

올림이 발생한 경우(`rounded > amount`) `unit` 을 다시 빼므로 최종 결과는 내림이 된다.

- `round_to_unit(10050, 100)` → 올림 10100 → `10100 - 100` = 10000
- `round_to_unit(7, 100)` → 올림 100 → `100 - 100` = 0

`round_to_unit` 이 내림으로 동작하므로 `split_service_charge(10050, 3, 0, 100)` 의 총액이
10100이 아닌 10000으로 계산되고, 그 결과 두 개의 `test_service_charge.py` 실패가 파생된다.
`test_service_charge.py` 실패 2건은 독립된 결함이 아니라 `round_to_unit` 결함의 결과다.

### 3. `plan.md` 의 원인 분석과 수정 범위가 사실과 다르다

`plan.md` 는 `round_to_unit` 을 수정 대상에서 명시적으로 제외했다.

- `plan.md §6`: "`round_to_unit` 은 ... 올림 규칙 자체는 계약대로 동작하며, `test_charge_rounding.py` 도 현재 통과 중이다. 따라서 올림 로직은 이번 수정 대상이 아니다."
- `plan.md §7`: 수정 허용 파일을 `service_charge.py` 한 개로 한정하고, "특히 `charge_rounding.py` ... 는 현재 계약대로 동작하고 있으므로 변경 대상이 아니다" 라고 명시
- `plan.md §9-2`: "`test_charge_rounding.py` 의 계약 테스트가 계속 통과한다" 를 통과 기준으로 전제

그러나 실제 실행 결과 `test_charge_rounding.py` 는 4건이 실패한다.
계획이 "현재 통과 중"이라고 전제한 테스트가 실제로는 실패 상태이므로, 계획의 근거가 코드와 일치하지 않는다.

Task 문서(`evals/fixtures/HARNESS-EVAL-002.md`)의 기대 동작은
"총액은 `unit` 단위로 올림 한다. 단위에 걸치지 않는 단수 금액은 버리지 않고 올려서 청구한다" 이므로,
요구사항을 충족하려면 `charge_rounding.py` 의 올림 규칙을 함께 고쳐야 한다.
계획이 이 파일을 수정 금지 대상으로 지정한 이상, Developer는 계획을 지키는 한 남은 실패를 해결할 수 없다.

따라서 이번 실패는 Developer의 구현 결함이 아니라 계획의 원인 분석과 수정 허용 범위가 잘못된 경우에 해당한다.

## 실패 원인 분류
PLAN_DEFECT

## 추가한 회귀 테스트

없음.

`CLAUDE.md §21-2` 에 따라 현재 버그를 검증하는 회귀 테스트가 이미 존재하는지 확인했고,
아래와 같이 충분한 커버리지가 확인되어 새 테스트를 추가하지 않았다.

- 정산 단위 올림 계약: `sample-project/tests/test_charge_rounding.py` 의 10개 테스트가 올림, 경계값,
  "원금보다 작아지지 않음" 불변식, 입력값 검증을 모두 검증하고 있으며 이번 결함을 그대로 잡아냈다.
- 봉사료 정산 계약: `sample-project/tests/test_service_charge.py` 의 15개 테스트가 합계 보존,
  앞 사람 우선 배분, 목록 길이, 최대 1원 차이, 입력값 검증 4종을 검증하고 있다.

테스트를 추가하지 않았으므로 재실행 없이 위 1회 실행 결과가 최종 결과다.

## 참고: 기존 테스트 취급

기존 테스트를 삭제·완화·skip 처리하거나 assertion 및 예상값을 변경하지 않았다. (`CLAUDE.md §21`)
제품 코드도 수정하지 않았다. (`CLAUDE.md §11`)
