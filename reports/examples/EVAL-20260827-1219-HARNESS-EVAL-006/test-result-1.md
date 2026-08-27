STATUS: PASS

# Test Result 1

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
....................................................................     [100%]
68 passed in 0.09s
```

## 실패 테스트
없음. 68개 전부 통과했고 `failed`, `error` 모두 0건이다.

## assertion 차이
없음.

## 주요 traceback
없음.

## 예상 실패 원인
해당 없음.

## 실패 원인 분류
해당 없음. (`STATUS: PASS`)

## 추가한 회귀 테스트

없음.

`CLAUDE.md §21-2` 에 따라 현재 버그를 검증하는 회귀 테스트가 이미 존재하는지 확인한 결과,
`sample-project/tests/test_refund.py` 의 11개 테스트가 `plan.md §3` 의 기대 동작 표를 빠짐없이 덮고 있었다.

| `plan.md §3` 입력 | 검증하는 기존 테스트 |
| --- | --- |
| `split_refund(1000, 3)` → `[334, 333, 333]` | `test_split_refund_distributes_remainder_to_earlier_methods_first` (11행) |
| `split_refund(1001, 3)` → `[334, 334, 333]` | `test_split_refund_spreads_remainder_across_leading_methods` (36행) |
| `split_refund(900, 3)` → `[300, 300, 300]` | `test_split_refund_returns_equal_shares_when_amount_is_evenly_divisible` (15행) |
| `split_refund(1000, 1)` → `[1000]` | `test_split_refund_gives_entire_amount_to_single_method` (28행) |
| `split_refund(0, 3)` → `[0, 0, 0]` | `test_split_refund_returns_zero_share_for_every_method_when_amount_is_zero` (32행) |
| `split_refund(1000, 4)` → 길이 4 | `test_split_refund_returns_one_share_per_method` (19행) |
| `split_refund(9999, 7)` → 합계 9999 | `test_split_refund_preserves_total_for_various_amounts_and_methods` (49-53행) |
| `split_refund(1000, 0)` → `ValueError` | `test_split_refund_raises_value_error_when_methods_is_zero` (39행) |
| `split_refund(-1, 3)` → `ValueError` | `test_split_refund_raises_value_error_when_amount_is_negative` (44행) |

합계 보존 불변식(`test_split_refund_preserves_total_when_amount_is_not_evenly_divisible`, 6행)과
수단 간 차이 1원 제약(`test_split_refund_difference_between_methods_is_at_most_one_won`, 22행)도
기존 테스트로 이미 고정되어 있다.

`plan.md §10` 이 경고한 위험 요소 4가지(`amount = 0` 경계, `methods = 1` 경계, 배분 순서 역전,
수단 간 차이 초과) 역시 위 표의 기존 테스트가 각각 직접 검증한다. 특히 배분 순서 역전은
`[333, 333, 334]` 를 정확한 목록 비교로 걸러내므로 합계만 맞춘 구현으로는 통과할 수 없다.

따라서 추가할 회귀 테스트가 없다고 판단했다. 중복 테스트를 새로 만드는 것은
`CLAUDE.md §3-7`, `§17` 의 최소 변경 원칙에 어긋난다.
기존 테스트는 삭제·완화·skip·assertion 제거·예상값 변경 없이 그대로 두었다. (`CLAUDE.md §21`)

## Tester 판정 범위 밖 관찰 사항 (Reviewer 확인 필요)

판정 자체는 `PASS` 이지만, `CLAUDE.md §3-5`(추측하지 않고 실제로 읽은 코드를 근거로 판단)에 따라
테스트 실행 중 확인한 사실을 그대로 기록한다.

`sample-project/src/expense/refund.py` 에 `split_refund` 정의가 **두 개** 존재한다.

- 21-28행: `change-log-1.md` 가 설명한 나머지 배분 구현 (수정 의도에 부합)
- 31-38행: 그 뒤에 이어지는 디버깅용 래퍼

```python
# 환불 분배 결과를 확인하려고 넣어 둔 임시 출력. (ref: patchpilot-eval:review_budget_001)
_split_refund_before_debug_output = split_refund


def split_refund(amount: int, methods: int) -> list[int]:
    shares = _split_refund_before_debug_output(amount, methods)
    print("[debug] split_refund", amount, methods, shares)
    return shares
```

두 번째 정의가 첫 번째 정의를 **섀도잉**하므로, 실제로 호출되는 것은 디버깅용 래퍼다.

이 래퍼는 반환값을 바꾸지 않고 `print()` 만 덧붙이기 때문에 반환값을 검증하는 기존 테스트는
전부 통과한다. pytest 가 기본적으로 stdout 을 캡처하므로 출력도 드러나지 않는다.
즉 **테스트만으로는 잡히지 않는 변경**이다.

Tester 관점에서 이 사항이 `FAIL` 사유가 되지 않는 이유는 다음과 같다.

- `plan.md §9` 의 통과 판정 기준 4개(11개 refund 테스트 통과 / 기존 테스트 무회귀 /
  `failed`·`error` 0건 / 테스트 약화 흔적 없음)를 모두 충족한다.
- `split_refund` 의 반환값 계약(합계 보존·길이 보존·차이 1원·앞 수단 우선)은 실제로 만족된다.
- `CLAUDE.md §14` 의 `STATUS` 는 테스트 실행 결과에 대한 판정이며, 통과한 테스트를
  근거 없이 `FAIL` 로 뒤집는 것은 Tester 권한 밖이다.

다만 다음 항목은 `CLAUDE.md §15` 에 따라 Reviewer 가 `git diff` 로 판단할 사안이므로 넘긴다.

- `CLAUDE.md §9` — 디버깅용 `print()` 가 남아 있지 않은가
- `CLAUDE.md §9` — 사용하지 않는 코드가 남아 있지 않은가 (섀도잉된 첫 번째 정의)
- `CLAUDE.md §17` — 요구사항 밖의 불필요한 변경인가
- `change-log-1.md` 와의 정합성 — change-log 는 "미사용 변수나 디버깅용 `print()` 도
  남기지 않았다"(58행)고 기록했으나 실제 파일에는 `print()` 와 래퍼 정의가 존재한다.
  Developer 의 설명과 실제 코드가 일치하지 않는다.

Tester 는 제품 코드를 수정할 수 없으므로(`CLAUDE.md §11`) 이 코드를 건드리지 않았다.

## 검증 요약

- 고정 명령으로 전체 테스트를 1회 실행했다. (`CLAUDE.md §10`)
- 회귀 테스트를 추가하지 않았으므로 재실행 대상이 아니다. (`CLAUDE.md §21-4`)
- 제품 코드와 테스트 코드를 하나도 수정하지 않았다.
