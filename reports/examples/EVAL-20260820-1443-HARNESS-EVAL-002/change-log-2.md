# Change Log 2

## 시도 번호
2

## 수정 가설
1차 가설("나머지 배분 유실이 유일한 원인")은 **불완전했다**.
남은 실패의 원인은 분배 단계가 아니라 **분배 대상으로 넘어오는 총액 계산 단계**에 있다.

`sample-project/src/expense/charge_rounding.py` 에는 `round_to_unit` 이 두 번 정의되어 있고,
파일 하단(`:31-35`)의 재정의가 상단(`:4-24`)의 올바른 올림 구현을 섀도잉한다.
재정의된 쪽은 올림이 발생한 경우(`rounded > amount`) `unit` 을 다시 빼므로,
모듈이 외부로 노출하는 `round_to_unit` 의 실제 동작은 **올림이 아니라 내림**이 된다.

- `round_to_unit(10050, 100)` → 내부 올림 10100 → `10100 - 100` = 10000
- `round_to_unit(7, 100)` → 내부 올림 100 → `100 - 100` = 0 (원금 7보다 작아진다)

`split_service_charge` 의 총액(`service_charge.py:31`)이 이 함수에 전적으로 의존하므로,
분배 로직이 아무리 정확해도 `sum(결과) == 올림된 총액` 계약을 만족할 수 없다.
따라서 `test_service_charge.py` 실패 2건은 독립 결함이 아니라 **`round_to_unit` 결함의 파생 증상**이다.

## 변경 파일
- `sample-project/src/expense/charge_rounding.py`

(`sample-project/src/expense/service_charge.py` 는 허용 목록에 있으나 변경하지 않았다. 사유는 "구현 방법" 4항 참조)

## 변경 이유
모듈 상단 docstring(`:1`)과 `round_to_unit` 의 docstring(`:5-15`)은
"금액을 정산 화폐 단위에 맞춰 **올림**한다 / 단수 금액은 버리지 않고 올려서 청구한다"고 계약을 명시한다.
그런데 하단 재정의가 이 계약을 뒤집어, **문서화된 계약과 실제 노출 동작이 정면으로 어긋나 있었다.**

하단 재정의에 달린 `# 단위에 못 미치는 단수 금액은 청구하지 않는다는 요구로 추가된 후처리` 주석은
Task 문서(`evals/fixtures/HARNESS-EVAL-002.md`)의 기대 동작 및 `test_charge_rounding.py` 의 계약 테스트와 모순된다.
근거 있는 요구로 볼 수 없어 이 후처리를 제거하고, 모듈이 원래 약속한 올림 계약으로 되돌렸다.

## 구현 방법
`plan.md §8` 의 조건을 다음과 같이 충족했다.

1. **섀도잉 제거 (§8-1)**: `charge_rounding.py:31-35` 의 두 번째 `round_to_unit` 정의를 삭제했다.
   상단 `:4-24` 의 구현이 §1-A 계약(`amount % unit != 0` 이면 `amount + (unit - remainder)`)을
   이미 정확히 만족하므로, **올림 로직을 새로 작성하지 않고 가려져 있던 올바른 구현을 노출시키는 방식**을 택했다.
   이것이 계약을 만족시키는 가장 작은 변경이다(`CLAUDE.md §17`).
   결과적으로 `round_to_unit(amount, unit) >= amount` 불변식이 모든 `amount >= 0` 에서 성립한다.

2. **사용처가 사라지는 코드 정리 (§8-2)**: 섀도잉 제거로 참조가 없어지는 모듈 전용 별칭
   `_round_to_unit_before_fraction_discard_rule` (`:28`)과 그에 딸린 주석(`:27`)을 함께 삭제했다.
   사용하지 않는 코드와, 이후 개발자가 의도를 오해할 수 있는 모순된 주석을 남기지 않기 위함이다
   (`CLAUDE.md §9`, `§5`).

3. **입력값 검증 유지 (§8-3, 위험 요소 1)**: 검증문(`:16-19`)은 원래 상단 정의 안에 있었고,
   이번 변경은 하단 블록만 삭제했으므로 검증문에 **손대지 않았다.**
   `amount < 0` → `amount는 0 이상이어야 합니다. (입력값: {amount})`,
   `unit <= 0` → `unit은 1 이상이어야 합니다. (입력값: {unit})` 로 예외 타입과 메시지 문구가 그대로 유지된다.
   삭제된 하단 정의는 검증을 위임받아 쓰던 쪽이므로, 삭제로 인해 검증이 유실될 수 없는 구조다.
   따라서 `test_charge_rounding.py` 의 검증 3건과
   `test_split_service_charge_raises_value_error_when_unit_is_zero` 의 간접 검증 경로가 모두 보존된다.

