# Plan: 분납 회차 청구 시 나머지 금액이 유실되어 회차 합계가 총액과 달라지는 문제 수정

## 1. 요구사항 요약

`split_installments(total, months)` 가 반환하는 회차별 청구 금액 목록의 합계가 항상 `total` 과
같아야 한다. 현재는 총액이 회차 수로 나누어떨어지지 않을 때 나머지가 유실되어 합계가 `total` 보다
작다.

만족해야 할 조건(요구사항):

- `sum(결과) == total` (항상)
- `len(결과) == months` (항상)
- `max(결과) - min(결과) <= 1`
- 나누어떨어지지 않아 생기는 1원 단위 차이는 **앞 회차부터** 배분한다.
  - 예: `split_installments(10000, 3)` → `[3334, 3333, 3333]`
- 기존 입력값 검증 동작 유지: `months < 1` 이면 `ValueError`, `total < 0` 이면 `ValueError`
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않아야 한다.

## 2. 재현 조건

- 대상 함수: `expense.installment.split_installments`
- 조건: `total % months != 0` 인 입력
- 재현 코드

```python
from expense.installment import split_installments

split_installments(10000, 3)
split_installments(9999, 4)
```

- 테스트로는 `uv run pytest sample-project/tests -q` 실행 시
  `sample-project/tests/test_installment.py` 의 나머지 배분/합계 보존 관련 테스트가 실패한다.

## 3. 기대 동작

| 입력 | 기대 반환값 | 근거 |
| --- | --- | --- |
| `(10000, 3)` | `[3334, 3333, 3333]` | 나머지 1원을 첫 회차에 배분 |
| `(9999, 4)` | 합계 9999, 길이 4, 최대-최소 차이 1 이하, 앞 회차 우선 배분 | 나머지 3원을 앞 3개 회차에 1원씩 배분 |
| `(9000, 3)` | `[3000, 3000, 3000]` | 나머지가 없으면 균등 |
| `(10000, 1)` | `[10000]` | 단일 회차는 전액 청구 |
| `(0, 3)` | `[0, 0, 0]` | 총액 0도 합계 보존 |
| `(10000, 0)` / `(10000, -1)` | `ValueError` | 기존 검증 유지 |
| `(-1, 3)` | `ValueError` | 기존 검증 유지 |

## 4. 현재 동작

- `split_installments(10000, 3)` → `[3333, 3333, 3333]` (합계 9999, 1원 유실)
- `split_installments(9999, 4)` → `[2499, 2499, 2499, 2499]` (합계 9996, 3원 유실)
- `split_installments(9000, 3)` → `[3000, 3000, 3000]` (나누어떨어지므로 정상)
- `split_installments(10000, 1)` → `[10000]` (나머지가 없으므로 정상)
- 입력값 검증(`ValueError`)은 현재도 정상 동작한다.
- 유실 금액은 `total % months` 와 같으므로 회차 수가 커질수록 최대 유실 금액도 커진다.

## 5. 예상 원인

`split_installments` 는 몫(`total // months`)만 계산해 그 값을 회차 수만큼 그대로 복제한 목록을
반환한다. 정수 나눗셈에서 버려지는 나머지(`total % months`)를 어느 회차에도 더하지 않기 때문에
합계가 항상 `total - (total % months)` 가 된다. 즉 "합계 보존"이라는 계약이 구현에서 빠져 있고,
docstring에 기술된 동작과 실제 구현이 불일치한다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/installment.py:22` — `amount_per_month = total // months` 로 몫만
  구하고, 나머지(`total % months`)를 계산하거나 사용하는 코드가 함수 어디에도 없다. 유실의 직접
  원인이다.
- `sample-project/src/expense/installment.py:23` — `return [amount_per_month] * months` 로 동일한
  몫을 회차 수만큼 복제해 반환한다. 길이는 `months` 로 맞지만 합계는 나머지만큼 부족해진다.
- `sample-project/src/expense/installment.py:7-8` — docstring에 "나누어떨어지지 않는 나머지는 앞
  회차부터 1원씩 배분하므로 회차별 청구 금액의 합계는 항상 total과 같아야 한다" 고 명시되어 있어,
  기대 동작이 문서화된 계약과 일치하며 구현만 누락되었음을 확인했다.
- `sample-project/src/expense/installment.py:17-20` — `months <= 0`, `total < 0` 에 대한
  `ValueError` 검증은 이미 존재하고 정상 동작한다. 이 부분은 유지 대상이며 수정 범위가 아니다.
- `sample-project/tests/test_installment.py:11` —
  `test_split_installments_distributes_remainder_to_earlier_months_first` 가
  `[3334, 3333, 3333]` 을 요구한다. 배분 순서가 앞 회차 우선이어야 한다는 근거다.
- `sample-project/tests/test_installment.py:50-61` —
  `test_split_installments_preserves_total_for_various_totals_and_months` 가 `(10000, 7)`,
  `(9999, 4)`, `(12345, 5)`, `(100, 3)`, `(0, 3)` 등 여러 조합에서 합계 보존을 요구한다. 특정
  입력에만 맞춘 수정으로는 통과할 수 없다.
- `sample-project/src/expense/splitter.py:21-28` — 같은 패키지의 `split_amount` 가 동일한 성격의
  "나머지를 앞에서부터 1원씩 배분" 요구사항을 이미 충족하고 있다. 프로젝트에 기존 스타일이 존재
  하므로(`CLAUDE.md §4`) 새로운 방식보다 기존 스타일과 일관된 형태를 따르는 것이 바람직하다.
