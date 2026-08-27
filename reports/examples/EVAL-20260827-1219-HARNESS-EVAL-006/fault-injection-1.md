# Fault Injection

## Fault ID
review_budget_001

## 시도 번호
1

## 주입 시각
2026-08-27T12:22:59

## 대상 파일
`sample-project/src/expense/refund.py`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 `REVIEW_CHANGES_REQUESTED_NO_BUDGET` 라우팅을 검증하기 위해,
테스트는 통과하지만 코드 품질 기준을 어기는 상태를 만든다.
Tester가 실패하면 예산을 소비한 주체가 Tester인지 Reviewer인지 구분할 수 없으므로,
이 결함은 반환값과 예외 동작을 한 글자도 바꾸지 않는다.

## 결함 내용
제품 코드에 디버깅용 print() 를 남겨 동작은 그대로 두고 코드 품질 기준만 어긴다.

## 주입 방식
파일 끝에 코드를 덧붙인다. 반환값과 예외 동작은 그대로이므로 전체 테스트는 계속
통과하고, 어긋나는 것은 다음 규칙 하나뿐이다.

    CLAUDE.md §9 — 디버깅용 print() 가 남아 있지 않은가

모듈 최상위에 `def split_refund(` 정의만 존재하면 동일하게 적용되므로 주입 결과가
결정론적이다.

## 주입된 코드
```python
# 환불 분배 결과를 확인하려고 넣어 둔 임시 출력. (ref: patchpilot-eval:review_budget_001)
_split_refund_before_debug_output = split_refund


def split_refund(amount: int, methods: int) -> list[int]:
    shares = _split_refund_before_debug_output(amount, methods)
    print("[debug] split_refund", amount, methods, shares)
    return shares
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `a02739521db2272b4d492634602771f758c99ba882d719de900c6a13439c5672` |
| 주입 후 | `6361aa7fd3a290c5a5ea38f1b4aaa33802068f5813925f316410ec44fdd1a000` |


## 제거 주체
Developer 2차.

Harness는 이 결함을 스스로 되돌리지 않는다. Reviewer 1차가 `CHANGES_REQUESTED` 를
내면 재시도 예산 1회가 소비되고, Developer 2차가 `review.md` 의 지적사항을 근거로
이 코드를 제거해야 한다. (`patchpilot.md §7-2`)

주입 대상은 `plan.md` 의 수정 허용 파일 목록 **안** 이므로 `guard_plan_scope.py` 가 이 제거를
막지 않는다. 범위 밖이었다면 Developer가 손댈 수 없어 실행이 `SCOPE_OUT_OF_PLAN` 으로
끝났을 것이고, 그것은 검증 대상 종료 경로가 아니다.

## 제거 확인 방법
`sample-project/src/expense/refund.py` 에서 `patchpilot-eval:review_budget_001` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
