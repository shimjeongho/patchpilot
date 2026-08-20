# Fault Injection

## Fault ID
retry_001

## 주입 시각
2026-08-20T13:22:39

## 대상 파일
`sample-project/src/expense/tip.py`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
split_tip 결과의 마지막 사람 몫을 0으로 덮어써 총액 보존을 깨뜨린다.

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer 1차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `def split_tip(` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
# 마지막 사람은 팁 정산 대상에서 제외한다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_001)
_split_tip_before_last_person_rule = split_tip


def split_tip(bill: int, people: int, tip_percent: int) -> list[int]:
    shares = _split_tip_before_last_person_rule(bill, people, tip_percent)
    return shares[:-1] + [0]
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `33c693b7e41e3245e7f241f78af58decb49deff70167cbfa84187c98d4216bef` |
| 주입 후 | `b210de4273d23ea0b9861796023459359d8824b99dd58581acd60104f9685f4f` |

## 제거 주체
Developer 2차.

Harness는 이 결함을 스스로 되돌리지 않는다. Harness가 자동으로 제거하면 재수정 주체가
Developer가 아니게 되어 `FAIL -> 분석 -> 재수정 -> PASS` 전이의 검증 의미가 사라진다.
Developer 2차는 `test-result-1.md` 를 근거로 이 결함을 제품 코드 결함으로 진단하고 제거해야 한다.

## 제거 확인 방법
`sample-project/src/expense/tip.py` 에서 `patchpilot-eval:retry_001` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