- `sample-project/src/expense/installment.py` 는 다른 모듈에서 import 되지 않는다
  (`installment` 문자열이 등장하는 파일은 해당 모듈과 그 테스트뿐). 따라서 이 함수 수정이
  `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 에
  영향을 주지 않는다.
- `sample-project/pytest.ini:2-3` — `pythonpath = src`, `testpaths = tests` 로 설정되어 있어
  테스트가 `expense.installment` 를 import 하는 구조가 이미 갖춰져 있다. 환경 관련 추가 작업은
  필요 없다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/installment.py`

이 목록 밖의 파일은 수정하지 않는다. 특히 `sample-project/tests/` 하위 테스트 파일은 수정 대상이
아니며, 요구사항에 따라 회귀 테스트는 이미 존재하므로 추가할 필요도 없다.

## 8. 구현 단계

1. `split_installments` 에서 정수 나눗셈으로 버려지는 나머지 금액을 파악하고, 이를 반환값에 반영
   되도록 계산 흐름을 바꾼다. — 합계가 `total` 과 항상 같아야 한다는 계약(합계 보존)을 구현에
   실제로 성립시키기 위한 단계다. 현재는 나머지가 계산조차 되지 않고 사라진다.
2. 회차별 금액을 만들 때 "동일한 몫을 복제"하는 대신, 나머지에 해당하는 만큼의 **앞쪽 회차**가 1원
   더 청구되도록 목록을 구성한다. — 배분 순서(앞 회차 우선)와 회차 간 차이 1원 이하 조건을 동시에
   만족시키기 위한 단계다. 어떤 코드 형태로 구성할지는 Developer가 `splitter.py:21-28` 의 기존
   스타일과 `installment.py` 현재 구조를 읽고 판단한다.
3. 경계 입력에서 계약이 깨지지 않는지 점검한다. — `months == 1`, `total == 0`, 나누어떨어지는
   경우(`(9000, 3)`)에서 기존과 동일한 결과가 나와야 하고, 반환 길이는 언제나 `months` 여야 한다.
   나머지 배분 로직이 이 경우들을 자연스럽게 포함하는지 확인하는 것이 목적이다.
4. 기존 입력값 검증 분기와 docstring을 그대로 유지한다. — `months <= 0`, `total < 0` 의
   `ValueError` 는 요구사항상 유지 대상이고, docstring은 이미 올바른 계약을 기술하고 있어 수정할
   이유가 없다. 요구사항 밖 변경을 만들지 않기 위한 단계다(`CLAUDE.md §17`).
5. 변경 범위를 이 함수 내부로 한정한다. — 함수 시그니처, 모듈 구조, 다른 모듈은 건드리지 않는다.
   diff가 리뷰하기 쉬운 최소 변경으로 남도록 하는 것이 목적이다.

주석은 `CLAUDE.md §5` 에 따라 "무엇을 하는지"가 아니라 "왜 앞 회차부터 배분하는지" 같은 의도가
필요한 지점에만 남긴다.

## 9. 검증 방법

- 실행 명령: `uv run pytest sample-project/tests -q`
- 통과 판정 기준
  - `sample-project/tests/test_installment.py` 의 11개 테스트가 모두 통과한다. 특히
    `test_split_installments_preserves_total_when_total_is_not_evenly_divisible`,
    `test_split_installments_distributes_remainder_to_earlier_months_first`,
    `test_split_installments_difference_between_installments_is_at_most_one_won`,
    `test_split_installments_preserves_total_for_various_totals_and_months` 가 통과해야 한다.
  - `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`,
    `test_reconciliation.py`, `test_formatter.py` 등 기존에 통과하던 테스트가 하나도 깨지지
    않는다. 즉 전체 실행 결과에 `failed` 와 `error` 가 0건이어야 한다.
  - 특정 실패 테스트 하나만 통과한 상태는 완료로 보지 않는다(`CLAUDE.md §10`).
- 회귀 테스트 추가 여부: 요구사항에 명시된 5가지 기대 동작을 검증하는 회귀 테스트가
  `sample-project/tests/test_installment.py` 에 이미 존재하므로 신규 테스트 추가는 필요 없다.

## 10. 예상 위험 요소

- **앞/뒤 배분 순서 혼동**: 합계만 맞추고 나머지를 뒤 회차부터 배분하면 합계 테스트는 통과하지만
  `[3334, 3333, 3333]` 를 요구하는 테스트에서 실패한다. 순서가 요구사항의 일부임에 유의해야 한다.
- **일부 케이스만 맞춘 수정**: `(10000, 3)` 만 맞추고 `(9999, 4)`, `(12345, 5)`, `(10000, 7)` 에서
  깨지는 형태의 수정은 `test_split_installments_preserves_total_for_various_totals_and_months`
  에서 드러난다. 특정 입력이 아니라 일반 규칙으로 해결해야 한다.
- **경계값 회귀**: `total == 0` 일 때 `[0, 0, 0]` 이 아니라 다른 길이/값이 나오거나,
  `months == 1` 에서 전액이 아닌 값이 나오는 회귀 가능성이 있다.
- **검증 로직 훼손**: 나머지 배분을 넣는 과정에서 기존 `ValueError` 분기를 건드리면 예외 관련
  테스트 3개가 함께 깨진다. `CLAUDE.md §8` 에 따라 예외를 조용히 삼키는 형태로 바꾸어서도 안 된다.
- **범위 초과 변경**: 같은 패키지의 `splitter.py` 등에 공통 헬퍼를 추출하는 식의 리팩터링은
  요구사항 밖 변경이며 다른 모듈 회귀 위험을 만든다(`CLAUDE.md §3-7`, `§17`). 이번 변경은
  `installment.py` 한 파일 안에서 끝나야 한다.
- **영향 범위 자체는 낮음**: `installment` 모듈은 다른 제품 모듈에서 import 되지 않으므로, 위
  위험들만 피하면 타 모듈로의 파급은 없다고 판단한다.
