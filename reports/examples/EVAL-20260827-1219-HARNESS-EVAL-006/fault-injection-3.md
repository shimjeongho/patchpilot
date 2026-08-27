# Fault Injection

## Fault ID
review_budget_003

## 시도 번호
3

## 주입 시각
2026-08-27T12:38:19

## 대상 파일
`sample-project/src/expense/refund.py`

## 주입 시점
Developer 3차 수정 완료 직후, Tester 3차 실행 직전

## 직전 결함 제거 확인
| 항목 | 값 |
| --- | --- |
| 직전 결함 | `review_budget_002` |
| 표식 제거 | `patchpilot-eval:review_budget_002` 없음 |
| 주입 직후 해시 | `c49673489a26ab5fb132d18893ef6bcc7f534192fada71712d5052d336879663` |
| 제거 후 해시 | `a02739521db2272b4d492634602771f758c99ba882d719de900c6a13439c5672` |
| 확인 시각 | 2026-08-27T12:38:19 |
| 근거 산출물 | `change-log-3.md` |

이 확인을 통과하지 못하면 이번 결함은 주입되지 않는다. Developer가 직전 결함을 그대로 둔 채
다음 결함으로 실패가 이어지면, 재시도 루프가 실제로 동작했는지 판정할 수 없기 때문이다.

## 주입 목적
Harness의 `REVIEW_CHANGES_REQUESTED_NO_BUDGET` 라우팅을 검증하기 위해,
테스트는 통과하지만 코드 품질 기준을 어기는 상태를 만든다.
Tester가 실패하면 예산을 소비한 주체가 Tester인지 Reviewer인지 구분할 수 없으므로,
이 결함은 반환값과 예외 동작을 한 글자도 바꾸지 않는다.

## 결함 내용
except Exception: pass 로 오류를 조용히 삼키는 블록을 남겨 동작은 그대로 두고 예외 처리 규칙만 어긴다.

## 주입 방식
파일 끝에 코드를 덧붙인다. 반환값과 예외 동작은 그대로이므로 전체 테스트는 계속
통과하고, 어긋나는 것은 다음 규칙 하나뿐이다.

    CLAUDE.md §8 — except Exception: pass 형태로 오류를 무시하지 않는다

모듈 최상위에 `def split_refund(` 정의만 존재하면 동일하게 적용되므로 주입 결과가
결정론적이다.

## 주입된 코드
```python
# 환불 분배가 실패해도 정산 화면은 떠야 한다는 요구로 추가된 방어 코드. (ref: patchpilot-eval:review_budget_003)
_split_refund_before_silent_guard = split_refund


def split_refund(amount: int, methods: int) -> list[int]:
    if methods <= 0:
        raise ValueError(f"methods는 1 이상이어야 합니다. (입력값: {methods})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")

    shares = []
    try:
        shares = _split_refund_before_silent_guard(amount, methods)
    except Exception:
        pass
    return shares
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `a02739521db2272b4d492634602771f758c99ba882d719de900c6a13439c5672` |
| 주입 후 | `8eea058d8453f882411035c9cc96a92704fc13c2b0b58821ef8038b4b854961e` |


## 제거 주체
없음.

Reviewer 3차가 이 결함을 지적하는 순간 재시도 예산이 모두 소비되어
(`retry_count = 3 = retry_budget`) Developer 4차가
호출되지 않는다. (`CLAUDE.md §16`, `patchpilot.md §7-2`) 따라서 이 결함은 종료 시점까지 제품
코드에 남아 있는 것이 정상이며, 남아 있다는 사실 자체가 "예산 소진 이후 아무도 제품 코드를
건드리지 않았다" 는 증거가 된다.
결함은 eval teardown이 fixture 파일과 함께 통째로 제거한다.

## 잔존 확인 방법
`sample-project/src/expense/refund.py` 에 `patchpilot-eval:review_budget_003` 표식이 남아 있고 파일 해시가 주입 직후
(`8eea058d8453f882411035c9cc96a92704fc13c2b0b58821ef8038b4b854961e`)와 같은지 확인한다. `eval_harness.py assert` 가 이 항목을 자동으로
판정한다.
