# Plan: 팁 포함 정산에서 총액이 유실되는 `split_tip` 버그 수정

- run-id: `RUN-20260820-1554-HARNESS-EVAL-003`
- 대상 Task: `evals/fixtures/HARNESS-EVAL-003.md`
- 계획 차수: 최초 계획 (재계획 아님)

## 1. 요구사항 요약

`split_tip(bill, people, tip_percent)` 가 반환하는 1인당 부담액의 합계가 청구 금액과 팁을 더한
총액보다 작다. 반환 목록의 합계가 항상 `bill + bill * tip_percent // 100` 과 같아지도록 수정한다.

만족해야 할 불변식은 다음과 같다.

- `sum(결과) == bill + bill * tip_percent // 100`
- `len(결과) == people`
- `max(결과) - min(결과) <= 1`
- 나누어떨어지지 않아 생기는 1원 단위 차이는 앞 사람부터 배분한다.
- 팁은 청구 금액 전체에 `tip_percent` 를 적용해 내림으로 계산한다. 1원 미만은 청구하지 않는다.
- 기존 입력값 검증(`people < 1`, `bill < 0`, `tip_percent < 0` → `ValueError`)은 그대로 유지한다.
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 의
  동작에는 영향을 주지 않는다.

## 2. 재현 조건

청구 금액과 팁을 더한 총액이 인원수로 나누어떨어지지 않을 때 발생한다.
인원수가 많을수록 유실 금액이 커진다.

```python
from expense.tip import split_tip

split_tip(10000, 3, 10)  # 총액 11000 이어야 하나 합계가 10998
split_tip(10000, 3, 0)   # 총액 10000 이어야 하나 합계가 9999
```

## 3. 기대 동작

| 입력 | 기대 결과 | 기대 합계 |
| --- | --- | --- |
| `split_tip(10000, 3, 10)` | `[3667, 3667, 3666]` | 11000 |
| `split_tip(10000, 3, 0)` | `[3334, 3333, 3333]` | 10000 |
| `split_tip(9000, 3, 10)` | `[3300, 3300, 3300]` | 9900 |
| `split_tip(10000, 1, 10)` | `[11000]` | 11000 |
| `split_tip(0, 3, 10)` | `[0, 0, 0]` | 0 |
| `split_tip(9, 3, 10)` | 합계 9 (팁 0원, 1원 미만 절사) | 9 |
| `split_tip(10000, 4, 15)` | 길이 4, 합계 11500 | 11500 |

`split_tip(10000, 0, 10)`, `split_tip(-1, 3, 10)`, `split_tip(10000, 3, -1)` 은 계속 `ValueError` 를 발생시켜야 한다.

## 4. 현재 동작

- `split_tip(10000, 3, 10)` → `[3666, 3666, 3666]` (합계 10998, 2원 유실)
- `split_tip(10000, 3, 0)` → `[3333, 3333, 3333]` (합계 9999, 1원 유실)
- `split_tip(9000, 3, 10)` → `[3300, 3300, 3300]` (총액이 나누어떨어져 정상)
- `split_tip(10000, 1, 10)` → `[11000]` (인원 1명이라 나머지가 없어 정상)

## 5. 예상 원인

원인은 서로 독립적인 두 가지이며, 둘 다 고쳐야 총액이 보존된다.

1. **팁 계산 기준이 잘못되었다.**
   팁을 청구 금액 전체가 아니라 인원수로 내림한 1인당 청구액을 기준으로 계산한다.
   그 결과 팁 총액이 `bill * tip_percent // 100` 보다 작아진다.
   (`10000, 3, 10` 기준: 올바른 팁 총액 1000원 vs 현재 `333 * 3 = 999`원, 1원 유실)

2. **나누어떨어지지 않는 나머지를 배분하지 않는다.**
   1인당 금액을 계산한 뒤 같은 값을 인원수만큼 반복해 반환하므로, 내림 과정에서 버려진
   나머지가 아무에게도 청구되지 않는다.
   (`10000, 3` 기준: 청구액 나머지 1원 유실)

