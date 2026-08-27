# Plan: 환불 금액을 결제 수단별로 나눌 때 나머지가 버려져 환불액이 유실되는 문제 수정

## 1. 요구사항 요약

`split_refund(amount, methods)` 가 반환하는 수단별 환불액의 합계가 `amount` 보다 작아지는 문제를 수정한다.

수정 후 만족해야 할 조건은 다음과 같다.

- 반환 목록의 합계는 항상 `amount` 와 같다. (합계 보존 불변식)
- 반환 목록의 길이는 항상 `methods` 와 같다.
- 수단 간 환불액 차이는 최대 1원이다.
- 나누어떨어지지 않아 생기는 1원 단위 나머지는 앞 수단부터 순서대로 배분한다.
- 기존 입력값 검증 동작(`methods < 1` → `ValueError`, `amount < 0` → `ValueError`)은 그대로 유지한다.
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의 동작에는 영향을 주지 않는다.

## 2. 재현 조건

`amount` 가 `methods` 로 나누어떨어지지 않는 모든 호출에서 재현된다.

```python
from expense.refund import split_refund

split_refund(1000, 3)   # 합계 999, 1원 유실
split_refund(1001, 3)   # 합계 999, 2원 유실
```

나누어떨어지는 경우(`split_refund(900, 3)`)와 수단이 1개인 경우(`split_refund(1000, 1)`)에는 나머지가 0이므로 재현되지 않는다.

## 3. 기대 동작

| 입력 | 기대 반환값 | 합계 |
| --- | --- | --- |
| `split_refund(1000, 3)` | `[334, 333, 333]` | 1000 |
| `split_refund(1001, 3)` | `[334, 334, 333]` | 1001 |
| `split_refund(900, 3)` | `[300, 300, 300]` | 900 |
| `split_refund(1000, 1)` | `[1000]` | 1000 |
| `split_refund(0, 3)` | `[0, 0, 0]` | 0 |
| `split_refund(1000, 4)` | 길이 4 목록 | 1000 |
| `split_refund(9999, 7)` | 길이 7 목록 | 9999 |
| `split_refund(1000, 0)` | `ValueError` | — |
| `split_refund(-1, 3)` | `ValueError` | — |

## 4. 현재 동작

- 모든 수단에 `amount // methods` 값이 동일하게 들어간 목록이 반환된다.
- 따라서 합계는 항상 `(amount // methods) * methods` 이며, `amount % methods` 만큼이 유실된다.
- 유실 금액은 최대 `methods - 1` 원이므로 결제 수단이 많을수록 커진다.
- 목록 길이와 입력값 검증은 현재도 정상이다.

## 5. 예상 원인

몫만 계산하고 나머지(`amount % methods`)를 계산하지도, 배분하지도 않기 때문이다.

정수 나눗셈으로 버려지는 나머지를 어딘가에 되돌려주는 단계가 함수에 아예 존재하지 않는다. 즉 누락된 로직이 원인이며, 잘못 계산된 로직이 원인이 아니다.

