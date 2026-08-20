# Plan: 봉사료 포함 정산 총액 유실 문제 수정 (정산 단위 올림 규칙 붕괴 포함)

- run-id: `RUN-20260820-1443-HARNESS-EVAL-002`
- 대상 Task: `evals/fixtures/HARNESS-EVAL-002.md`
- 계획 차수: **2차 (재계획)**
- 재계획 사유: `reports/RUN-20260820-1443-HARNESS-EVAL-002/test-result-1.md` 가 `STATUS: FAIL` / 실패 원인 분류 `PLAN_DEFECT` 를 반환했다. (`CLAUDE.md §20` PLAN_DEFECT 라우팅)
- 1차 계획 스냅샷: `reports/RUN-20260820-1443-HARNESS-EVAL-002/plan-1.md`

---

## 0. 1차 계획의 어떤 판단이 틀렸는가 (재계획 근거)

`test-result-1.md` 의 실패 결과와 현재 `sample-project/src/expense/charge_rounding.py` 를 다시 읽어 확인한 결과,
1차 계획의 다음 세 가지 판단이 **사실과 달랐다**.

### 틀린 판단 1 — "`round_to_unit` 은 계약대로 동작한다"

- 1차 계획 `plan-1.md:76-78` (§6): "`round_to_unit` 은 `amount < 0`, `unit <= 0` 을 검증한 뒤 나머지가 있으면 올림한다.
  올림 규칙 자체는 계약대로 동작하며 ... 따라서 올림 로직은 이번 수정 대상이 아니다."
- 실제: `charge_rounding.py` 에는 `round_to_unit` 이 **두 번 정의**되어 있고, 뒤에 정의된 쪽이 앞의 올림 구현을 덮어쓴다.
  모듈이 외부로 노출하는 `round_to_unit` 은 올림이 아니라 **내림**으로 동작한다.
- 1차 Planner는 `charge_rounding.py:16-24`(앞쪽 정의)만 읽고 `:27-35`(뒤쪽 재정의)를 확인하지 않은 채
  "올림은 정상"이라고 단정했다. 이것이 이번 `PLAN_DEFECT` 의 직접적 원인이다.

### 틀린 판단 2 — "`test_charge_rounding.py` 는 현재 통과 중이다"

- 1차 계획 `plan-1.md:77`, `plan-1.md:146` (§9-2): "현재 통과 중이다", "계속 통과한다"를 통과 기준으로 전제했다.
- 실제(`test-result-1.md:71-74`): `test_charge_rounding.py` 는 **4건이 실패**하고 있었다.
  - `test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary` (`10000 != 10100`)
  - `test_round_to_unit_rounds_up_even_when_remainder_is_one_won` (`10000 != 10100`)
  - `test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit` (`10000 != 10100`)
  - `test_round_to_unit_never_returns_less_than_the_original_amount` (`round_to_unit(7, 100) == 0`)
- 1차 Planner는 테스트를 실행하지 않고 Task 문서의 "정산 단위 올림 자체는 현재 정상 동작한다"라는 서술을
  검증 없이 그대로 받아들였다. Task 문서의 현상 서술을 코드 근거로 대체한 것이 `CLAUDE.md §3-5` 위반이다.

### 틀린 판단 3 — 수정 허용 파일을 `service_charge.py` 한 개로 한정한 것

- 1차 계획 `plan-1.md:98-102` (§7): "`charge_rounding.py` ... 는 현재 계약대로 동작하고 있으므로 변경 대상이 아니다."
- 실제: 남은 실패 2건(`test_service_charge.py`)은 `round_to_unit` 결함에서 파생된 것이며,
  `charge_rounding.py` 를 수정하지 않으면 해결할 수 없다.
  **계획을 준수하는 한 Developer가 남은 실패를 고칠 수 없는 상태**였다.

### 1차 계획에서 옳았던 판단 (유지한다)

