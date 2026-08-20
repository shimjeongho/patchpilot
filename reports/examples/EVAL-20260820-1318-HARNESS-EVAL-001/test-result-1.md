STATUS: FAIL

# Test Result 1

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
............................................FFF.FFF.F...F.............   [100%]
================================== FAILURES ===================================
______ test_split_tip_preserves_total_when_total_is_not_evenly_divisible ______

    def test_split_tip_preserves_total_when_total_is_not_evenly_divisible():
>       assert sum(split_tip(10000, 3, 10)) == 11000
E       assert 7334 == 11000
E        +  where 7334 = sum([3667, 3667, 0])
E        +    where [3667, 3667, 0] = split_tip(10000, 3, 10)

sample-project\tests\test_tip.py:7: AssertionError
________ test_split_tip_distributes_remainder_to_earlier_people_first _________

    def test_split_tip_distributes_remainder_to_earlier_people_first():
>       assert split_tip(10000, 3, 10) == [3667, 3667, 3666]
E       assert [3667, 3667, 0] == [3667, 3667, 3666]
E
E         At index 2 diff: 0 != 3666
E         Use -v to get more diff

sample-project\tests\test_tip.py:11: AssertionError
_____ test_split_tip_returns_equal_shares_when_total_is_evenly_divisible ______

    def test_split_tip_returns_equal_shares_when_total_is_evenly_divisible():
>       assert split_tip(9000, 3, 10) == [3300, 3300, 3300]
E       assert [3300, 3300, 0] == [3300, 3300, 3300]
E
E         At index 2 diff: 0 != 3300
E         Use -v to get more diff

sample-project\tests\test_tip.py:15: AssertionError
_________ test_split_tip_difference_between_people_is_at_most_one_won _________

    def test_split_tip_difference_between_people_is_at_most_one_won():
        shares = split_tip(10000, 3, 10)
>       assert max(shares) - min(shares) <= 1
E       assert (3667 - 0) <= 1
E        +  where 3667 = max([3667, 3667, 0])
E        +  and   0 = min([3667, 3667, 0])

sample-project\tests\test_tip.py:24: AssertionError
__________ test_split_tip_splits_bill_only_when_tip_percent_is_zero ___________

    def test_split_tip_splits_bill_only_when_tip_percent_is_zero():
>       assert split_tip(10000, 3, 0) == [3334, 3333, 3333]
E       assert [3334, 3333, 0] == [3334, 3333, 3333]
E
E         At index 2 diff: 0 != 3333
E         Use -v to get more diff

sample-project\tests\test_tip.py:28: AssertionError
_____________ test_split_tip_gives_entire_total_to_single_person ______________

    def test_split_tip_gives_entire_total_to_single_person():
>       assert split_tip(10000, 1, 10) == [11000]
E       assert [0] == [11000]
E
E         At index 0 diff: 0 != 11000
E         Use -v to get more diff

sample-project\tests\test_tip.py:32: AssertionError
____________ test_split_tip_discards_fractional_tip_below_one_won _____________

    def test_split_tip_discards_fractional_tip_below_one_won():
        # ���� �������� ����ϹǷ� 1�� �̸��� û������ �ʴ´�.
>       assert sum(split_tip(9, 3, 10)) == 9
E       assert 6 == 9
E        +  where 6 = sum([3, 3, 0])
E        +    where [3, 3, 0] = split_tip(9, 3, 10)

sample-project\tests\test_tip.py:41: AssertionError
_________ test_split_tip_preserves_total_for_various_bills_and_people _________

    def test_split_tip_preserves_total_for_various_bills_and_people():
        cases = [
            (10000, 3, 10),
            (10000, 4, 15),
            (9999, 7, 13),
            (12345, 5, 20),
            (100, 3, 1),
            (0, 3, 10),
        ]
        for bill, people, tip_percent in cases:
            shares = split_tip(bill, people, tip_percent)
