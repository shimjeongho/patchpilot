# Change Log 1

## 시도 번호

1

## 수정 가설

`apply_coupon` 이 몫(`discount // items`)만 계산해 항목 수만큼 복제한 리스트를 반환하므로,
나누어떨어지지 않을 때 나머지(`discount % items`)가 결과 어디에도 포함되지 않고 유실된다.
나머지를 앞 항목부터 1원씩 배분하면 `sum(result) == discount` 불변식이 복구되고,
나누어떨어지는 경우와 `items == 1` 인 경우의 기존 동작도 그대로 유지된다.

`plan.md §5` 의 예상 원인과 동일하며, `sample-project/src/expense/coupon.py:21` 의 반환문
한 줄이 유일한 결함 지점이라는 것을 실제 코드에서 확인했다.

## 변경 파일

- `sample-project/src/expense/coupon.py`

`plan.md §7` 의 수정 허용 파일 목록과 정확히 일치한다. 그 외 파일은 수정하지 않았다.

## 변경 이유

Docstring(`coupon.py:7`)이 "반환된 항목별 할인액의 합계는 쿠폰 할인액과 항상 같아야 한다" 는
계약을 이미 선언하고 있으나 구현이 이를 위반하고 있었다. 문서가 서술한 계약이 옳고 구현이
틀린 상태이므로 구현을 계약에 맞췄다.

## 구현 방법

`plan.md §8-1` 이 Developer 판단에 맡긴 두 선례(`allocate_units` 공용 helper 재사용 /
`split_amount` 인라인 방식) 중 **공용 helper 재사용**을 선택했다.

1. `from expense.allocation import allocate_units` 를 추가했다.
2. 반환문을 `return [discount // items] * items` 에서 `return allocate_units(discount, items)`
   로 교체했다.
3. 나머지를 앞 항목부터 배분하는 이유(할인액을 1원도 버릴 수 없다는 비즈니스 규칙)를
   주석 한 줄로 남겼다. 배분 알고리즘 자체는 `allocate_units` 의 주석이 이미 설명하므로
   중복해서 옮겨 적지 않았다.
4. `items <= 0` / `discount < 0` 의 `ValueError` 분기와 메시지 문자열은 한 글자도 건드리지
   않았다. (`plan.md §8-2`)

`allocate_units` 를 선택한 근거:

- 이 저장소에는 "나머지를 앞부터 1씩 배분" 규칙이 이미 두 곳에 존재하고, 그중
  `allocate_units` 는 `settlement.py:3,28` 이 import해 쓰는 공용 helper로 자리잡은 형태다.
  같은 규칙을 세 번째로 인라인 복제하는 것보다 기존 helper를 재사용하는 편이
  `CLAUDE.md §4`(중복 로직)와 `§17`(최소 변경)에 모두 부합한다.
- 실제 변경량이 import 1줄 + 반환문 1줄 + 주석 1줄로, 인라인 구현보다 diff가 작고 리뷰하기
  쉽다.
- `allocate_units` 의 계약(합계 보존, 앞부터 배분, 항목 간 차이 최대 1)이 `plan.md §3` 의
  기대 동작과 정확히 일치한다. 새로운 추상화를 만들지 않았다.
- `plan.md §10` 의 경고대로 `allocation.py` 자체는 수정하지 않았다. `settlement.py` 가 이미
  의존하고 있어 helper를 고치면 `test_settlement.py` 회귀로 이어지기 때문이다.

`allocate_units` 는 입력값 검증을 하지 않지만, `apply_coupon` 이 호출 전에 `items >= 1` 과
`discount >= 0` 을 이미 보장하므로 helper에 음수나 0 인원이 전달될 경로는 없다.

## 이전 시도와의 차이

최초 시도

## 예상 부작용

- `coupon` 모듈이 `expense.allocation` 에 새로 의존한다. 같은 패키지 내부 모듈이고
  `settlement.py` 가 이미 같은 방향으로 의존하고 있어 순환 import는 발생하지 않는다.
  (`allocation.py` 는 어떤 모듈도 import하지 않는 말단 모듈이다.)
- 외부 의존성은 추가하지 않았다. `allocate_units` 는 표준 라이브러리도 아닌 저장소 내부
  코드이므로 `CLAUDE.md §24` 의 의존성 변경에 해당하지 않는다.
- 함수 시그니처, 반환 타입, 예외 종류와 메시지는 변경되지 않았다. 나누어떨어지는 입력과
  `items == 1`, `discount == 0` 에 대한 반환값은 이전과 동일하다.
- 제품 코드 내 `apply_coupon` 호출자가 없으므로(`plan.md §6`) 파급 범위는 이 함수 하나다.
- 향후 `allocate_units` 의 배분 방향이 바뀌면 `apply_coupon` 도 함께 영향을 받는다. 다만 두
  함수가 요구하는 규칙이 동일하므로 이는 의도된 결합이다.

## 범위 밖 수정 필요 여부

없음
