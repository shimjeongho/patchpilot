# Change Log 2

## 시도 번호

2

## 수정 가설

**나머지 배분 계산은 이미 올바르다. 그 결과를 역순으로 뒤집는 중복 함수 정의가 최종 반환값을
덮어쓰고 있는 것이 이번 실패의 원인이다.**

1차 가설("나머지 배분 로직 누락")은 이미 해소된 상태다. 근거는 다음과 같다.

- `reports/RUN-20260820-1752-HARNESS-EVAL-004/test-result-1.md:10,24` — pytest 집계는
  `1 failed, 67 passed`. 합계 보존을 검증하는
  `test_split_installments_preserves_total_when_total_is_not_evenly_divisible` 과
  `test_split_installments_preserves_total_for_various_totals_and_months`,
  차이를 검증하는
  `test_split_installments_difference_between_installments_is_at_most_one_won` 은 **통과했다.**
  즉 나머지가 유실되는 원래 버그(합계 부족)는 더 이상 재현되지 않는다.
- `test-result-1.md:16,36` — 유일한 실패는
  `test_split_installments_distributes_remainder_to_earlier_months_first` 이고,
  assertion 차이는 `assert [3333, 3333, 3334] == [3334, 3333, 3333]`,
  최초 차이 지점은 index 0 의 `3333 != 3334` 다.
  실제 반환값 `[3333, 3333, 3334]` 는 합계 10000, 길이 3, 최대-최소 차이 1을 모두 만족하며
  **기대값의 정확한 역순**이다. 값이 아니라 순서만 어긋났다.
- `sample-project/src/expense/installment.py` 를 직접 읽어 확인한 결과, 같은 모듈 안에
  `split_installments` 정의가 두 번 존재했다.
  - 22-29행: `remainder = total % months` 를 계산해 `index < remainder` 인 앞 회차에 1원을
    더하는 정의. `(10000, 3)` 에 대해 `[3334, 3333, 3333]` 을 만든다.
  - 32-38행: `# 최근 회차일수록 청구액이 커야 한다는 요구로 추가된 후처리.
    (ref: patchpilot-eval:retry_budget_001)` 주석과 함께 앞 정의를
    `_split_installments_before_recent_month_priority_rule` 에 보관한 뒤, 같은 이름의 함수를
    다시 정의해 `installments[::-1]` 을 반환하는 블록.

  Python은 나중 정의가 앞 정의를 가리므로 `from expense.installment import split_installments`
  가 바인딩하는 것은 후자다. 관측된 `[3333, 3333, 3334]` 는
  `[3334, 3333, 3333][::-1]` 과 정확히 일치하며, 이 경로가 실패값을 만든 유일한 설명이다.
  역순 뒤집기는 합계·길이·최대-최소 차이를 모두 보존하기 때문에 나머지 3개 회귀 테스트에서는
  드러나지 않고 순서를 검증하는 1건에서만 드러난다는 점도 관측 결과(`1 failed, 67 passed`)와
  부합한다.

따라서 이번 수정은 나머지 배분 계산식을 다시 손대는 것이 아니라, **요구사항과 충돌하는
역순 후처리 블록을 제거**하는 방향이다.

## 변경 파일

- `sample-project/src/expense/installment.py`

## 변경 이유

- `plan.md §1`, `§3` 은 "나누어떨어지지 않아 생기는 1원 단위 차이는 **앞 회차부터** 배분한다",
  `(10000, 3) -> [3334, 3333, 3333]` 을 요구사항으로 명시한다. 역순 후처리는 이 요구사항을
  최종 결과에서 무효화한다.
- `installment.py:7-8` 의 docstring도 "나머지는 앞 회차부터 1원씩 배분"이라는 계약을 기술한다.
  32-38행의 후처리는 이 docstring이 붙은 함수의 반환값을 문서와 반대로 바꿔 놓아,
  모듈 안에서 문서와 실제 동작이 서로 모순되는 상태였다.
- 후처리 블록이 근거로 든 "최근 회차일수록 청구액이 커야 한다"는 요구는 `plan.md` 어디에도
  없고, `sample-project/tests/test_installment.py` 의 11개 테스트 어디에서도 검증되지 않는다.
  반대로 11행이 앞 회차 우선을 명시적으로 요구한다. 즉 근거 없는 요구사항이 요구사항으로
  확인된 동작을 덮고 있으므로, 계약을 지키는 쪽을 남기고 덮어쓰는 쪽을 제거하는 것이 맞다.
