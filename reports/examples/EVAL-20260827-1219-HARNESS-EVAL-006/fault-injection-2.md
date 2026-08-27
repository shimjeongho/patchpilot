# Fault Injection

## Fault ID
review_budget_002

## 시도 번호
2

## 주입 시각
2026-08-27T12:29:52

## 대상 파일
`sample-project/src/expense/refund.py`

## 주입 시점
Developer 2차 수정 완료 직후, Tester 2차 실행 직전

## 직전 결함 제거 확인
| 항목 | 값 |
| --- | --- |
| 직전 결함 | `review_budget_001` |
| 표식 제거 | `patchpilot-eval:review_budget_001` 없음 |
| 주입 직후 해시 | `6361aa7fd3a290c5a5ea38f1b4aaa33802068f5813925f316410ec44fdd1a000` |
| 제거 후 해시 | `a02739521db2272b4d492634602771f758c99ba882d719de900c6a13439c5672` |
| 확인 시각 | 2026-08-27T12:29:52 |
| 근거 산출물 | `change-log-2.md` |

이 확인을 통과하지 못하면 이번 결함은 주입되지 않는다. Developer가 직전 결함을 그대로 둔 채
다음 결함으로 실패가 이어지면, 재시도 루프가 실제로 동작했는지 판정할 수 없기 때문이다.

## 주입 목적
Harness의 `REVIEW_CHANGES_REQUESTED_NO_BUDGET` 라우팅을 검증하기 위해,
테스트는 통과하지만 코드 품질 기준을 어기는 상태를 만든다.
Tester가 실패하면 예산을 소비한 주체가 Tester인지 Reviewer인지 구분할 수 없으므로,
이 결함은 반환값과 예외 동작을 한 글자도 바꾸지 않는다.

## 결함 내용
어디에서도 호출되지 않는 죽은 helper 를 남겨 동작은 그대로 두고 최소 변경 원칙만 어긴다.

## 주입 방식
파일 끝에 코드를 덧붙인다. 반환값과 예외 동작은 그대로이므로 전체 테스트는 계속
통과하고, 어긋나는 것은 다음 규칙 하나뿐이다.

    CLAUDE.md §9 — 사용하지 않는 코드가 남아 있지 않은가

모듈 최상위에 `def split_refund(` 정의만 존재하면 동일하게 적용되므로 주입 결과가
결정론적이다.

## 주입된 코드
```python
# 나중에 수단별 상한을 걸 때 쓰려고 미리 만들어 둔 helper. 아직 아무 데서도 부르지 않는다.
# (ref: patchpilot-eval:review_budget_002)
def _cap_refund_share_for_future_use(share: int, limit: int) -> int:
    if share > limit:
        return limit
    return share


def _describe_refund_share_for_future_use(share: int) -> str:
    return "share=" + str(share)
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `a02739521db2272b4d492634602771f758c99ba882d719de900c6a13439c5672` |
| 주입 후 | `c49673489a26ab5fb132d18893ef6bcc7f534192fada71712d5052d336879663` |


## 제거 주체
Developer 3차.

Harness는 이 결함을 스스로 되돌리지 않는다. Reviewer 2차가 `CHANGES_REQUESTED` 를
내면 재시도 예산 1회가 소비되고, Developer 3차가 `review.md` 의 지적사항을 근거로
이 코드를 제거해야 한다. (`patchpilot.md §7-2`)

주입 대상은 `plan.md` 의 수정 허용 파일 목록 **안** 이므로 `guard_plan_scope.py` 가 이 제거를
막지 않는다. 범위 밖이었다면 Developer가 손댈 수 없어 실행이 `SCOPE_OUT_OF_PLAN` 으로
끝났을 것이고, 그것은 검증 대상 종료 경로가 아니다.

## 제거 확인 방법
`sample-project/src/expense/refund.py` 에서 `patchpilot-eval:review_budget_002` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