- 나머지 배분 유실이 실재하는 결함이라는 분석은 옳았고, Developer의 1차 수정으로 해소되었다.
  `test-result-1.md:128-138` 이 확인했듯 `[3334, 3333, 3333]` 은 길이 3, 최대 차이 1원, 앞 사람 우선, 합계 보존을 모두 만족한다.
- 따라서 이번 재계획은 **1차 수정을 되돌리는 것이 아니라, 놓친 두 번째 결함을 추가로 다루는 것**이다.

---

## 1. 요구사항 요약

`split_service_charge(bill, people, charge_percent, unit)` 가 반환하는 1인당 부담액 목록의 합계가
**봉사료를 더한 뒤 정산 단위로 올림한 총액** 과 항상 같아야 한다.

만족해야 할 계약은 다음 두 층으로 나뉜다.

**A. 정산 단위 올림 계약 (`round_to_unit`)**

- 금액이 단위 경계에 있지 않으면 **올림**한다. 단수 금액은 버리지 않고 올려서 청구한다.
- 불변식: 임의의 `amount >= 0`, `unit >= 1` 에 대해 `round_to_unit(amount, unit) >= amount`
- 이미 단위 경계에 있으면 그대로 반환한다. `unit == 1` 이면 원금 그대로다. `amount == 0` 이면 0이다.
- `amount < 0` 또는 `unit < 1` 이면 `ValueError` (기존 메시지 문구 유지)

**B. 봉사료 정산 계약 (`split_service_charge`)**

- `sum(결과) == round_to_unit(bill + bill * charge_percent // 100, unit)`
- `len(결과) == people`
- `max(결과) - min(결과) <= 1`
- 1원 단위 차이는 **앞 사람부터** 배분한다.
- 입력값 검증(`people` < 1, `bill` < 0, `charge_percent` < 0, `unit` < 1 → `ValueError`)을 유지한다.
- `split_amount`, `split_by_weights`, `settle_by_unit`, `reconcile_payments`, `format_split` 동작에는 영향을 주지 않는다.

## 2. 재현 조건

**결함 A (올림 붕괴)**: `amount % unit != 0` 인 모든 `round_to_unit` 호출.

```python
from expense.charge_rounding import round_to_unit

round_to_unit(10050, 100)   # 10000 (기대 10100)
round_to_unit(7, 100)       # 0     (기대 100, 원금보다 작아짐)
```

**결함 B (파생)**: 총액이 단위 경계에 걸치지 않는 `split_service_charge` 호출.

```python
from expense.service_charge import split_service_charge

split_service_charge(10050, 3, 0, 100)   # [3334, 3333, 3333] (기대 [3367, 3367, 3366])
```

`unit == 1` 이거나 총액이 이미 단위 경계에 있는 경우(`split_service_charge(9000, 3, 10, 100)`)에는 재현되지 않는다.
이 때문에 1차 실행에서 15개 중 13개 테스트가 통과해 결함이 가려졌다.

## 3. 기대 동작

### `round_to_unit`

| 입력 | 기대 결과 | 현재 결과 |
| --- | --- | --- |
| `(10050, 100)` | `10100` | `10000` |
| `(10001, 100)` | `10100` | `10000` |
| `(10099, 100)` | `10100` | `10000` |
| `(10100, 100)` | `10100` | `10100` (정상) |
| `(10057, 1)` | `10057` | `10057` (정상) |
| `(0, 100)` | `0` | `0` (정상) |
| `(7, 100)` | `100` | `0` |
| `(-1, 100)` | `ValueError` | `ValueError` (정상) |
| `(10000, 0)` | `ValueError` | `ValueError` (정상) |
| `(10000, -100)` | `ValueError` | `ValueError` (정상) |

### `split_service_charge`