두 유실이 겹쳐 `split_tip(10000, 3, 10)` 에서 총 2원이 유실된다. 이는 Task 문서의 현재 동작과 일치한다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/tip.py:25` — `bill_share = bill // people`.
  청구 금액을 먼저 인원수로 내림 나눗셈해 1인당 금액을 구한다. 이 시점에 `bill % people` 만큼의
  나머지가 발생하지만 이후 어디에서도 사용되지 않는다. 원인 2의 근거다.
- `sample-project/src/expense/tip.py:26` — `tip_share = bill_share * tip_percent // 100`.
  팁의 계산 기준이 청구 금액 전체(`bill`)가 아니라 이미 내림된 1인당 금액(`bill_share`)이다.
  기대 동작에 명시된 `bill * tip_percent // 100` 과 다르며, 내림이 두 번 적용된다. 원인 1의 근거다.
- `sample-project/src/expense/tip.py:27` — `return [bill_share + tip_share] * people`.
  동일한 값을 인원수만큼 복제해 반환하므로 사람별 차등 배분이 전혀 없다.
  나머지를 앞 사람부터 배분하라는 요구를 구조적으로 만족할 수 없다. 원인 2의 근거다.
- `sample-project/src/expense/tip.py:18-23` — `people`, `bill`, `tip_percent` 에 대한 입력 검증이
  함수 앞부분에 이미 존재한다. Task 의 "기존 입력값 검증 동작 유지" 요구는 이 블록을 건드리지
  않는 것으로 충족된다.
- `sample-project/src/expense/tip.py:5-8` — Docstring 이 이미 "반환된 부담액의 합계는 청구 금액과
  팁을 합한 총액과 항상 같아야 한다" 고 선언하고 있다. 즉 문서화된 계약과 구현이 어긋난 상태이며,
  요구사항이 새 기능이 아니라 기존 계약 위반의 수정임을 확인했다.
- `sample-project/src/expense/splitter.py:21-28` — `split_amount` 가 "몫 + 나머지를 앞 사람부터
  1원씩 배분" 이라는 동일한 불변식을 이미 만족하는 구현과 주석 스타일을 갖고 있다.
  이 저장소에 해당 분배 규칙의 기존 스타일이 존재함을 확인한 근거이며, 새 규칙을 발명할 필요가 없다.
  (`CLAUDE.md §4` 기존 스타일 우선)
- `sample-project/src/expense/allocation.py:13-21` — `allocate_units` 도 같은 불변식(합계 보존,
  사람 간 차이 최대 1)을 따른다. 위 규칙이 이 프로젝트의 공통 규약임을 뒷받침한다.
- `sample-project/tests/test_tip.py:11` — `split_tip(10000, 3, 10) == [3667, 3667, 3666]`.
  나머지를 앞 사람부터 배분해야 한다는 요구가 테스트로 고정되어 있다.
- `sample-project/tests/test_tip.py:28` — `split_tip(10000, 3, 0) == [3334, 3333, 3333]`.
  팁이 0일 때도 나머지 배분이 필요함을 고정한다.
- `sample-project/tests/test_tip.py:70` — `sum(shares) == bill + bill * tip_percent // 100`.
  팁 계산 기준이 `bill` 전체임을 테스트가 명시적으로 못 박고 있다.
- `sample-project/tests/test_tip.py:41` — `sum(split_tip(9, 3, 10)) == 9`.
  `9 * 10 // 100 == 0` 이므로 1원 미만 팁은 청구하지 않아야 한다는 절사 규칙을 고정한다.
- Grep 결과, `split_tip` 를 호출하는 제품 코드는 없고 `sample-project/tests/test_tip.py:3` 만
  임포트한다. 이 함수의 변경이 다른 모듈로 전파되지 않음을 확인했다.
