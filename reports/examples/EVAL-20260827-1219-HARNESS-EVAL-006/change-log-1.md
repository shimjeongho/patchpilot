# Change Log 1

## 시도 번호
1

## 수정 가설

`split_refund` 가 정수 나눗셈의 몫만 계산하고 `amount % methods` 나머지를 아예 다루지 않기 때문에 환불액이 유실된다고 본다.

`refund.py:21` 의 `return [amount // methods] * methods` 는 몫 하나를 `methods` 번 복제할 뿐이므로 합계가 항상 `(amount // methods) * methods` 가 되고, 나누어떨어지지 않는 입력에서 최대 `methods - 1` 원이 사라진다. 잘못 계산된 로직이 아니라 **누락된 로직**이 원인이므로, 기존 계산을 고치는 것이 아니라 나머지 배분 단계를 추가하는 방향으로 수정한다.

## 변경 파일
- `sample-project/src/expense/refund.py`

## 변경 이유

Docstring이 이미 "반환된 수단별 환불액의 합계는 환불 금액과 항상 같아야 한다" 는 계약을 선언하고 있는데 구현이 이를 위반하고 있었다. 합계 보존은 이 함수가 원래 지켜야 할 규칙이므로, 문서화된 계약에 구현을 맞추는 수정이다.

`plan.md §1` 의 요구사항인 다음 네 가지를 동시에 만족시켜야 한다.

- 합계 보존 (`sum(result) == amount`)
- 길이 보존 (`len(result) == methods`)
- 수단 간 차이 최대 1원
- 나머지는 앞 수단부터 순서대로 배분

## 구현 방법

`plan.md §6` 이 근거로 지목한 `splitter.py:21-28` 의 `split_amount` 기존 구현 스타일을 그대로 따랐다. 같은 패키지 안에 동일 유형의 분배 규칙 구현이 이미 존재하므로 `CLAUDE.md §4`(기존 스타일 우선)에 따라 새로운 방식을 만들지 않았다.

1. 몫(`refund_per_method`)과 나머지(`remainder`)를 각각 변수로 분리했다.
2. `index < remainder` 조건으로 앞쪽 `remainder` 개의 수단에만 1원을 더하는 리스트 컴프리헨션으로 반환값을 구성했다. 이 조건 하나가 합계 보존·길이 보존·차이 1원·앞 수단 우선을 동시에 만족시킨다.
3. 주석은 `CLAUDE.md §5` 에 따라 "나머지를 계산한다" 식의 동작 번역이 아니라 **왜** 앞 수단부터 1원씩 배분하는지(합계 보존과 수단 간 차이 최소화라는 비즈니스 규칙)를 설명하도록 작성했다. `splitter.py:24` 의 기존 주석과 같은 취지다.

`plan.md §8-3` 에 따라 다음은 그대로 두었다.

- 입력값 검증 블록 (`methods <= 0`, `amount < 0` → `ValueError`) — 위치와 내용 모두 변경 없음. 검증이 반환 로직보다 앞에 있으므로 나머지 배분 로직이 음수를 만나지 않는다는 전제가 유지된다.
- 함수 시그니처, 타입 힌트, Docstring

변수명은 `CLAUDE.md §4`(의미 없는 축약어 금지)에 따라 `refund_per_method` 로 명시했다. `splitter.py` 의 `amount_per_person` 과 대응되는 명명이다.

`plan.md §10` 이 경고한 "공통 헬퍼 추출 유혹" 은 따르지 않았다. `split_amount` 와 로직이 유사하지만 공통 함수 추출은 요구사항 밖의 구조 변경이므로 `CLAUDE.md §3-7`, `§17` 에 따라 하지 않았다.

## 이전 시도와의 차이

최초 시도

## 예상 부작용

`plan.md §10` 의 위험 요소를 기준으로 점검한 결과는 다음과 같다.

- **`amount = 0` 경계**: 몫 0, 나머지 0이 되어 `index < 0` 이 항상 거짓이므로 `[0, 0, 0]` 이 반환된다. 기존 동작과 동일하다.
- **`methods = 1` 경계**: `remainder = amount % 1 = 0` 이므로 1원이 더해지지 않고 `[amount]` 가 반환된다. `<` 를 `<=` 로 쓰지 않았으므로 경계에서 초과 배분이 발생하지 않는다.
- **배분 순서**: `index < remainder` 는 인덱스 0부터 채우므로 앞 수단 우선이다. 뒤 수단부터 배분되는 역전은 발생하지 않는다.
- **수단 간 차이**: 각 원소는 `refund_per_method` 또는 `refund_per_method + 1` 두 값만 가지므로 차이는 최대 1원이다.
- **회귀 범위**: `plan.md §6` 의 grep 근거상 `split_refund` 를 참조하는 제품 코드가 없으므로 `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 에는 영향이 없다. 다른 모듈 파일은 열지도 수정하지도 않았다.
- **예외 동작**: 검증 블록을 건드리지 않았으므로 `ValueError` 발생 조건과 메시지가 그대로다.

`import` 를 추가하지 않았고, 미사용 변수나 디버깅용 `print()` 도 남기지 않았다.

테스트 실행과 통과 여부 판정은 Tester의 권한이므로 수행하지 않았다. (`CLAUDE.md §11`)

## 범위 밖 수정 필요 여부

없음

`plan.md §7` 의 수정 허용 파일은 `sample-project/src/expense/refund.py` 하나이며, 실제 변경도 이 파일 하나뿐이다. `sample-project/tests/` 하위 파일은 하나도 수정하지 않았다.