| 입력 | 총액 | 기대 결과 | 현재 결과 |
| --- | --- | --- | --- |
| `(10000, 3, 10, 1)` | 11000 | `[3667, 3667, 3666]` | `[3667, 3667, 3666]` (정상) |
| `(10050, 3, 0, 100)` | 10100 | `[3367, 3367, 3366]` | `[3334, 3333, 3333]` |
| `(10000, 3, 0, 1)` | 10000 | `[3334, 3333, 3333]` | 정상 |
| `(9000, 3, 10, 100)` | 9900 | `[3300, 3300, 3300]` | 정상 |
| `(10000, 1, 10, 100)` | 11000 | `[11000]` | 정상 |
| `(0, 3, 10, 100)` | 0 | `[0, 0, 0]` | 정상 |
| `(9, 3, 10, 1)` | 9 | 합계 9 | 정상 |

## 4. 현재 동작

`test-result-1.md:14-77` 의 실행 결과 기준으로 **6 failed, 76 passed** 상태다.

- `test_charge_rounding.py` 4건 실패 — `round_to_unit` 이 올림이 아니라 내림으로 동작한다.
  기대값과 실제값의 차이가 정확히 `unit` 1단위다(`test-result-1.md:99-100`).
- `test_service_charge.py` 2건 실패 — `split_service_charge(10050, 3, 0, 100)` 의 총액이
  10100이 아닌 10000으로 계산되어 합계가 부족하다.
  반환값 `[3334, 3333, 3333]` 은 10000을 정확히 3분할한 결과이므로 **분배 로직은 이미 정상**이다(`test-result-1.md:114-124`).
- 1차 계획이 대상으로 삼았던 나머지 유실 관련 테스트 3건은 Developer의 1차 수정으로 통과 상태다.

## 5. 예상 원인

원인은 하나가 아니라 **두 개의 독립된 결함**이었고, 1차 계획은 그중 하나만 인식했다.

- **결함 1 (해소됨)**: `split_service_charge` 가 몫만 인원수만큼 복제해 나머지를 버렸다.
  → Developer 1차 수정으로 공용 분배 함수 재사용으로 교체되어 해소되었다.
- **결함 2 (미해소, 이번 수정 대상)**: `charge_rounding.py` 모듈 하단에서 `round_to_unit` 이 **같은 이름으로 재정의**되어
  앞의 올림 구현을 섀도잉한다. 재정의된 함수는 올림이 발생한 경우(`rounded > amount`) `unit` 을 다시 빼므로
  최종 결과가 내림이 된다. 모듈을 import 하는 모든 호출자는 이 뒤쪽 정의만 보게 된다.

`round_to_unit` 이 내림으로 동작하므로 `split_service_charge` 에 넘어오는 총액 자체가 잘못되고,
분배 로직이 아무리 정확해도 합계 보존 계약을 만족할 수 없다.
즉 `test_service_charge.py` 실패 2건은 독립 결함이 아니라 **결함 2의 파생 증상**이다.

또한 재정의된 쪽에는 docstring이 없어, 이 모듈이 문서(`:5-15`)로 약속한 "올림" 계약과 실제 노출 동작이 정면으로 어긋난다.
`# 단위에 못 미치는 단수 금액은 청구하지 않는다는 요구로 추가된 후처리` 라는 주석이 달려 있으나,
이 서술은 Task 문서의 기대 동작("단수 금액은 버리지 않고 올려서 청구한다")과 모순되며
`test_charge_rounding.py` 의 계약 테스트와도 충돌한다. 근거 없는 요구로 판단한다.

## 6. 실제 코드에서 확인한 근거

- `sample-project/src/expense/charge_rounding.py:31-35` — 파일 하단에서 `round_to_unit` 이 **두 번째로 정의**된다.
  본문은 앞 구현을 호출한 뒤 `if rounded > amount: return rounded - unit` 으로 올림분을 되돌린다.
  이 정의가 `:4` 의 정의를 섀도잉하므로 모듈이 노출하는 최종 동작은 내림이다.
  `round_to_unit(10050, 100)` → 내부 올림 10100 → `10100 - 100` = 10000,
  `round_to_unit(7, 100)` → 내부 올림 100 → `100 - 100` = 0 (원금 7보다 작아진다).
  **이것이 이번 재계획의 핵심 근거이며, 1차 계획이 읽지 않았던 부분이다.**
