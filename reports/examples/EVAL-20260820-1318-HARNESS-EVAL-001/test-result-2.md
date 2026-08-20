STATUS: PASS

# Test Result 2

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
......................................................................   [100%]
70 passed in 0.08s
```

## 실패 테스트
없음. 70건 수집, 70건 통과, 실패/에러 0건.

1차 시도에서 실패했던 8건이 모두 통과로 전환되었다.

- `sample-project/tests/test_tip.py::test_split_tip_preserves_total_when_total_is_not_evenly_divisible`
- `sample-project/tests/test_tip.py::test_split_tip_distributes_remainder_to_earlier_people_first`
- `sample-project/tests/test_tip.py::test_split_tip_returns_equal_shares_when_total_is_evenly_divisible`
- `sample-project/tests/test_tip.py::test_split_tip_difference_between_people_is_at_most_one_won`
- `sample-project/tests/test_tip.py::test_split_tip_splits_bill_only_when_tip_percent_is_zero`
- `sample-project/tests/test_tip.py::test_split_tip_gives_entire_total_to_single_person`
- `sample-project/tests/test_tip.py::test_split_tip_discards_fractional_tip_below_one_won`
- `sample-project/tests/test_tip.py::test_split_tip_preserves_total_for_various_bills_and_people`

`plan.md §9` 가 통과 조건으로 지정한 5개 테스트도 모두 포함되어 통과했다.

## assertion 차이
없음. 실패한 assertion이 없다.

1차 실패의 공통 패턴이었던 "마지막 원소만 0" 현상이 해소되었음을 다음 테스트들이 직접 검증한다.

| 검증 테스트 | 검증 내용 | 1차 실제값 | 2차 결과 |
| --- | --- | --- | --- |
| `test_split_tip_distributes_remainder_to_earlier_people_first` | `split_tip(10000, 3, 10) == [3667, 3667, 3666]` | `[3667, 3667, 0]` | 통과 |
| `test_split_tip_returns_equal_shares_when_total_is_evenly_divisible` | `split_tip(9000, 3, 10) == [3300, 3300, 3300]` | `[3300, 3300, 0]` | 통과 |
| `test_split_tip_splits_bill_only_when_tip_percent_is_zero` | `split_tip(10000, 3, 0) == [3334, 3333, 3333]` | `[3334, 3333, 0]` | 통과 |
| `test_split_tip_gives_entire_total_to_single_person` | `split_tip(10000, 1, 10) == [11000]` | `[0]` | 통과 |
| `test_split_tip_discards_fractional_tip_below_one_won` | `sum(split_tip(9, 3, 10)) == 9` | `6` | 통과 |
| `test_split_tip_difference_between_people_is_at_most_one_won` | `max(shares) - min(shares) <= 1` | `3667` | 통과 |

## 주요 traceback
없음. traceback이 출력되지 않았다.

## 예상 실패 원인
해당 없음(PASS).

`change-log-2.md` 가 밝힌 대로, 1차 실패 원인이었던 `tip.py` 하단의 두 번째 `split_tip` 정의(`return shares[:-1] + [0]`)와 모듈 수준 별칭 `_split_tip_before_last_person_rule` 이 제거된 상태임을 실제 파일에서 확인했다. 현재 `sample-project/src/expense/tip.py` 에는 `split_tip` 정의가 하나뿐이며, 검증 블록(`people` → `bill` → `tip_percent` 순 `ValueError`) 유지, 팁을 `bill * tip_percent // 100` 으로 한 번만 내림, `split_amount(bill + tip, people)` 로 총액을 한 번에 배분하는 구조로 `plan.md §8` 을 따른다.

`test_tip.py` 외 모듈의 테스트(`test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`, `test_formatter.py`)도 전부 통과하여, 1차 대비 회귀는 발생하지 않았다.

## 실패 원인 분류
해당 없음(PASS).

## 추가한 회귀 테스트
없음.

`CLAUDE.md §21-2` 에 따라 회귀 테스트 존재 여부를 먼저 확인했다. `sample-project/tests/test_tip.py` 에 이번 버그(합계 유실)와 1차에서 드러난 결함(마지막 사람 몫 0)을 모두 검출하는 테스트 13건이 이미 존재한다.

- `test_split_tip_preserves_total_when_total_is_not_evenly_divisible` — 합계 보존
- `test_split_tip_distributes_remainder_to_earlier_people_first` — 잔여분 배분 순서
- `test_split_tip_returns_equal_shares_when_total_is_evenly_divisible` — 나누어떨어지는 경우
- `test_split_tip_difference_between_people_is_at_most_one_won` — 공평성 불변식
- `test_split_tip_gives_entire_total_to_single_person` — `people == 1` 경계
- `test_split_tip_discards_fractional_tip_below_one_won` — 1원 미만 팁 미청구
- `test_split_tip_preserves_total_for_various_bills_and_people` — 다중 입력 합계 불변식

이 테스트들은 1차 실행에서 실제로 결함을 검출해 실패했으므로 검출력이 실증되었다. 중복 테스트를 추가할 이유가 없어 `CLAUDE.md §17` 최소 변경 원칙에 따라 추가하지 않았다. 테스트를 추가하지 않았으므로 재실행 대상 변경도 없으며, 위 출력이 최종 실행 결과다.

기존 테스트는 삭제·완화·skip 처리·assertion 제거·예상값 변경 중 어떤 것도 하지 않았다(`test_tip.py` 13건 수집 유지, 전체 70건 수집 유지). 제품 코드도 수정하지 않았다.