동일 저장소의 `split_amount` 는 같은 종류의 분배 문제를 이미 나머지 보존 방식으로 처리하고 있어, `split_refund` 만 그 처리가 빠진 상태다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/refund.py:21` — 함수 본문의 마지막이자 유일한 반환문이 `return [amount // methods] * methods` 다. 몫 하나를 `methods` 번 복제할 뿐이고 `amount % methods` 를 사용하는 코드가 파일 어디에도 없다. `amount=1000, methods=3` 이면 몫 333이 3번 복제되어 합계가 999가 되므로, 문제 상황의 현재 동작이 이 한 줄로 그대로 설명된다.
- `sample-project/src/expense/refund.py:16-19` — `methods <= 0` 과 `amount < 0` 에 대한 `ValueError` 검증이 반환문보다 앞에 존재한다. 검증 로직은 정상이며 이번 수정에서 건드릴 필요가 없다는 근거다.
- `sample-project/src/expense/refund.py:5-7` — Docstring이 "반환된 수단별 환불액의 합계는 환불 금액과 항상 같아야 한다" 고 이미 선언하고 있다. 즉 합계 보존은 이 함수가 원래 지켜야 할 계약이며, 구현이 문서화된 계약을 위반하고 있는 상태다.
- `sample-project/src/expense/splitter.py:21-28` — `split_amount` 가 몫과 나머지를 각각 구한 뒤, 앞 인덱스부터 나머지를 1원씩 얹어 합계를 보존한다. 같은 패키지에 동일 유형의 분배 규칙에 대한 기존 구현 스타일이 이미 존재하므로, `split_refund` 도 이 기존 스타일을 우선해 맞추는 것이 `CLAUDE.md §4`(기존 스타일 우선)에 부합한다는 근거다.
- `sample-project/tests/test_refund.py:11,36` — 테스트가 `[334, 333, 333]` 과 `[334, 334, 333]` 을 기대한다. 나머지를 뒤 수단이 아니라 **앞 수단부터** 배분해야 한다는 순서 요구가 테스트로 고정되어 있음을 확인했다.
- `sample-project/tests/test_refund.py:49-53` — 여러 `(amount, methods)` 조합에 대해 합계 보존을 일괄 검증한다. 특정 입력에만 맞춘 하드코딩으로는 통과할 수 없다는 근거다.
- `grep` 결과, `split_refund` 를 참조하는 곳은 `sample-project/tests/test_refund.py` 뿐이고 `sample-project/src/` 내 다른 모듈은 `refund` 를 import 하지 않는다. 영향 범위가 이 함수 하나로 닫혀 있다는 근거다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/refund.py`

이 파일 하나로 충분하다. 근거는 §6의 grep 결과이며, 다른 제품 코드 모듈은 `refund` 를 참조하지 않는다.

테스트 파일은 수정 대상이 아니다. 기대 동작이 이미 `sample-project/tests/test_refund.py` 에 정확히 인코딩되어 있으므로 테스트를 손댈 이유가 없다.

## 8. 구현 단계

1. `sample-project/src/expense/refund.py:21` 의 반환 로직을, 정수 나눗셈에서 버려지는 나머지가 사라지지 않고 수단들에게 되돌아가도록 바꾼다. — 합계 보존 불변식(`sum(result) == amount`)을 성립시키는 것이 이 단계의 유일한 목적이다. 나머지를 어떤 수단에게 얼마나 얹을지는 §1과 §3의 조건(길이 `methods` 유지, 수단 간 차이 최대 1원, 앞 수단 우선)을 동시에 만족하도록 Developer가 `splitter.py:21-28` 의 기존 구현 스타일을 읽고 판단한다.

2. 변경한 로직의 **의도**를 설명하는 주석을 남긴다. — `CLAUDE.md §5` 에 따라 "나머지를 계산한다" 같은 코드 반복 주석이 아니라, 왜 나머지를 앞 수단부터 배분하는지(합계 보존과 수단 간 차이 최소화라는 비즈니스 규칙)를 남긴다. `splitter.py:24` 의 주석이 같은 취지의 기존 예시다.

3. 기존 입력값 검증(`refund.py:16-19`)과 Docstring, 함수 시그니처, 타입 힌트는 그대로 둔다. — `CLAUDE.md §17` 최소 변경 원칙. 이번 요구사항은 반환값 계산만 다루며, 검증 동작 유지는 §1의 명시적 요구사항이다.

4. 변경 후 `refund.py` 에 사용하지 않는 변수나 import가 남지 않았는지 확인한다. — `CLAUDE.md §9` 코드 품질 체크.

구현 방향에 대한 제약을 한 가지 덧붙인다. §6에서 확인했듯 테스트가 여러 `(amount, methods)` 조합을 일괄 검증하므로, 특정 입력값에 분기하거나 기대값을 하드코딩하는 방식은 요구사항을 만족하지 못한다. 임의의 `amount >= 0`, `methods >= 1` 에 대해 성립하는 일반 로직이어야 한다.

## 9. 검증 방법

- 실행 명령: `uv run pytest sample-project/tests -q`

통과 판정 기준:

1. `sample-project/tests/test_refund.py` 의 11개 테스트가 모두 통과한다.
2. `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`, `test_formatter.py` 등 기존에 통과하던 테스트가 하나도 깨지지 않는다.
3. 전체 실행 결과에 `failed` 와 `error` 가 0건이다.
4. skip 처리나 assertion 완화로 통과시킨 흔적이 없다. (`CLAUDE.md §3-3`)

특정 실패 테스트 하나만 통과한 상태는 완료로 보지 않는다. 전체가 통과해야 한다.

## 10. 예상 위험 요소

- **`amount = 0` 경계**: 몫과 나머지가 모두 0이 되어 `[0, 0, 0]` 이 나와야 한다. 나머지 배분 로직을 넣으면서 이 경계가 깨지지 않는지 확인이 필요하다. `test_refund.py:32` 가 이를 검증한다.

- **`methods = 1` 경계**: 나머지가 항상 0이므로 전액이 단일 수단에 가야 한다. 나머지 배분 조건식의 경계 처리(`<` 와 `<=` 혼동 등)에서 실수가 나기 쉬운 지점이다. `test_refund.py:28` 이 검증한다.

- **배분 순서 역전**: 합계 보존만 만족시키고 나머지를 뒤 수단부터 배분하면 `[333, 333, 334]` 가 되어 합계 테스트는 통과하지만 `test_refund.py:11,36` 의 정확한 목록 비교에서 실패한다. 합계만 보고 완료로 판단하지 않아야 한다.

- **수단 간 차이 초과**: 나머지를 한 수단에 몰아주면 합계는 보존되지만 차이가 1원을 넘어 `test_refund.py:22-24` 에서 실패한다.

- **음수 입력 처리**: `amount < 0` 은 `ValueError` 로 차단되므로 나머지 배분 로직이 음수를 만날 일은 없다. 다만 검증 순서를 바꾸면 이 전제가 깨지므로 검증 블록을 반환 로직보다 뒤로 옮기지 않아야 한다.

- **회귀 범위**: §6의 grep 결과상 `split_refund` 는 다른 제품 코드에서 호출되지 않으므로 이 함수 밖으로 회귀가 번질 가능성은 낮다. 단, 수정 과정에서 `splitter.py` 등 다른 모듈을 "함께 정리"하려는 시도는 요구사항 범위를 벗어나며 `CLAUDE.md §3-7`, `§17` 위반이다. 수정은 §7의 파일 하나로 제한한다.

- **공통 헬퍼 추출 유혹**: `split_amount` 와 `split_refund` 의 분배 규칙이 유사해 보여 공통 함수로 묶고 싶을 수 있으나, 이는 요구사항 밖의 구조 변경이다. `CLAUDE.md §3-7`, `§17` 에 따라 이번 실행에서는 하지 않는다.