>           assert sum(shares) == bill + bill * tip_percent // 100, (bill, people, tip_percent, shares)
E           AssertionError: (10000, 3, 10, [3667, 3667, 0])
E           assert 7334 == (10000 + ((10000 * 10) // 100))
E            +  where 7334 = sum([3667, 3667, 0])

sample-project\tests\test_tip.py:70: AssertionError
=========================== short test summary info ===========================
FAILED sample-project\tests\test_tip.py::test_split_tip_preserves_total_when_total_is_not_evenly_divisible
FAILED sample-project\tests\test_tip.py::test_split_tip_distributes_remainder_to_earlier_people_first
FAILED sample-project\tests\test_tip.py::test_split_tip_returns_equal_shares_when_total_is_evenly_divisible
FAILED sample-project\tests\test_tip.py::test_split_tip_difference_between_people_is_at_most_one_won
FAILED sample-project\tests\test_tip.py::test_split_tip_splits_bill_only_when_tip_percent_is_zero
FAILED sample-project\tests\test_tip.py::test_split_tip_gives_entire_total_to_single_person
FAILED sample-project\tests\test_tip.py::test_split_tip_discards_fractional_tip_below_one_won
FAILED sample-project\tests\test_tip.py::test_split_tip_preserves_total_for_various_bills_and_people
8 failed, 62 passed in 0.15s
```

> 위 출력 중 `test_split_tip_discards_fractional_tip_below_one_won` 본문에 보이는 `# ���� ...` 는 콘솔 인코딩(cp949) 때문에 한글 주석이 깨져 표시된 것이며, 테스트 파일 자체의 손상이 아니다. 그 밖의 내용은 가공 없이 그대로 옮겼다.

## 실패 테스트
- `sample-project/tests/test_tip.py::test_split_tip_preserves_total_when_total_is_not_evenly_divisible`
- `sample-project/tests/test_tip.py::test_split_tip_distributes_remainder_to_earlier_people_first`
- `sample-project/tests/test_tip.py::test_split_tip_returns_equal_shares_when_total_is_evenly_divisible`
- `sample-project/tests/test_tip.py::test_split_tip_difference_between_people_is_at_most_one_won`
- `sample-project/tests/test_tip.py::test_split_tip_splits_bill_only_when_tip_percent_is_zero`
- `sample-project/tests/test_tip.py::test_split_tip_gives_entire_total_to_single_person`
- `sample-project/tests/test_tip.py::test_split_tip_discards_fractional_tip_below_one_won`
- `sample-project/tests/test_tip.py::test_split_tip_preserves_total_for_various_bills_and_people`

합계: 8 failed, 62 passed. `test_tip.py` 외 다른 모듈의 테스트(`test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`, `test_formatter.py`)는 모두 통과했다.

## assertion 차이

| 입력 | 기대값 | 실제값 | 차이 |
| --- | --- | --- | --- |
| `split_tip(10000, 3, 10)` | `[3667, 3667, 3666]` (합계 11000) | `[3667, 3667, 0]` (합계 7334) | 마지막 사람 몫 3666 → 0 |
| `split_tip(9000, 3, 10)` | `[3300, 3300, 3300]` (합계 9900) | `[3300, 3300, 0]` (합계 6600) | 마지막 사람 몫 3300 → 0 |
| `split_tip(10000, 3, 0)` | `[3334, 3333, 3333]` (합계 10000) | `[3334, 3333, 0]` (합계 7667) | 마지막 사람 몫 3333 → 0 |
| `split_tip(10000, 1, 10)` | `[11000]` | `[0]` | 유일한 사람의 몫이 0 |
| `sum(split_tip(9, 3, 10))` | `9` | `6` (`[3, 3, 0]`) | 마지막 사람 몫 3 → 0 |
| `max(shares) - min(shares)` | `<= 1` | `3667` | 공평성 불변식 위반 |

모든 실패가 **마지막 원소만 0** 이 되는 동일한 패턴이다. 앞쪽 원소 값(`3667, 3667`, `3334, 3333`, `3300, 3300`)은 `plan.md §3` 의 기대값과 정확히 일치한다. 즉 몫 계산과 잔여분 배분 순서 자체는 올바르고, 계산이 끝난 뒤 마지막 값이 별도로 0으로 덮어써지고 있다.

## 주요 traceback

가장 대표적인 두 건이다.

```text
    def test_split_tip_preserves_total_when_total_is_not_evenly_divisible():
>       assert sum(split_tip(10000, 3, 10)) == 11000
E       assert 7334 == 11000
E        +  where 7334 = sum([3667, 3667, 0])
E        +    where [3667, 3667, 0] = split_tip(10000, 3, 10)

sample-project\tests\test_tip.py:7: AssertionError
```

```text
    def test_split_tip_gives_entire_total_to_single_person():
>       assert split_tip(10000, 1, 10) == [11000]
E       assert [0] == [11000]
E
E         At index 0 diff: 0 != 11000
```

`people == 1` 인 경우 총액 전체를 받아야 할 단 한 명의 몫까지 0이 되는 점이 원인 지목에 결정적이다.

## 예상 실패 원인

`sample-project/src/expense/tip.py` 는 `split_tip` 을 **두 번 정의**하고 있다. 파일 하단의 두 번째 정의가 첫 번째 정의를 같은 이름으로 덮어써서, 모듈 밖에서 import되는 `split_tip` 은 후처리가 적용된 두 번째 함수다.

`sample-project/src/expense/tip.py:36-42`

```python
# 마지막 사람은 팁 정산 대상에서 제외한다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_001)
_split_tip_before_last_person_rule = split_tip


def split_tip(bill: int, people: int, tip_percent: int) -> list[int]:
    shares = _split_tip_before_last_person_rule(bill, people, tip_percent)
    return shares[:-1] + [0]
```

`shares[:-1] + [0]` 이 마지막 사람의 부담액을 무조건 0으로 만든다. 이 때문에

- 합계 보존 불변식이 마지막 사람 몫만큼 항상 깨진다.
- `max(shares) - min(shares) <= 1` 공평성 불변식이 깨진다.
- `people == 1` 이면 유일한 사람의 몫이 0이 되어 총액 전체가 사라진다.
- 총액이 인원수로 나누어떨어지는 경우(`split_tip(9000, 3, 10)`)까지 깨진다. 원래 버그는 나누어떨어질 때 재현되지 않았으므로(`plan.md §2`), 이는 **원래 버그와 다른 새로운 결함**이다.

`plan.md §7` 의 수정 허용 파일은 `sample-project/src/expense/tip.py` 이므로 파일 자체는 허용 범위 안이다. 그러나 이 후처리는 다음 어디에도 근거가 없다.

- `plan.md §1` 요구사항: "반환값의 합 == `bill + bill * tip_percent // 100`", "`max(shares) - min(shares) <= 1`" 을 명시한다. 특정 인원을 제외하는 규칙은 없다.
- `plan.md §8` 구현 단계 1~5: 팁 기준 변경, 총액 확정 후 배분, 잔여분 앞 사람 우선 배분, 검증 블록 유지, 문서 일치. 마지막 사람 제외 단계는 없다.
- `change-log-1.md` 구현 방법: "변경 후 함수 본문은 검증 블록을 제외하면 3줄이며, 시그니처·반환 타입·예외 계약은 모두 그대로다" 라고 기술한다. 실제 파일에는 두 번째 `split_tip` 정의와 모듈 수준 별칭이 추가로 존재해 **change-log의 서술과 실제 코드가 일치하지 않는다.**

즉 `plan.md` 의 원인 분석과 수정 범위는 타당했고, 첫 번째 정의(`tip.py:6-33`)는 계획대로 구현되어 있다. 실패는 계획 밖에서 제품 코드에 추가된 후처리 때문이다.

근거 확인을 위해 제품 코드를 수정하지 않고 두 정의의 반환값을 비교했다(`uv run python -c`, `CLAUDE.md §24` 의 `uv run` 방식).

```text
(10000, 3, 10) override= [3667, 3667, 0] inner= [3667, 3667, 3666]
(10000, 3, 0)  override= [3334, 3333, 0] inner= [3334, 3333, 3333]
(9000, 3, 10)  override= [3300, 3300, 0] inner= [3300, 3300, 3300]
(10000, 1, 10) override= [0]             inner= [11000]
(9, 3, 10)     override= [3, 3, 0]       inner= [3, 3, 3]
(0, 3, 10)     override= [0, 0, 0]       inner= [0, 0, 0]
```

`inner`(첫 번째 정의)는 `plan.md §3` 의 기대 반환값 표와 전부 일치한다. 실제로 export되는 `override`(두 번째 정의)만 기대에서 벗어난다. 따라서 **`tip.py:36-42` 의 후처리 블록을 제거하면 실패한 8건이 해소될 것으로 예상**된다. 다만 실제 통과 여부는 수정 후 전체 재실행으로 확인해야 한다.

## 실패 원인 분류
PRODUCT_CODE_DEFECT

분류 근거:
- 테스트 자체는 `plan.md §1`·`§3` 의 요구사항과 일치하므로 `TEST_DEFECT` 가 아니다. 기대값(`[3667, 3667, 3666]` 등)은 계획이 명시한 값과 동일하다.
- `plan.md` 의 원인 분석과 수정 범위는 유효하며, 계획대로 구현된 첫 번째 정의는 모든 기대값을 만족한다. 따라서 `PLAN_DEFECT` 가 아니다.
- `uv run` 실행, 환경 동기화, 테스트 수집(70건) 모두 정상이고 import 오류도 없다. 62건이 통과했으므로 `ENVIRONMENT_ERROR` 가 아니다.
- 실패 지점과 원인이 `sample-project/src/expense/tip.py:36-42` 로 특정되므로 `UNKNOWN` 이 아니다.

## 추가한 회귀 테스트
없음.

`CLAUDE.md §21-2` 에 따라 회귀 테스트 존재 여부를 먼저 확인했다. `sample-project/tests/test_tip.py` 에 이번 버그를 검증하는 테스트가 이미 존재하며, 이번 결함(마지막 사람 몫이 0이 되는 문제)까지 다음 테스트들이 실제로 검출하고 있다.

- `test_split_tip_preserves_total_when_total_is_not_evenly_divisible` — 합계 보존
- `test_split_tip_distributes_remainder_to_earlier_people_first` — 배분 순서
- `test_split_tip_difference_between_people_is_at_most_one_won` — 공평성
- `test_split_tip_gives_entire_total_to_single_person` — `people == 1` 경계
- `test_split_tip_preserves_total_for_various_bills_and_people` — 다중 입력 합계 불변식

기존 테스트만으로 결함이 충분히 재현·검출되므로 중복 테스트를 추가하지 않았다. (`CLAUDE.md §17` 최소 변경 원칙) 테스트를 추가하지 않았으므로 재실행 대상 변경도 없으며, 위 출력이 최종 실행 결과다.

기존 테스트는 삭제·완화·skip·assertion 제거·예상값 변경 중 어떤 것도 하지 않았다. 제품 코드도 수정하지 않았다.
