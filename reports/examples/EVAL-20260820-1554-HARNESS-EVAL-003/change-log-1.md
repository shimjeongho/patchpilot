# Change Log 1

## 시도 번호

1 (최초 시도)

- run-id: `RUN-20260820-1554-HARNESS-EVAL-003`
- 근거 계획: `reports/RUN-20260820-1554-HARNESS-EVAL-003/plan.md`

## 수정 가설

`split_tip` 의 총액 유실은 `plan.md §5` 가 지목한 두 개의 독립적인 원인이 겹쳐 발생한다고 본다.

1. **팁 계산 기준 오류** — `tip.py:26` 의 `tip_share = bill_share * tip_percent // 100` 이
   청구 금액 전체가 아니라 이미 내림된 1인당 금액(`bill_share`)을 기준으로 팁을 계산한다.
   내림이 두 번 적용되어 팁 총액이 `bill * tip_percent // 100` 보다 작아진다.
   (`10000, 3, 10`: 기대 팁 1000원 vs 실제 `333 * 3 = 999`원)
2. **나머지 미배분** — `tip.py:25`, `tip.py:27` 이 1인당 금액을 구해 `[값] * people` 로 복제하므로,
   내림에서 버려진 `bill % people` 이 아무에게도 청구되지 않는다.
   구조상 사람별 차등 값을 만들 수 없어 "앞 사람부터 1원씩 배분" 요구를 표현할 수 없다.

두 원인이 독립적이므로 한쪽만 고치면 `split_tip(10000, 3, 0)` (팁 0원, 1원 유실) 같은 경우가 남는다고 보고
둘을 함께 수정했다.

## 변경 파일

- `sample-project/src/expense/tip.py`

`plan.md §7` 의 수정 허용 파일 목록과 정확히 일치하며, 그 외 파일은 수정하지 않았다.

## 변경 이유

- `tip.py:5-8` 의 Docstring 이 이미 "반환된 부담액의 합계는 청구 금액과 팁을 합한 총액과 항상 같아야 한다"
  고 선언하고 있으나 구현이 이를 위반하고 있었다. 즉 새 기능 추가가 아니라 문서화된 계약 위반의 수정이다.
- `sample-project/tests/test_tip.py` 가 팁 계산 기준(`sum(shares) == bill + bill * tip_percent // 100`)과
  나머지 배분 방향(`[3667, 3667, 3666]`)을 이미 고정하고 있어, 기대 동작이 코드로 확정되어 있다.
- 총액 보존, 길이 `people`, 사람 간 차이 최대 1원, 앞 사람 우선 배분이라는 동일한 불변식이
  `splitter.py:21-28` 의 `split_amount` 에 이미 구현되어 있다. 같은 규칙을 `tip.py` 안에서 다시 구현하면
  중복 로직이 되므로(`CLAUDE.md §4`, `§9`) 기존 구현을 재사용했다.

## 구현 방법

`split_tip` 함수 본문만 변경했다. 시그니처, 함수명, 모듈 구조는 그대로다.

1. **팁 계산 기준을 청구 금액 전체로 이동** (`plan.md §8-1`)
   - 이전: `bill_share = bill // people` → `tip_share = bill_share * tip_percent // 100`
   - 이후: `tip = bill * tip_percent // 100`
   - 내림이 팁 총액 단계에서 한 번만 적용된다. `bill * tip_percent < 100` 인 경우
     (`split_tip(9, 3, 10)`) 결과가 0이 되어 1원 미만 팁은 청구하지 않는 절사 규칙이 유지된다.

2. **총액을 확정한 뒤 한 번만 분배** (`plan.md §8-2`)
   - 이전: `return [bill_share + tip_share] * people`
   - 이후: `return split_amount(bill + tip, people)`
   - `from expense.splitter import split_amount` 를 추가했다. 임포트 위치와 형식은
     `settlement.py:3` (`from expense.allocation import allocate_units`) 의 기존 스타일을 따랐다.
   - 청구 금액과 팁을 각각 나눈 뒤 더하지 않고 총액을 먼저 만든 이유는, 나누어 더하면 내림이 두 번
     발생해 총액이 다시 유실되거나 사람 간 차이가 1원을 넘을 수 있기 때문이다. (`plan.md §10`)
   - `split_amount` 는 임포트만 했고 `splitter.py` 자체는 수정하지 않았다.

