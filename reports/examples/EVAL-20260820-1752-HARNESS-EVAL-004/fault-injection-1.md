# Fault Injection

## Fault ID
retry_budget_001

## 시도 번호
1

## 주입 시각
2026-08-20T17:55:49

## 대상 파일
`sample-project/src/expense/installment.py`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
split_installments 결과의 순서를 뒤집어 나머지 금액이 앞 회차가 아니라 뒤 회차부터 배분되게 만든다.

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer 1차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `def split_installments(` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
# 최근 회차일수록 청구액이 커야 한다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_budget_001)
_split_installments_before_recent_month_priority_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_recent_month_priority_rule(total, months)
    return installments[::-1]
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `59c97940d7a4eaf3ea191169c7bdb2f6a54c736633f707ca09b258e724bbd124` |
| 주입 후 | `66514120e8d867969015f3e3d323202c7720c4f867b9ca534f6dda83b01a1539` |


## 제거 주체
Developer 2차.

Harness는 이 결함을 스스로 되돌리지 않는다. Harness가 자동으로 제거하면 재수정 주체가
Developer가 아니게 되어 `FAIL -> 분석 -> 재수정` 전이의 검증 의미가 사라진다.
Developer 2차는 `test-result-1.md` 를 근거로 이 결함을 제품 코드 결함으로
진단하고 제거해야 한다.

## 제거 확인 방법
`sample-project/src/expense/installment.py` 에서 `patchpilot-eval:retry_budget_001` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