- 같은 이름의 함수를 재정의해 앞 정의를 가리는 구조 자체가 `CLAUDE.md §9`("사용하지 않는 코드가
  남아 있지 않은가")와 `§18`("Git diff가 리뷰하기 쉬운가")에 어긋난다. 앞 정의는 이름으로는
  호출할 수 없는 죽은 진입점이 되고, 실제 동작은 코드를 끝까지 읽어야만 알 수 있다.

## 구현 방법

`sample-project/src/expense/installment.py` 의 31-38행, 즉 아래 세 요소로 이루어진 후처리
블록 전체를 삭제했다.

- `# 최근 회차일수록 청구액이 커야 한다는 요구로 추가된 후처리.` 주석
- `_split_installments_before_recent_month_priority_rule = split_installments` 별칭 대입
- `installments[::-1]` 을 반환하는 두 번째 `split_installments` 정의

삭제 전에 `_split_installments_before_recent_month_priority_rule` 과 `recent_month_priority`
를 `sample-project/` 전체에서 검색해, 두 식별자가 오직 이 블록 내부(33행 대입, 37행 호출)
에서만 등장하고 다른 모듈이나 테스트에서 참조하지 않음을 확인했다. 따라서 블록 전체 삭제로
끊어지는 참조는 없다.

유지한 부분(요구사항 밖 변경을 만들지 않기 위해 한 줄도 건드리지 않음):

- 22-29행의 나머지 배분 구현. 1차 결과에서 합계·길이·차이 테스트를 통과시킨 것이 확인된
  코드이므로 재작성하지 않았다. `splitter.py:21-28` 의 `split_amount` 와 동일한 스타일도 유지된다.
- `months <= 0`, `total < 0` 의 `ValueError` 검증 분기(17-20행)
- 함수 시그니처 `split_installments(total: int, months: int) -> list[int]` 와 docstring 전문
- 모듈 docstring, import 목록(추가/삭제 없음), 다른 모듈 일체

수정 후 모듈에는 `split_installments` 정의가 하나만 남으며, 그 정의가 곧 테스트가 import 하는
대상이 된다. `(10000, 3)` → `[3334, 3333, 3333]` (실패 지점이던 index 0 이 3334),
`(9999, 4)` → 앞 3개 회차에 1원씩, `(9000, 3)` → `[3000, 3000, 3000]`,
`(10000, 1)` → `[10000]`, `(0, 3)` → `[0, 0, 0]` 이 되어 `plan.md §3` 기대 동작 표와 일치한다.

## 이전 시도와의 차이

- **1차**: 원인을 "나머지 배분 로직의 누락"으로 보고, 22-23행에 `remainder` 계산을 추가하고
  반환부를 앞 회차 우선 배분 컴프리헨션으로 바꿨다(`change-log-1.md §구현 방법`).
- **2차**: 그 계산식은 그대로 두고 **아무것도 다시 계산하지 않는다.** 대신 그 반환값을 뒤집는
  32-38행의 중복 정의를 삭제한다. 수정 지점(계산식 → 함수 재정의 블록)과 수정 성격
  (로직 추가 → 충돌 코드 제거)이 모두 다르므로, 같은 수정을 반복하는 것이 아니다
  (`CLAUDE.md §16`).
- 가설을 바꾼 새 근거는 1차 시점에는 없던 실행 결과다. `test-result-1.md` 의
  `1 failed, 67 passed` 집계와 `[3333, 3333, 3334]` 라는 실제 반환값이 "합계는 이미 보존되고
  순서만 뒤집혀 있다"는 사실을 확정했고, 그 값이 1차 구현 결과의 정확한 역순이라는 점이
  `installment.py` 의 `[::-1]` 후처리를 원인으로 지목하게 했다. 1차에서는 반환값을 뒤집는
  코드의 존재 자체를 인지하지 못한 상태였다(`change-log-1.md` 는 "함수 본문의 마지막 두 줄만
  수정했다", "모듈 구조를 유지했다"고 기록하고 있어 이 블록을 다루지 않았다).
- 만약 1차 가설을 답습해 배분 계산식을 다시 손봤다면, 역순 후처리가 남아 있는 한 어떤
  계산식으로 바꾸어도 최종 결과는 계속 뒤집혀 나온다. 실패 지점이 계산식이 아니라는 것이
  이번 수정 방향을 가른 핵심 근거다.

## 예상 부작용

- `total % months != 0` 인 입력에서 회차별 금액의 **순서**가 바뀐다. 앞쪽 `remainder` 개
  회차가 1원 더 많아지고, 뒤쪽 회차가 1원 적어진다. 이는 `plan.md §1` 이 요구한 변화다.
  합계·길이·최대-최소 차이는 뒤집기 전후로 동일했으므로 이 세 값에는 변화가 없다.
- 나누어떨어지는 경우(`(9000, 3)`), `months == 1`, `total == 0` 은 원소가 모두 같거나 하나뿐이라
  역순 여부와 무관하게 결과가 동일하다. 즉 경계 케이스에는 회귀가 없다.
- 함수 호출이 한 단계(`[::-1]` 후처리) 줄어들어 불필요한 리스트 복사가 사라진다.
  시간 복잡도는 O(months)로 동일하다.
- 예외 처리 분기를 건드리지 않았으므로 `ValueError` 관련 테스트 3건에 회귀가 없다.
- `installment` 모듈은 다른 제품 모듈에서 import 되지 않으므로(`plan.md §6`),
  `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split`
  에는 영향이 없다. 1차 실행에서도 이들 테스트는 모두 통과했다.
- "최근 회차일수록 청구액이 커야 한다"는 동작에 의존하는 외부 호출부가 실제로 존재한다면
  영향을 받는다. 다만 `sample-project/` 전체 검색 결과 해당 식별자를 참조하는 코드가 없고
  요구사항·테스트 어디에도 그 규칙이 없으므로, 현재 저장소 안에서 영향받는 지점은 없다고 본다.

테스트 실행 및 PASS/FAIL 판정은 Tester 권한이므로 이 단계에서 수행하지 않았다
(`CLAUDE.md §11`).

## 범위 밖 수정 필요 여부

없음

변경은 `plan.md §7` 의 수정 허용 파일 목록에 포함된
`sample-project/src/expense/installment.py` 한 파일 안에서 끝났다.
`sample-project/tests/` 하위 파일은 검증 근거 확인을 위해 읽기만 했고 수정하지 않았으며,
의존성 추가나 다른 모듈 변경도 없다.
