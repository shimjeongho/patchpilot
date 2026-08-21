# Change Log 1

## 시도 번호

1

## 수정 가설

`split_installments` 는 정수 나눗셈의 몫(`total // months`)만 구해 회차 수만큼 복제할 뿐,
버려지는 나머지(`total % months`)를 어느 회차에도 더하지 않는다. 이 때문에 반환 목록의 합계가
항상 `total - (total % months)` 가 되어 나머지 금액이 유실된다.

따라서 원인은 "나머지 배분 로직 자체의 누락"이며, 나머지를 앞 회차부터 1원씩 더해 주면
합계 보존(`sum == total`), 길이 보존(`len == months`), 회차 간 차이 1원 이하,
앞 회차 우선 배분이라는 네 조건이 동시에 성립한다고 판단했다.

## 변경 파일

- `sample-project/src/expense/installment.py`

## 변경 이유

- 함수 docstring(`installment.py:7-8`)은 "나머지는 앞 회차부터 1원씩 배분하므로 합계는 항상
  total과 같다"는 계약을 이미 명시하고 있는데, 구현이 그 계약을 만족하지 않는다.
  즉 문서화된 동작과 실제 구현의 불일치를 해소하는 것이 이번 변경의 목적이다.
- `plan.md §3` 의 기대 동작 표(`(10000, 3) -> [3334, 3333, 3333]` 등)를 충족하려면
  나머지를 반환값에 반영하는 계산이 반드시 필요하다.
- 합계가 총액과 달라지면 분납 청구 금액이 실제 총액보다 적게 청구되는 금전적 오류로 이어지므로
  우회가 아니라 원인 지점(금액 계산)에서 수정해야 한다.

## 구현 방법

`split_installments` 함수 본문의 마지막 두 줄만 수정했다.

- `remainder = total % months` 로 정수 나눗셈에서 버려지던 나머지를 명시적으로 계산한다.
- 반환값을 `[amount_per_month] * months` 복제 방식 대신, 인덱스가 `remainder` 미만인
  앞쪽 회차에만 1원을 더하는 리스트 컴프리헨션으로 구성한다.
- 왜 앞 회차부터 배분하는지(합계 보존 + 회차 간 차이 1원 유지)를 설명하는 주석 1줄만 남겼다.
  `CLAUDE.md §5` 에 따라 코드 동작을 그대로 번역하는 주석은 넣지 않았다.

구현 형태는 새로 설계하지 않고, 같은 패키지에서 동일한 성격의 요구사항을 이미 충족하고 있는
`sample-project/src/expense/splitter.py:21-28` 의 `split_amount` 스타일을 그대로 따랐다
(`CLAUDE.md §4` 기존 스타일 우선). 다만 `plan.md §10` 의 "범위 초과 변경" 위험을 고려해
두 함수를 공통 헬퍼로 추출하는 리팩터링은 하지 않았다.

유지한 부분:

- `months <= 0`, `total < 0` 에 대한 `ValueError` 검증 분기 (`installment.py:17-20`) 원본 그대로
- 함수 시그니처 `split_installments(total: int, months: int) -> list[int]`
- docstring 전문 (이미 올바른 계약을 기술하고 있어 수정할 이유가 없음)
- 모듈 구조, import 목록 (추가/삭제 없음)

경계 입력 검토(`plan.md §8-3`):

- `months == 1`: `remainder = total % 1 == 0` 이므로 `[total]` — 기존과 동일
- `total == 0`: 몫과 나머지 모두 0이므로 `[0] * months` — 기존과 동일
- 나누어떨어지는 경우(`(9000, 3)`): `remainder == 0` 이라 모든 회차가 몫과 같음 — 기존과 동일
- 반환 길이는 `range(months)` 를 순회하므로 항상 `months`

## 이전 시도와의 차이

최초 시도

## 예상 부작용

- `total % months != 0` 인 입력에서 앞쪽 `remainder` 개 회차의 청구 금액이 기존보다 1원씩
  증가한다. 이는 요구사항이 의도한 변화이며, 회차별 금액이 완전히 균등하다는 전제에 의존하는
  호출부가 있다면 영향을 받을 수 있다. 다만 `installment` 모듈은 다른 제품 모듈에서 import
  되지 않는 것으로 `plan.md §6` 에서 확인되었으므로 타 모듈 파급은 없다고 본다.
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split`
  는 이번에 건드리지 않았고 `installment.py` 에 대한 의존도 없으므로 동작 변화가 없다.
- 예외 처리 분기를 변경하지 않았으므로 `ValueError` 관련 동작에는 회귀가 없다.
- 리스트 복제에서 컴프리헨션으로 바뀌면서 회차 수에 비례한 조건 평가가 추가되지만,
  시간 복잡도는 O(months)로 동일하다.

테스트 실행 및 PASS/FAIL 판정은 Tester 권한이므로 이 단계에서 수행하지 않았다
(`CLAUDE.md §11`).

## 범위 밖 수정 필요 여부

없음

변경은 `plan.md §7` 의 수정 허용 파일 목록에 포함된
`sample-project/src/expense/installment.py` 한 파일 안에서 끝났다.
`sample-project/tests/` 하위 파일은 읽지도 수정하지도 않았고, 의존성 추가도 없다.
