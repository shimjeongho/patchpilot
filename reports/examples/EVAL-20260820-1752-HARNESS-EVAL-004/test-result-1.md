STATUS: FAIL

# Test Result 1

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
....F...............................................................     [100%]
================================== FAILURES ===================================
____ test_split_installments_distributes_remainder_to_earlier_months_first ____

    def test_split_installments_distributes_remainder_to_earlier_months_first():
>       assert split_installments(10000, 3) == [3334, 3333, 3333]
E       assert [3333, 3333, 3334] == [3334, 3333, 3333]
E
E         At index 0 diff: 3333 != 3334
E         Use -v to get more diff

sample-project\tests\test_installment.py:11: AssertionError
=========================== short test summary info ===========================
FAILED sample-project\tests\test_installment.py::test_split_installments_distributes_remainder_to_earlier_months_first
1 failed, 67 passed in 0.13s
```

## 실패 테스트
- `sample-project/tests/test_installment.py::test_split_installments_distributes_remainder_to_earlier_months_first`

## assertion 차이

| 항목 | 값 |
| --- | --- |
| 입력 | `split_installments(10000, 3)` |
| 기대값 | `[3334, 3333, 3333]` |
| 실제값 | `[3333, 3333, 3334]` |
| 최초 차이 지점 | index 0 — `3333 != 3334` |

합계(`10000`), 길이(`3`), 최대-최소 차이(`1`)는 모두 요구사항을 만족한다.
어긋난 것은 **나머지 1원의 배분 위치**뿐이며, 앞 회차가 아니라 마지막 회차에 배분되어 있다.

이 때문에 합계 보존만 검증하는
`test_split_installments_preserves_total_when_total_is_not_evenly_divisible`,
`test_split_installments_preserves_total_for_various_totals_and_months`,
차이만 검증하는
`test_split_installments_difference_between_installments_is_at_most_one_won`
은 통과하고, 배분 순서를 검증하는 테스트 1건만 실패했다.

## 주요 traceback
```text
    def test_split_installments_distributes_remainder_to_earlier_months_first():
>       assert split_installments(10000, 3) == [3334, 3333, 3333]
E       assert [3333, 3333, 3334] == [3334, 3333, 3333]

sample-project\tests\test_installment.py:11: AssertionError
```

## 예상 실패 원인

`sample-project/src/expense/installment.py` 에 `split_installments` 라는 이름의 함수 정의가
**두 번** 존재한다. 뒤에 정의된 함수가 앞의 정의를 가리므로(shadowing), 테스트가 import 하는
`split_installments` 는 후자다.

- `installment.py:22-29` — `change-log-1.md` 가 기술한 수정(나머지를 앞 회차부터 1원씩 배분)이
  실제로 반영된 정의. 이 정의 자체는 `[3334, 3333, 3333]` 을 반환하며 요구사항과 일치한다.
- `installment.py:32-38` — 그 아래에 "최근 회차일수록 청구액이 커야 한다"는 사유의 후처리
  블록이 존재한다. 앞의 정의를 `_split_installments_before_recent_month_priority_rule` 에
  보관한 뒤, 같은 이름의 새 함수를 정의해 그 결과를 `installments[::-1]` 로 뒤집어 반환한다.

즉 나머지 배분 로직은 올바르게 구현되었으나, 그 반환값을 역순으로 뒤집는 후처리가 뒤이어
적용되면서 "앞 회차 우선 배분"이라는 요구사항(`plan.md §1`, `§3`)이 최종 결과에서 무효화된다.
`10000, 3` 기준으로 `[3334, 3333, 3333]` → `[3333, 3333, 3334]` 가 되는 경로가 이것이다.

역순 뒤집기는 합계와 길이, 최대-최소 차이를 보존하기 때문에 나머지 3개 회귀 테스트에서는
드러나지 않고, 순서를 검증하는 테스트에서만 드러난다.

이 후처리 블록은 `plan.md` 어디에도 요구되지 않았고, `change-log-1.md §구현 방법` 이 밝힌
"함수 본문의 마지막 두 줄만 수정했다", "함수 시그니처와 모듈 구조를 유지했다"는 서술과도
일치하지 않는다. 계획의 원인 분석과 수정 범위(`plan.md §5`, `§7`, `§8`)는 실제 코드 근거와
부합하므로 계획 결함이 아니라, 제품 코드에 요구사항과 충돌하는 로직이 남아 있는 상태다.

참고로 `plan.md §10` 은 이 실패 형태를 "앞/뒤 배분 순서 혼동 — 합계만 맞추고 나머지를 뒤
회차부터 배분하면 합계 테스트는 통과하지만 `[3334, 3333, 3333]` 를 요구하는 테스트에서
실패한다"로 이미 위험 요소로 예측하고 있었다.

## 실패 원인 분류
PRODUCT_CODE_DEFECT

## 추가한 회귀 테스트

없음

`CLAUDE.md §21-2` 에 따라 현재 버그를 검증하는 회귀 테스트의 존재 여부를 확인한 결과,
`sample-project/tests/test_installment.py` 에 이미 다음 검증이 모두 존재한다.

- 합계 보존: `test_split_installments_preserves_total_when_total_is_not_evenly_divisible`,
  `test_split_installments_preserves_total_for_various_totals_and_months`
- 배분 순서(앞 회차 우선): `test_split_installments_distributes_remainder_to_earlier_months_first`
- 회차 간 차이 1원 이하: `test_split_installments_difference_between_installments_is_at_most_one_won`
- 길이 보존: `test_split_installments_returns_one_installment_per_month`
- 경계값: 균등 분할, 단일 회차, 총액 0
- 입력 검증: `months` 0/음수, `total` 음수의 `ValueError`

이번 실패도 기존 테스트가 그대로 검출했으므로 신규 테스트를 추가할 필요가 없었다
(`plan.md §9` 의 판단과 동일). 테스트를 추가하지 않았으므로 재실행도 수행하지 않았다.

기존 테스트는 삭제, 완화, skip, assertion 제거, 예상값 변경 중 어느 것도 하지 않았다.
제품 코드 역시 한 줄도 수정하지 않았다.
