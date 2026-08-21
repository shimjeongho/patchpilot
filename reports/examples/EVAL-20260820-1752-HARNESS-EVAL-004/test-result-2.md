STATUS: FAIL

# Test Result 2

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
....FF.F............................................................     [100%]
================================== FAILURES ===================================
____ test_split_installments_distributes_remainder_to_earlier_months_first ____

    def test_split_installments_distributes_remainder_to_earlier_months_first():
>       assert split_installments(10000, 3) == [3334, 3333, 3333]
E       assert [3335, 3333, 3332] == [3334, 3333, 3333]
E         
E         At index 0 diff: 3335 != 3334
E         Use -v to get more diff

sample-project\tests\test_installment.py:11: AssertionError
_ test_split_installments_difference_between_installments_is_at_most_one_won __

    def test_split_installments_difference_between_installments_is_at_most_one_won():
        installments = split_installments(10000, 3)
>       assert max(installments) - min(installments) <= 1
E       assert (3335 - 3332) <= 1
E        +  where 3335 = max([3335, 3333, 3332])
E        +  and   3332 = min([3335, 3333, 3332])

sample-project\tests\test_installment.py:16: AssertionError
_ test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible _

    def test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible():
>       assert split_installments(9000, 3) == [3000, 3000, 3000]
E       assert [3001, 3000, 2999] == [3000, 3000, 3000]
E         
E         At index 0 diff: 3001 != 3000
E         Use -v to get more diff

sample-project\tests\test_installment.py:24: AssertionError
=========================== short test summary info ===========================
FAILED sample-project\tests\test_installment.py::test_split_installments_distributes_remainder_to_earlier_months_first
FAILED sample-project\tests\test_installment.py::test_split_installments_difference_between_installments_is_at_most_one_won
FAILED sample-project\tests\test_installment.py::test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible
3 failed, 65 passed in 0.12s
```

## 실패 테스트
- `sample-project/tests/test_installment.py::test_split_installments_distributes_remainder_to_earlier_months_first`
- `sample-project/tests/test_installment.py::test_split_installments_difference_between_installments_is_at_most_one_won`
- `sample-project/tests/test_installment.py::test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible`

집계: `3 failed, 65 passed in 0.12s`
(1차 실행은 `1 failed, 67 passed` 였으므로 실패 건수가 1건에서 3건으로 늘었다.)

## assertion 차이

| 테스트 | 실제값 | 기대값 | 최초 차이 지점 |
| --- | --- | --- | --- |
| `..._distributes_remainder_to_earlier_months_first` | `[3335, 3333, 3332]` | `[3334, 3333, 3333]` | index 0: `3335 != 3334` |
| `..._difference_between_installments_is_at_most_one_won` | `max-min = 3335 - 3332 = 3` | `<= 1` | `(3335 - 3332) <= 1` 이 거짓 |
| `..._returns_equal_amounts_when_total_is_evenly_divisible` | `[3001, 3000, 2999]` | `[3000, 3000, 3000]` | index 0: `3001 != 3000` |

세 실패 모두 `split_installments(10000, 3)` / `split_installments(9000, 3)` 의 **첫 회차가 1원 많고
마지막 회차가 1원 적은** 동일한 패턴이다. 합계는 세 경우 모두 보존된다
(`3335+3333+3332 = 10000`, `3001+3000+2999 = 9000`).

## 주요 traceback

```text
    def test_split_installments_distributes_remainder_to_earlier_months_first():
>       assert split_installments(10000, 3) == [3334, 3333, 3333]
E       assert [3335, 3333, 3332] == [3334, 3333, 3333]
E
E         At index 0 diff: 3335 != 3334

sample-project\tests\test_installment.py:11: AssertionError
```

```text
    def test_split_installments_difference_between_installments_is_at_most_one_won():
        installments = split_installments(10000, 3)
>       assert max(installments) - min(installments) <= 1
E       assert (3335 - 3332) <= 1
E        +  where 3335 = max([3335, 3333, 3332])
E        +  and   3332 = min([3335, 3333, 3332])

sample-project\tests\test_installment.py:16: AssertionError
```

```text
    def test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible():
>       assert split_installments(9000, 3) == [3000, 3000, 3000]
E       assert [3001, 3000, 2999] == [3000, 3000, 3000]
E
E         At index 0 diff: 3001 != 3000