- `sample-project/src/expense/charge_rounding.py:28` — `_round_to_unit_before_fraction_discard_rule = round_to_unit`.
  섀도잉 직전에 원래 구현을 보존하려고 만든 모듈 전용 별칭이다.
  섀도잉이 제거되면 이 별칭은 사용처가 사라진다(`CLAUDE.md §9` "사용하지 않는 코드가 남아 있지 않은가").
- `sample-project/src/expense/charge_rounding.py:4-24` — 첫 번째 정의는 `amount < 0`, `unit <= 0` 을 검증한 뒤
  나머지가 있으면 `amount + (unit - remainder)` 로 올림한다. §1-A 계약과 정확히 일치한다.
  즉 **올바른 구현은 이미 파일 안에 존재하며, 뒤 정의에 가려져 있을 뿐이다.**
- `sample-project/src/expense/charge_rounding.py:5-15` — 첫 번째 정의의 docstring은
  "금액을 정산 화폐 단위에 맞춰 올림한 결과를 반환한다. 단위에 걸치지 않는 단수 금액은 버리지 않고 올려서 청구한다"라고
  명시한다. Task 문서의 기대 동작과 동일하다. 문서화된 계약이 곧 요구사항임을 확인했다.
- `sample-project/src/expense/service_charge.py:31` — `total = round_to_unit(bill + service_charge, unit)`.
  총액 계산이 결함 있는 `round_to_unit` 에 전적으로 의존하므로, 총액이 내림된 채로 분배 단계에 전달된다.
- `sample-project/src/expense/service_charge.py:33-36` — 1차 수정 결과로 `split_amount(total, people)` 를 반환한다.
  나머지 배분·앞 사람 우선·합계 보존 계약을 이미 만족하므로 **이 부분은 추가 변경이 필요 없다.**
- `sample-project/src/expense/service_charge.py:23-28` — `people`, `bill`, `charge_percent` 만 직접 검증한다.
  `unit < 1` 의 `ValueError` 는 `:31` 의 `round_to_unit` 호출을 통해 간접 발생한다.
  따라서 `charge_rounding.py` 를 고칠 때 입력값 검증을 함께 잃으면
  `test_split_service_charge_raises_value_error_when_unit_is_zero` 가 조용히 깨진다.
- `sample-project/src/expense/splitter.py:16-28` — `split_amount` 는 입력값 검증 후 나머지를 앞 사람부터 1원씩 배분한다.
  현재 계약대로 동작하며 변경 대상이 아니다.
- `sample-project/tests/test_charge_rounding.py:6-47` — 올림 3건, 경계값 3건, `>= amount` 불변식 1건,
  입력값 검증 3건으로 §1-A 계약 전체를 검증한다. 회귀 테스트를 새로 만들 필요가 없다.
- `sample-project/tests/test_service_charge.py:6-69` — 합계 보존, 앞 사람 우선 배분, 목록 길이,
  최대 1원 차이, 입력값 검증 4종을 검증하는 15개 테스트가 존재한다.
- Grep 결과 `round_to_unit` 호출자는 `sample-project/src/expense/service_charge.py:3,31` 과
  `sample-project/tests/test_charge_rounding.py` 뿐이다. `settlement.py`, `reconciliation.py`,
  `weighted_splitter.py`, `allocation.py`, `formatter.py` 는 이 모듈을 import 하지 않는다.
  → `charge_rounding.py` 수정의 영향 범위는 이 두 파일로 한정된다.
- `sample-project/src/expense/__init__.py` — 비어 있다. 패키지 레벨 재노출이 없어 import 경로 side effect가 없다.

## 7. 수정 허용 파일 목록

- `sample-project/src/expense/charge_rounding.py`  ← **2차에서 추가된 실제 결함 파일**
- `sample-project/src/expense/service_charge.py`  ← 1차 목록 유지 (필요한 경우에만 손댄다)