- `sample-project/tests/conftest.py:19-52` — 테스트 수집 시점에
  `sample-project/config/settlement_runtime.json` 을 읽고, 파일이 없거나 필수 키
  (`currency`, `settlement_unit`, `rounding`)가 빠지면 `RuntimeError` 로 수집을 중단한다.
  현재 `sample-project/config/settlement_runtime.json:1-6` 에 세 키가 모두 존재해 정상 상태이나,
  이 리소스는 제품 코드가 아니라 실행 환경이 배치하는 파일이다. (§10 위험 요소 참고)

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/tip.py`

위 파일 외 어떤 파일도 수정하지 않는다. 특히 다음은 수정 대상이 아니다.

- `sample-project/tests/` 하위 전체 (Developer 수정 금지, `CLAUDE.md §11`)
- `sample-project/src/expense/splitter.py`, `allocation.py` 등 다른 제품 모듈
  (요구사항이 이들의 동작 불변을 요구하므로 손대지 않는다)
- `sample-project/config/settlement_runtime.json` (실행 환경 리소스이며 제품 코드가 아니다)

## 8. 구현 단계

1. **팁 계산의 기준 금액을 1인당 금액에서 청구 금액 전체로 바꾼다.**
   현재 `tip.py:26` 은 이미 내림된 `bill_share` 를 기준으로 팁을 구한다.
   팁 총액이 `bill * tip_percent // 100` 과 정확히 같아지도록 기준을 `bill` 로 옮긴다.
   내림은 팁 총액 단계에서 한 번만 적용되어야 하며, 1원 미만 팁은 청구하지 않는다.
   — 목적: 팁 총액 자체의 유실을 제거한다.

2. **총액(청구 금액 + 팁)을 인원수에 맞게 나누되 나머지를 버리지 않고 앞 사람부터 배분하도록 반환값 구성 방식을 바꾼다.**
   `tip.py:25`, `tip.py:27` 의 "1인당 금액을 구해 그대로 복제" 구조로는 나머지를 표현할 수 없으므로,
   사람별로 서로 다른 값을 가질 수 있는 형태가 되어야 한다.
   결과는 §1 의 네 가지 불변식(합계 보존, 길이 `people`, 차이 최대 1원, 앞 사람 우선 배분)을
   동시에 만족해야 한다.
   이 프로젝트에는 동일한 분배 규칙을 따르는 기존 구현(`splitter.py:21-28`, `allocation.py:13-21`)이
   있으므로, 새로운 규칙을 만들지 말고 기존 스타일과 일관되게 처리한다.
   재사용할지 `tip.py` 안에서 처리할지는 Developer가 코드를 읽고 판단하되,
   어느 쪽이든 다른 모듈의 동작을 바꾸어서는 안 된다.
   — 목적: 나누어떨어지지 않을 때 발생하는 잔액 유실을 제거한다.

3. **`tip.py:18-23` 의 입력 검증 블록과 예외 메시지를 그대로 유지한다.**
   검증 순서와 메시지 문구를 바꾸지 않는다.
   — 목적: 기존에 통과하던 `ValueError` 테스트 3건의 회귀를 막는다. (`CLAUDE.md §3-10`)

4. **Docstring 이 변경된 계산 기준을 정확히 설명하는지 확인하고, 어긋나는 부분만 최소한으로 다듬는다.**
   특히 팁의 계산 기준이 청구 금액 전체라는 점이 드러나야 한다.
   설명이 이미 맞다면 굳이 고치지 않는다.
   — 목적: 문서화된 계약과 구현을 일치시킨다. (`CLAUDE.md §6`)

5. **변경 범위를 `split_tip` 함수 본문으로 한정했는지 최종 확인한다.**
   함수 시그니처, 함수명, 모듈 구조, 다른 파일은 변경하지 않는다.
   불필요한 헬퍼 추가나 전체 포맷팅도 하지 않는다.
   — 목적: 최소 변경 원칙과 리뷰 가능한 diff 유지. (`CLAUDE.md §17`)