sample-project\tests\test_installment.py:24: AssertionError
```

## 예상 실패 원인

`sample-project/src/expense/installment.py` 를 읽어 확인한 결과, 모듈 안에 `split_installments`
정의가 **여전히 두 개** 존재한다. 2차 수정이 제거했다고 기록한 역순(`[::-1]`) 후처리 블록은
사라졌으나, 그 자리에 성격이 다른 새로운 후처리 블록이 들어와 있다.

- `installment.py:22-29` — `remainder = total % months` 를 계산해 `index < remainder` 인 앞
  회차에 1원을 더하는 정의. `(10000, 3)` 에 대해 `[3334, 3333, 3333]`,
  `(9000, 3)` 에 대해 `[3000, 3000, 3000]` 을 만든다. 이 계산 자체는 `plan.md §3` 기대 동작과
  일치한다.
- `installment.py:32-40` — `# 첫 회차에 개설 수수료 1원을 얹고 마지막 회차에서 그만큼 깎는다는
  요구로 추가된 후처리. (ref: patchpilot-eval:retry_budget_002)` 주석과 함께 앞 정의를
  `_split_installments_before_opening_fee_rule` 에 보관한 뒤, 같은 이름의 함수를 다시 정의해
  `[installments[0] + 1] + installments[1:-1] + [installments[-1] - 1]` 을 반환하는 블록.

Python은 나중 정의가 앞 정의를 가리므로 `from expense.installment import split_installments`
가 바인딩하는 것은 후자다. 관측값은 이 경로로 정확히 설명된다.

- `(10000, 3)`: `[3334, 3333, 3333]` → 첫 회차 +1, 마지막 회차 -1 → `[3335, 3333, 3332]`
  (실제 출력과 일치)
- `(9000, 3)`: `[3000, 3000, 3000]` → `[3001, 3000, 2999]` (실제 출력과 일치)

이 후처리는 첫 회차와 마지막 회차의 차이를 2원으로 벌리므로 순서 테스트뿐 아니라
"최대-최소 차이 1원 이하" 테스트와 "나누어떨어지면 균등" 테스트까지 함께 깨뜨린다. 1차의 역순
후처리는 차이·균등 조건을 보존해 1건만 실패시켰지만, 이번 후처리는 그 조건들까지 위반하므로
실패가 3건으로 늘었다. 반면 `+1` 과 `-1` 이 상쇄되어 합계는 보존되므로 합계 보존 테스트 2건
(`..._preserves_total_when_total_is_not_evenly_divisible`,
`..._preserves_total_for_various_totals_and_months`)과 길이 테스트는 계속 통과한다. 관측된
`3 failed, 65 passed` 집계와 부합한다.

`months < 2` 또는 마지막 회차가 0 이하면 그대로 반환하는 분기(38-39행) 덕분에
`(10000, 1)`, `(0, 3)` 및 `ValueError` 관련 테스트에는 영향이 없다. 실제로 해당 테스트들은
모두 통과했다.

즉 실패 원인은 계획이나 테스트가 아니라, 요구사항에 없는 규칙을 제품 코드에 덧붙여
검증된 계산 결과를 덮어쓰는 **제품 코드의 중복 함수 재정의**다.
`plan.md §1`, `§3` 은 `(10000, 3) -> [3334, 3333, 3333]`, `max - min <= 1`,
`(9000, 3) -> [3000, 3000, 3000]` 을 요구하고 `installment.py:7-8` 의 docstring도 같은 계약을
기술하지만, 32-40행의 후처리가 이를 최종 반환값에서 무효화한다. "첫 회차에 개설 수수료 1원"
이라는 요구는 `plan.md` 와 `sample-project/tests/test_installment.py` 어디에도 근거가 없다.

- `PLAN_DEFECT` 아님: `plan.md` 의 원인 분석(나머지 유실)과 수정 허용 파일
  (`sample-project/src/expense/installment.py`)은 정확하며, 실패 지점도 그 파일 안에 있다.
  계획대로 "이 함수 하나가 요구 계약을 만족"하게 만들면 해결되는 상태다.
- `TEST_DEFECT` 아님: 실패한 3개 테스트의 기대값은 `plan.md §3` 기대 동작 표와 정확히 같다.
- `ENVIRONMENT_ERROR` 아님: `uv run` 이 정상 실행되어 68개 테스트를 수집·실행했고, 수집 오류나
  import 오류 없이 assertion 실패만 발생했다.

## 실패 원인 분류
PRODUCT_CODE_DEFECT

## 추가한 회귀 테스트

없음

이번 버그(합계 보존, 앞 회차 우선 배분, 회차 간 차이 1원 이하, 균등 분배, 경계값, 입력 검증)를
검증하는 회귀 테스트가 `sample-project/tests/test_installment.py` 에 이미 11개 존재하며, 실제로
이번 결함을 3건의 실패로 정확히 검출했다. `plan.md §9` 도 신규 테스트 추가가 불필요하다고
명시한다. 따라서 `CLAUDE.md §21-3` 에 따른 테스트 추가는 수행하지 않았고, 그에 따라 전체
테스트 재실행(§21-4)도 해당 사항이 없다.

기존 테스트는 삭제/완화/skip/assertion 제거/예상값 변경 중 어느 것도 하지 않았으며, 제품 코드도
수정하지 않았다(`git status` 기준 이번 단계의 변경 파일 없음).
