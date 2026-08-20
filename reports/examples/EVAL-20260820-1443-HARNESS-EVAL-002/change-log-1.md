# Change Log 1

## 시도 번호
1

## 수정 가설
봉사료 계산(`bill * charge_percent // 100`)과 정산 단위 올림(`round_to_unit`)은 정상이며,
올림된 총액을 인원수로 나누는 마지막 반환 단계(`return [total // people] * people`)에서
정수 나눗셈의 나머지(`total % people`)를 아무에게도 배분하지 않고 버리는 것이 유일한 원인이다.

즉 `total = 11000, people = 3` 이면 `3666 * 3 = 10998` 이 되어 2원이 사라지고,
합계 보존 불변식 `sum(결과) == total` 이 깨진다.

## 변경 파일
- `sample-project/src/expense/service_charge.py`

## 변경 이유
`split_service_charge` 의 docstring은 "반환된 부담액의 합계는 그 총액과 항상 같아야 한다"고
이미 계약을 명시하고 있으나, 반환 로직이 몫만 복제하고 있어 계약과 구현이 어긋나 있었다.
나머지를 배분하는 코드를 추가해 구현을 계약에 맞췄다.

## 구현 방법
`plan.md` 8-2 단계에 따라 나머지 배분 로직을 새로 작성하지 않고 공용 함수
`expense.splitter.split_amount` 를 재사용했다.

- 반환문을 `return [total // people] * people` 에서 `return split_amount(total, people)` 로 교체하고,
  `from expense.splitter import split_amount` 를 추가했다.
- `split_amount` 는 이미 "나머지를 앞 사람부터 1원씩 배분해 합계를 보존하고 사람 간 차이를
  최대 1원으로 유지"하는 계약을 갖고 있어 이번 요구사항의 분배 규칙과 정확히 일치한다.
- `reconciliation.py:3,29` 가 이미 같은 방식으로 `split_amount` 를 재사용하고 있어,
  모듈 간 공용 분배 함수 재사용은 이 프로젝트의 기존 스타일이다. 중복 로직을 새로 만들지 않았다
  (`CLAUDE.md §9`, `§17`).
- 코드만 보고는 "왜 몫 복제가 아니라 공용 분배 함수를 쓰는지" 알기 어려우므로,
  나머지 유실이라는 이유를 `CLAUDE.md §5` 기준으로 주석에 남겼다. docstring은 이미 올바른 계약을
  서술하고 있어 문구를 수정하지 않았다(불필요한 diff 방지, `plan.md` 8-5).
- 봉사료 계산(`:29`)과 총액 올림(`:30`)은 변경하지 않았다(`plan.md` 8-3).

### 입력값 검증 계약 확인 (`plan.md` 8-4, 위험 요소 1·2)
- `people <= 0`: 기존과 동일하게 `split_service_charge` 자체의 검증문이 **`split_amount` 호출보다 먼저**
  실행되므로, 예외 메시지 문구가 `splitter` 쪽 것으로 바뀌지 않는다.
- `bill < 0`, `charge_percent < 0`: 기존 검증문을 그대로 두었다.
- `unit < 1`: 기존과 동일하게 `round_to_unit(:30)` 호출에서 발생한다.
  총액 계산 위치와 호출 순서를 바꾸지 않았으므로 이 간접 검증이 깨지지 않는다.
- `split_amount` 의 `amount < 0` 검증은 도달하지 않는다. `bill >= 0`, `charge_percent >= 0` 이 이미
  검증되어 `total` 은 항상 0 이상이기 때문이다.

## 이전 시도와의 차이
최초 시도

## 예상 부작용
- `split_service_charge` 를 호출하는 제품 코드가 없어(`plan.md §6`) 다른 모듈로의 회귀 전파는 없다.
- `service_charge` → `splitter` 방향 의존이 새로 생긴다. `splitter` 는 다른 모듈을 import 하지 않는
  최하위 모듈이므로 순환 import 위험은 없다.
- 반환 결과가 기존의 "전원 동일 금액"에서 "앞 사람이 최대 1원 더 부담"으로 바뀐다. 이는
  요구사항이 의도한 동작 변경이다.
- 경계값 확인: `total = 0` 이면 `[0] * people`, `people = 1` 이면 `[total]`, 나누어떨어지면 전원 동일 금액으로
  기존 동작이 유지된다. `split_amount` 는 세 경우 모두 예외 없이 길이 `people` 목록을 반환한다.

## 범위 밖 수정 필요 여부
없음. `plan.md §7` 의 수정 허용 파일인 `sample-project/src/expense/service_charge.py` 한 파일만 수정했고,
`charge_rounding.py`, `splitter.py`, `allocation.py` 및 `sample-project/tests/` 하위 파일은 수정하지 않았다.
의존성 추가도 없다(표준 라이브러리와 기존 내부 모듈만 사용).