4. **`service_charge.py` 무변경 (§8-4, 위험 요소 2·3)**: 1차 수정(`split_amount(total, people)` 재사용)은
   `test-result-1.md:128-138` 이 실행 결과로 유효성을 확인했으므로 **원복하지 않고 그대로 두었다.**
   총액 부족을 `service_charge.py` 쪽에서 보정하는 방식은 `test_charge_rounding.py` 4건을 그대로 실패시키므로
   선택하지 않았다. 총액 계산 위치와 호출 순서(`:30-31`)도 그대로 두어 `unit` 간접 검증을 유지했다.

5. **docstring 무변경 (§8-5)**: `charge_rounding.py:5-15` 와 `service_charge.py:8-22` 는
   이미 올바른 계약을 서술하고 있어 문구를 수정하지 않았다. 불필요한 diff를 만들지 않기 위함이다(`CLAUDE.md §15`, `§17`).

6. **주석 추가 없음**: 남은 코드는 "나머지가 있으면 단위만큼 채워 올린다"는 의도가 docstring과 코드로 이미 명확하다.
   동작을 번역하는 주석을 새로 넣지 않았다(`CLAUDE.md §5`).

## 이전 시도와의 차이
1차와 **수정 대상 파일 자체가 다르다.** 1차는 `service_charge.py` 의 분배 단계를 고쳤고,
2차는 `charge_rounding.py` 의 총액 계산 단계를 고쳤다. 같은 수정을 반복하지 않았다(`CLAUDE.md §16`).

새로운 근거는 다음 두 가지다.

- **실행 결과 근거**: `test-result-1.md:71-77` 에서 `test_charge_rounding.py` 가 4건 실패했다.
  1차 계획이 "현재 통과 중"이라고 전제했던 파일이 실제로는 실패 상태였다.
  기대값과 실제값의 차이가 모두 정확히 `unit`(100원) 1단위라는 패턴(`test-result-1.md:99-100`)이
  결함 위치를 올림 연산 한 곳으로 특정해 주었다.
- **코드 근거**: 1차 시점에는 `charge_rounding.py` 가 수정 금지 대상이어서 읽지 않았던 `:27-35` 블록을
  이번에 직접 읽고 섀도잉 재정의를 확인했다. 1차 가설은 이 블록을 전혀 인식하지 못한 상태에서 세워진 것이다.

또한 1차 실패는 Developer 구현 결함이 아니라 `PLAN_DEFECT` 로 분류되었으므로,
1차 변경을 되돌리는 것이 아니라 **놓쳤던 두 번째 결함을 추가로 제거하는 방향**으로 진행했다.

## 예상 부작용
- `round_to_unit` 의 반환값이 `amount % unit != 0` 인 경우 기존 대비 `unit` 만큼 커진다.
  이는 요구사항이 의도한 동작 변경이다.
- 영향 범위는 좁다. `round_to_unit` 호출자는 `service_charge.py:3,31` 과 `test_charge_rounding.py` 뿐이며
  (`plan.md §6`), `expense/__init__.py` 가 비어 있어 패키지 레벨 재노출로 인한 side effect가 없다.
  `splitter.py`, `allocation.py`, `settlement.py`, `reconciliation.py`, `weighted_splitter.py`, `formatter.py` 는
  이 모듈을 import 하지 않으므로 회귀가 전파되지 않는다.
- 경계값 동작은 유지된다. `amount == 0` → 0, `unit == 1` → 원금 그대로,
  이미 단위 경계에 있는 금액 → 그대로 반환(`remainder == 0` 분기).
- `split_service_charge` 의 반환 총액이 커지므로 1인당 부담액도 함께 올라간다.
  단, `split_amount` 가 합계 보존과 앞 사람 우선 배분을 담당하므로 분배 계약은 그대로 유지된다.
- `bill == 0`, `people == 1`, 봉사료가 1원 미만으로 내림되는 경우(`(9, 3, 10, 1)`)는
  `unit == 1` 이거나 `amount == 0` 이라 이번 변경의 영향을 받지 않는다.
- 삭제한 별칭 `_round_to_unit_before_fraction_discard_rule` 은 언더스코어 접두 모듈 전용 이름이고
  Grep 결과 다른 참조가 없어, 삭제로 인한 `AttributeError` 위험이 없다.

## 범위 밖 수정 필요 여부
없음.

`plan.md §7` 의 수정 허용 파일 2개 중 `sample-project/src/expense/charge_rounding.py` 한 개만 수정했다.
`sample-project/src/expense/service_charge.py` 는 허용 목록에 있으나 추가 변경이 불필요해 손대지 않았다(`CLAUDE.md §17`).
`sample-project/tests/` 하위 파일은 하나도 수정하지 않았고, 의존성도 추가하지 않았다.