위 두 파일 외에는 어떤 파일도 수정하지 않는다.
`splitter.py`, `allocation.py`, `settlement.py`, `reconciliation.py`, `weighted_splitter.py`, `formatter.py` 는
현재 계약대로 동작하므로 변경 대상이 아니며, `sample-project/tests/` 하위 파일은 Developer의 수정 대상이 아니다.

> `service_charge.py` 는 1차 목록 유지 차원에서 허용 목록에 남긴다.
> 다만 현재 분석상 이 파일은 이미 요구된 분배 계약을 만족하므로,
> 추가 변경이 불필요하다면 손대지 않는 것이 `CLAUDE.md §17` 최소 변경 원칙에 부합한다.

## 8. 구현 단계

1. `charge_rounding.py` 가 외부로 노출하는 `round_to_unit` 이 **올림 계약(§1-A)을 만족하도록 되돌린다.**
   — 이 단계의 유일한 목적은 모듈이 문서화한 계약과 실제 노출 동작을 일치시키는 것이다.
   현재는 `:31-35` 의 재정의가 `:4-24` 의 올바른 올림 구현을 섀도잉하고 있다.
   수정 후 `round_to_unit(amount, unit) >= amount` 불변식이 모든 `amount >= 0` 에서 성립해야 한다.

2. 섀도잉 제거로 사용처가 없어지는 모듈 전용 별칭(`charge_rounding.py:28`)과
   그에 딸린 주석을 함께 정리한다.
   — 사용하지 않는 코드를 남기지 않기 위한 단계다(`CLAUDE.md §9`).
   `# 단위에 못 미치는 단수 금액은 청구하지 않는다`는 주석은 Task 문서의 기대 동작 및
   `test_charge_rounding.py` 의 계약과 모순되므로 남겨두면 이후 개발자가 의도를 오해한다(`CLAUDE.md §5`).

3. 수정 후에도 `round_to_unit` 의 입력값 검증(`amount < 0`, `unit <= 0` → `ValueError`)이
   호출 즉시 동작하는지 확인한다.
   — 현재 이 검증은 앞쪽 정의 안에만 존재하고, 뒤쪽 정의는 위임을 통해 간접적으로 검증을 얻고 있다(`§6`).
   구조를 정리하는 과정에서 검증이 유실되면
   `test_charge_rounding.py` 의 검증 테스트 3건과
   `test_split_service_charge_raises_value_error_when_unit_is_zero` 가 동시에 깨진다.
   예외 타입과 기존 메시지 문구를 바꾸지 않는다(`CLAUDE.md §3-10`).

4. `service_charge.py` 의 분배 로직과 봉사료 계산은 **변경하지 않는다.**
   — `test-result-1.md:128-138` 이 1차 수정의 분배 계약 충족을 실행 결과로 확인했고,
   남은 실패는 전부 총액 계산 단계에서 비롯되기 때문이다.
   총액 계산 위치와 호출 순서를 바꾸면 `unit` 간접 검증(`§6`)이 깨질 수 있으므로 그대로 둔다.

5. 두 파일의 docstring 서술과 실제 동작이 일치하는지 확인한다.
   — `charge_rounding.py:5-15` 와 `service_charge.py:8-22` 는 이미 올바른 계약을 서술하고 있으므로
   문구 수정이 필요 없을 가능성이 높다. 불필요한 문구 변경으로 diff를 키우지 않는다(`CLAUDE.md §15`, `§17`).

> 구현 방법(코드)은 Developer가 위 파일들을 직접 읽고 결정한다. 이 계획에는 만족해야 할 조건만 기술한다.
> 재시도이므로 Developer는 `CLAUDE.md §16` 에 따라 `test-result-1.md` 와 `change-log-1.md` 를 먼저 읽고,
> 1차와 다른 근거(총액 계산 단계의 결함)를 `change-log-2.md` 에 기록해야 한다.

## 9. 검증 방법

- 실행 명령: `uv run pytest sample-project/tests -q`

통과 판정 기준:

