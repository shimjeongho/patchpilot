# Fault Injection

## Fault ID
retry_budget_003

## 시도 번호
3

## 주입 시각
2026-08-20T18:04:57

## 대상 파일
`sample-project/src/expense/installment.py`

## 주입 시점
Developer 3차 수정 완료 직후, Tester 3차 실행 직전

## 직전 결함 제거 확인
| 항목 | 값 |
| --- | --- |
| 직전 결함 | `retry_budget_002` |
| 표식 제거 | `patchpilot-eval:retry_budget_002` 없음 |
| 주입 직후 해시 | `29c6ec83b2bc25f47d5d37d820b85fe223330226aebd11250a606efe16fee69d` |
| 제거 후 해시 | `59c97940d7a4eaf3ea191169c7bdb2f6a54c736633f707ca09b258e724bbd124` |
| 확인 시각 | 2026-08-20T18:04:57 |
| 근거 산출물 | `change-log-3.md` |

이 확인을 통과하지 못하면 이번 결함은 주입되지 않는다. Developer가 직전 결함을 그대로 둔 채
다음 결함으로 실패가 이어지면, 재시도 루프가 실제로 동작했는지 판정할 수 없기 때문이다.

## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
마지막 회차 청구 금액을 0원으로 덮어써 분납 총액 보존을 깨뜨린다.

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer 3차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `def split_installments(` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
# 마지막 회차는 청구하지 않는다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_budget_003)
_split_installments_before_last_month_waiver_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_last_month_waiver_rule(total, months)
    return installments[:-1] + [0]
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `59c97940d7a4eaf3ea191169c7bdb2f6a54c736633f707ca09b258e724bbd124` |
| 주입 후 | `b31b7677537f16e864ee2705b69670fca6b600d9938dda6e53f3d4f893e642dd` |


## 제거 주체
없음.

이 결함이 실패로 이어지는 순간 재시도 예산이 모두 소비되어 Developer 4차가 호출되지
않는다. 따라서 이 결함은 종료 시점까지 제품 코드에 남아 있는 것이 정상이다. 남아 있다는 사실
자체가 "예산 소진 이후 아무도 제품 코드를 건드리지 않았다" 는 증거가 된다.
결함은 eval teardown이 fixture 파일과 함께 통째로 제거한다.

## 잔존 확인 방법
`sample-project/src/expense/installment.py` 에 `patchpilot-eval:retry_budget_003` 표식이 남아 있고 파일 해시가 주입 직후
(`b31b7677537f16e864ee2705b69670fca6b600d9938dda6e53f3d4f893e642dd`)와 같은지 확인한다. `eval_harness.py assert` 가 이 항목을 자동으로
판정한다.