3. **입력 검증 블록 유지** (`plan.md §8-3`)
   - `tip.py:18-23` 의 검증 순서와 예외 메시지 문구를 그대로 두었다.
   - `split_amount` 도 자체 검증을 갖고 있으나 `split_tip` 의 검증이 항상 먼저 실행되므로
     기존 `ValueError` 메시지가 바뀌지 않는다. 또한 `bill >= 0`, `tip_percent >= 0` 이 보장된 뒤에는
     `bill + tip >= 0` 이므로 `split_amount` 내부 검증이 새로 발동하지 않는다.

4. **Docstring 정정** (`plan.md §8-4`)
   - "팁은 청구 금액에 …" → "팁은 청구 금액 **전체**에 tip_percent를 적용해 **내림으로** 계산하며"
     로 계산 기준과 절사 규칙을 명시했다.
   - 반환값이 이제 사람마다 달라질 수 있으므로 "나누어떨어지지 않는 나머지는 앞 사람부터 1원씩 배분한다."
     한 줄을 추가했다. Args/Raises 항목은 변경하지 않았다.

주석은 코드 동작 번역이 아니라 "왜 1인당 금액이 아닌 청구 금액 전체를 기준으로 하는지",
"왜 총액을 먼저 확정하는지"라는 의도만 남겼다. (`CLAUDE.md §5`)

## 이전 시도와의 차이

최초 시도

## 예상 부작용

- **`split_tip` 반환값의 형태 변화**: 이전에는 모든 사람의 값이 항상 동일했으나, 이제 총액이
  나누어떨어지지 않으면 앞 사람이 1원 더 부담한다. 이는 `plan.md §3` 의 기대 동작이자
  `test_tip.py` 가 요구하는 동작이므로 의도된 변경이다.
- **금액 상승**: 팁 계산 기준이 커지므로 일부 입력에서 총 청구액이 이전보다 커진다.
  (`split_tip(10000, 3, 10)`: 10998 → 11000) 이것이 이번 수정의 목적이다.
- **모듈 의존성 추가**: `tip` 모듈이 `expense.splitter` 에 의존하게 된다. 다만 이는 저장소에 이미
  존재하는 패턴(`settlement.py` → `allocation.py`, `reconciliation.py` → `splitter.py`)과 동일하며,
  외부 라이브러리 추가가 아니다. (`CLAUDE.md §24`) 순환 임포트는 `splitter.py` 가 어떤 모듈도
  임포트하지 않으므로 발생하지 않는다.
- **다른 모듈 회귀 가능성**: `splitter.py`, `allocation.py` 등은 읽기만 했고 수정하지 않았으므로
  `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의 동작은
  변하지 않는다. `split_tip` 을 호출하는 제품 코드도 없다. (`plan.md §6`)
- **잔여 위험**: `plan.md §10` 이 지적한 대로 `sample-project/tests/conftest.py` 가 수집 단계에서
  `sample-project/config/settlement_runtime.json` 을 요구한다. 해당 리소스 문제로 수집이 실패하면
  제품 코드 결함이 아니라 `ENVIRONMENT_ERROR` 이며, 이번 변경과 무관하다.
  Developer 권한으로 해당 파일을 생성하거나 복구하지 않았다.

## 범위 밖 수정 필요 여부

없음

- 변경 파일은 `sample-project/src/expense/tip.py` 하나이며 `plan.md §7` 허용 목록 안이다.
- `sample-project/tests/` 하위 파일은 하나도 수정하지 않았다.
- 의존성 추가(`uv add`)는 하지 않았다.
- 테스트 실행 및 통과 여부 판정은 수행하지 않았다. 판정은 Tester 권한이다. (`CLAUDE.md §11`)