1. `test-result-1.md` 에서 실패한 6건이 모두 통과한다.
   - `test_charge_rounding.py::test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary`
   - `test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_one_won`
   - `test_charge_rounding.py::test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit`
   - `test_charge_rounding.py::test_round_to_unit_never_returns_less_than_the_original_amount`
   - `test_service_charge.py::test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit`
   - `test_service_charge.py::test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit`
2. `test_charge_rounding.py` 의 10개 테스트가 모두 통과한다.
   특히 입력값 검증 3건(`unit == 0`, `unit < 0`, `amount < 0`)이 계속 `ValueError` 를 발생시킨다.
3. `test_service_charge.py` 의 15개 테스트가 모두 통과한다.
   1차에서 이미 통과한 나머지 배분 관련 3건이 회귀하지 않아야 한다.
4. `test_splitter.py`, `test_weighted_splitter.py`, `test_settlement.py`, `test_reconciliation.py`,
   `test_formatter.py` 등 1차에서 통과한 76건이 하나도 깨지지 않는다.
5. 최종 결과는 실패 0건이어야 한다. 특정 테스트 하나만 통과한 상태는 완료로 보지 않는다(`CLAUDE.md §10`).
6. 테스트를 약화시키거나 기대값을 바꾸는 방식의 통과는 인정하지 않는다(`CLAUDE.md §3-3`).
7. Reviewer는 `git diff` 상 변경 파일이 §7 허용 목록 2개를 벗어나지 않는지 확인한다.

## 10. 예상 위험 요소

- **입력값 검증 유실 (높음)**: 현재 `round_to_unit` 의 검증은 앞쪽 정의 안에만 있고,
  `split_service_charge` 의 `unit` 검증은 이 호출에 간접 의존한다(`§6`).
  섀도잉 정리 과정에서 검증문이 함께 사라지면 `test_charge_rounding.py` 3건과
  `test_split_service_charge_raises_value_error_when_unit_is_zero` 가 동시에 깨진다.
  이번 수정에서 가장 사고가 나기 쉬운 지점이다.
- **1차 수정 되돌림 (중간)**: Developer가 재시도 과정에서 `service_charge.py` 의
  `split_amount` 재사용을 원복하면, 이미 통과한 나머지 배분 테스트 3건이 다시 깨진다.
  1차 수정은 유효하므로 유지한다(`test-result-1.md:128-138`).
- **잘못된 지점 수정 (중간)**: 총액 부족을 `service_charge.py` 쪽에서 보정하려는 시도
  (예: 분배 직전에 금액을 더하는 방식)는 `test_charge_rounding.py` 4건을 그대로 실패시킨다.
  결함의 위치는 `charge_rounding.py` 이므로 그곳에서 고쳐야 한다.
- **예외 메시지 변경 (낮음)**: 기존 메시지 문구(`amount는 0 이상이어야 합니다. (입력값: {amount})` 등)를
  바꾸면 요구사항 밖 변경이 된다(`CLAUDE.md §3-10`).
- **경계값 회귀 (낮음)**: `amount == 0`, `unit == 1`, 이미 단위 경계에 있는 금액,
  `bill == 0`, `people == 1`, 봉사료가 1원 미만으로 내림되는 경우(`(9, 3, 10, 1)`)에서
  기존 동작이 유지되어야 한다.
- **범위 초과 변경 (중간)**: `splitter.py` 등 정상 동작 중인 모듈을 함께 손대면
  `test_splitter.py`, `reconciliation.py` 까지 회귀 위험이 번진다. 수정은 §7의 두 파일로 제한한다.
- **재시도 예산 (관리 항목)**: `CLAUDE.md §16` 기준 이번 재계획으로 예산 1회를 소비했다.
  남은 예산 안에서 해결되지 않으면 Orchestrator가 `BLOCKED` 로 종료한다.
- **영향 범위 자체는 좁음**: `round_to_unit` 호출자는 `service_charge.py` 와 `test_charge_rounding.py` 뿐이고
  `__init__.py` 는 비어 있어 패키지 레벨 재노출이 없다. 위 제약만 지키면 다른 모듈로의 전파 가능성은 낮다.