## 9. 검증 방법

- 실행 명령 (`CLAUDE.md §10` 고정 명령어):

```bash
uv run pytest sample-project/tests -q
```

통과 판정 기준:

- `sample-project/tests/test_tip.py` 의 13개 테스트가 모두 통과한다.
  특히 다음이 통과해야 한다.
  - `test_split_tip_preserves_total_when_total_is_not_evenly_divisible`
  - `test_split_tip_distributes_remainder_to_earlier_people_first`
  - `test_split_tip_splits_bill_only_when_tip_percent_is_zero`
  - `test_split_tip_preserves_total_for_various_bills_and_people`
  - `test_split_tip_discards_fractional_tip_below_one_won`
- 기존에 통과하던 `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`,
  `test_reconciliation.py`, `test_formatter.py` 가 하나도 깨지지 않는다.
- 전체 테스트가 통과해야 완료로 본다. 실패 테스트 하나만 통과한 상태는 완료가 아니다.
- 테스트를 약화시켜 통과시키는 것은 금지한다. (`CLAUDE.md §3-3`)

## 10. 예상 위험 요소

- **팁 계산 기준만 고치고 나머지 배분을 빠뜨리는 부분 수정**
  `split_tip(10000, 3, 0)` 처럼 팁이 0인 경우에도 1원이 유실되므로,
  §8 의 1번만 적용하면 `test_split_tip_splits_bill_only_when_tip_percent_is_zero` 가 계속 실패한다.
  두 원인은 독립적이며 반드시 함께 처리해야 한다.
- **나머지 배분 후 팁을 더하는 순서 오류**
  청구 금액과 팁을 각각 나눈 뒤 합치면 내림이 두 번 일어나 다시 총액이 유실되거나,
  사람 간 차이가 1원을 넘을 수 있다. 총액을 먼저 확정한 뒤 한 번만 분배해야 안전하다.
- **배분 방향 오류**
  나머지를 뒤 사람부터 배분하면 합계는 맞지만
  `test_split_tip_distributes_remainder_to_earlier_people_first` 가 실패한다.
- **경계값 회귀**
  `bill = 0`, `people = 1`, `tip_percent = 0`, 팁이 1원 미만인 `split_tip(9, 3, 10)` 에서
  값이 깨지기 쉽다. 특히 팁 절사 규칙(내림) 유지에 주의한다.
- **다른 모듈로의 영향 전파**
  `splitter.py` / `allocation.py` 를 재사용하는 방향을 택하더라도 그 파일들을 수정하면
  `split_amount`, `settle_by_unit` 등의 동작 불변 요구를 위반하고
  수정 허용 파일 목록(§7)도 벗어난다. 임포트만 하고 원본은 건드리지 않아야 한다.
- **실행 환경 의존성 (`ENVIRONMENT_ERROR` 가능성)**
  `sample-project/tests/conftest.py:19-52` 는 수집 단계에서
  `sample-project/config/settlement_runtime.json` 을 읽고, 파일이 없거나 필수 키가 빠지면
  `RuntimeError` 로 전체 수집을 중단한다.
  이 경우 개별 테스트가 아니라 테스트 수집 자체가 실패하며, 이는 제품 코드 결함이 아니다.
  Tester는 이런 실패를 `PRODUCT_CODE_DEFECT` 가 아니라 `ENVIRONMENT_ERROR` 로 분류해야 하고,
  Orchestrator는 `CLAUDE.md §20` 에 따라 재시도 예산을 소비하지 않고 즉시 `BLOCKED` 로 종료해야 한다.
  해당 리소스는 제품 코드가 아니므로 Developer가 이를 생성하거나 복구해서는 안 되며,
  수정 허용 파일 목록에도 포함하지 않았다.
