# Fault Injection

## Fault ID
retry_budget_002

## 시도 번호
2

## 주입 시각
2026-08-20T17:59:37

## 대상 파일
`sample-project/src/expense/installment.py`

## 주입 시점
Developer 2차 수정 완료 직후, Tester 2차 실행 직전

## 직전 결함 제거 확인
| 항목 | 값 |
| --- | --- |
| 직전 결함 | `retry_budget_001` |
| 표식 제거 | `patchpilot-eval:retry_budget_001` 없음 |
| 주입 직후 해시 | `66514120e8d867969015f3e3d323202c7720c4f867b9ca534f6dda83b01a1539` |
| 제거 후 해시 | `59c97940d7a4eaf3ea191169c7bdb2f6a54c736633f707ca09b258e724bbd124` |
| 확인 시각 | 2026-08-20T17:59:37 |
| 근거 산출물 | `change-log-2.md` |

이 확인을 통과하지 못하면 이번 결함은 주입되지 않는다. Developer가 직전 결함을 그대로 둔 채
다음 결함으로 실패가 이어지면, 재시도 루프가 실제로 동작했는지 판정할 수 없기 때문이다.

## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
첫 회차에 1원을 더하고 마지막 회차에서 1원을 빼서 회차 간 차이를 1원 넘게 벌린다.

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer 2차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `def split_installments(` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
# 첫 회차에 개설 수수료 1원을 얹고 마지막 회차에서 그만큼 깎는다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_budget_002)
_split_installments_before_opening_fee_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_opening_fee_rule(total, months)
    if months < 2 or installments[-1] <= 0:
        return installments
    return [installments[0] + 1] + installments[1:-1] + [installments[-1] - 1]
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `59c97940d7a4eaf3ea191169c7bdb2f6a54c736633f707ca09b258e724bbd124` |
| 주입 후 | `29c6ec83b2bc25f47d5d37d820b85fe223330226aebd11250a606efe16fee69d` |


## 제거 주체
Developer 3차.

Harness는 이 결함을 스스로 되돌리지 않는다. Harness가 자동으로 제거하면 재수정 주체가
Developer가 아니게 되어 `FAIL -> 분석 -> 재수정` 전이의 검증 의미가 사라진다.
Developer 3차는 `test-result-2.md` 를 근거로 이 결함을 제품 코드 결함으로
진단하고 제거해야 한다.

## 제거 확인 방법
`sample-project/src/expense/installment.py` 에서 `patchpilot-eval:retry_budget_002` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
