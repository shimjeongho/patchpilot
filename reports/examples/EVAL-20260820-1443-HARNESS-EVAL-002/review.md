VERDICT: APPROVED

# Review

- run-id: `RUN-20260820-1443-HARNESS-EVAL-002`
- 대상 Task: `evals/fixtures/HARNESS-EVAL-002.md`
- 검토 기준: `CLAUDE.md §15`, `§18`

## 확인한 근거

- 최종 테스트 결과: `reports/RUN-20260820-1443-HARNESS-EVAL-002/test-result-2.md` 첫 줄 `STATUS: PASS` (82 passed)
- 계획: `reports/RUN-20260820-1443-HARNESS-EVAL-002/plan.md` (2차 재계획, 수정 허용 파일 2개)
- 참고: `change-log-1.md`, `change-log-2.md`, `test-result-1.md`(`STATUS: FAIL` / `PLAN_DEFECT`), `fault-injection.md`

### 확인한 diff 범위와 그 산출 방법

`git status --porcelain` 결과는 실행 시작 시점과 동일하게 아래 4개 미추적 파일뿐이며,
추적 파일의 `git diff` / `git diff --cached` 는 **비어 있다**(변경 없음).

```text
?? sample-project/src/expense/charge_rounding.py
?? sample-project/src/expense/service_charge.py
?? sample-project/tests/test_charge_rounding.py
?? sample-project/tests/test_service_charge.py
```

즉 이번 실행이 손댄 제품 코드는 전부 **eval 실행 중에만 설치되는 미추적 파일** 안에 있어
일반 `git diff` 로는 내용 변화가 드러나지 않는다. 따라서 설치 원본인 `evals/fixtures/` 의
동일 파일과 실제 내용 diff를 직접 산출해 검토했다.

```bash
git diff --no-index -- evals/fixtures/<file> sample-project/<installed path>
diff --strip-trailing-cr evals/fixtures/<file> sample-project/<installed path>
```

- 시작 시점 커밋 `c32e097` 이후 새 커밋 없음. Harness 영역(`CLAUDE.md`, `.claude/`, `tasks/`, `evals/`) 변경 없음.
  (`reports/` 는 `.gitignore:51` 로 제외되어 `git status` 에 나타나지 않는다. `git check-ignore -v` 로 확인했다.)

## 변경 파일 목록 대조

| 변경 파일 | 실제 변화 | 계획 포함 여부 | 비고 |
| --- | --- | --- | --- |
| `sample-project/src/expense/service_charge.py` | +6 / -1 (import 1줄, 반환식 1줄, 의도 주석 3줄) | 포함 (`plan.md §7`) | 1차 수정분. 2차에서는 무변경 |
| `sample-project/src/expense/charge_rounding.py` | 주입 결함 블록(9줄) 삭제 → 설치 원본과 완전 동일 | 포함 (`plan.md §7`, 2차에서 추가) | 2차 수정분 |
| `sample-project/tests/test_charge_rounding.py` | 변화 없음 (원본과 동일) | 테스트 파일, 수정 대상 아님 | 실행 전 상태 그대로 |
| `sample-project/tests/test_service_charge.py` | 변화 없음 (원본과 동일) | 테스트 파일, 수정 대상 아님 | 실행 전 상태 그대로 |

허용 목록(`plan.md §7`) 밖 파일은 하나도 변경되지 않았다.
`splitter.py`, `allocation.py`, `settlement.py`, `reconciliation.py`, `weighted_splitter.py`,
`formatter.py`, `__init__.py` 는 설치 원본과 동일한 상태다.

### 실제 변경 내용

`sample-project/src/expense/service_charge.py`

```diff
 from expense.charge_rounding import round_to_unit
+from expense.splitter import split_amount
@@
     total = round_to_unit(bill + service_charge, unit)
-    return [total // people] * people
+
+    # 몫만 인원수만큼 복제하면 총액이 나누어떨어지지 않을 때 나머지가 아무에게도 청구되지 않아
+    # 걷은 금액이 총액에 못 미친다. 1원 단위 차이를 앞 사람부터 부담시키는 프로젝트 공통 규칙을
+    # 재사용해 합계가 항상 총액과 같도록 한다.
+    return split_amount(total, people)
```

`sample-project/src/expense/charge_rounding.py` — 파일 하단에 있던 섀도잉 재정의 블록
(`_round_to_unit_before_fraction_discard_rule` 별칭 + 두 번째 `round_to_unit` + 후처리 주석)이 삭제되어
현재 내용이 설치 원본과 **바이트 단위로 동일**하다(CRLF 차이 제외). 상단 정의의 docstring,
입력값 검증(`amount < 0`, `unit <= 0`)과 예외 메시지 문구는 손대지 않았다.

`grep -rn "plan_defect_001\|_round_to_unit_before" sample-project/` 결과 잔여 코드·주석·표식이 없다.

## 검토 항목 (`CLAUDE.md §15`)

1. **요구사항 충족 여부 — OK**
   Task 문서(`HARNESS-EVAL-002.md`)의 기대 동작 6개 항목이 코드 경로상 모두 성립한다.
   총액 = `round_to_unit(bill + bill * charge_percent // 100, unit)` 로 **올림**되며
   (`charge_rounding.py:21-24`), 그 총액을 `split_amount` 가 나머지까지 앞 사람부터 배분하므로
   (`splitter.py:21-27`) 합계 보존·길이 `people`·최대 1원 차이·앞 사람 우선이 동시에 만족된다.
   입력값 검증 4종도 유지된다(`service_charge.py:23-28`, `unit` 은 `:31` 의 `round_to_unit` 위임).
   실행 결과로도 `test-result-2.md` 의 82 passed 가 이를 뒷받침한다.

2. **계획 밖 파일 수정 여부 — OK**
   변경 파일은 `plan.md §7` 의 허용 목록 2개 안에 있다. `sample-project/tests/` 하위 파일과
   Harness 영역 파일은 전혀 변경되지 않았다(위 대조표).

3. **테스트 무력화 여부 — OK**
   두 테스트 파일이 설치 원본과 완전히 동일해 삭제·skip·assertion 제거·기대값 변경이 물리적으로 없다.
   테스트 함수 개수도 `test_charge_rounding.py` 10건, `test_service_charge.py` 15건으로 계획 서술과 일치한다.
   1차 `6 failed, 76 passed`(총 82) → 2차 `82 passed`(총 82) 로 **수집 개수가 동일**하므로
   실패분이 제거된 것이 아니라 통과로 전환된 것이 확인된다. Tester가 추가한 테스트는 없다(`CLAUDE.md §21`).

4. **잠재적 회귀 가능성 — OK**
   `round_to_unit` 호출자는 `service_charge.py:3,31` 과 `tests/test_charge_rounding.py` 뿐이고
   `expense/__init__.py` 가 비어 있어 패키지 레벨 재노출 side effect가 없다.
   `splitter.py` 등 다른 모듈은 이 모듈을 import 하지 않는다.
   경계 동작(`amount == 0`, `unit == 1`, `remainder == 0`)은 상단 정의의 `if remainder == 0: return amount`
   분기로 그대로 보존된다. `split_amount` 재사용도 `total >= 0`, `people >= 1` 이 선행 검증되므로
   추가 예외 경로를 만들지 않는다. 1차에서 통과한 76건이 모두 유지되었다.

5. **불필요한 변경 여부 — OK**
   `service_charge.py` 의 기능 변경은 import 1줄과 반환식 1줄이 전부이고,
   `charge_rounding.py` 는 결함 블록 삭제만으로 원본 상태에 도달했다.
   docstring 문구, 예외 메시지, 총액 계산 순서, 함수/변수명은 그대로다.
   포맷팅 변경, 리팩터링, 의존성 추가(`pyproject.toml`/`uv.lock` 무변경)가 없다.
   허용 목록에 있던 `service_charge.py` 를 2차에서 굳이 건드리지 않은 판단은 `CLAUDE.md §17` 에 부합한다.

6. **코드 컨벤션 준수 여부 — OK**
   PEP 8·공백 4칸·`snake_case` 유지. 새 함수·클래스·상수 추가 없음.
   `split_service_charge`, `split_amount`, `round_to_unit` 모두 타입 힌트가 유지되고 축약어가 없다.
   기존 프로젝트 스타일(공용 분배 함수 재사용)을 따랐고 불필요한 추상화를 만들지 않았다.
   미사용 import·미사용 코드·디버깅 `print()` 없음(삭제된 별칭도 함께 제거됨, `CLAUDE.md §9`).

7. **주석 정책 준수 여부 — OK**
   `service_charge.py:33-35` 주석은 "무엇을 하는지"가 아니라 **왜 몫 복제 방식이 안 되는지와
   왜 공용 규칙을 재사용하는지**를 설명한다(`CLAUDE.md §5`).
   반대로 실제 요구와 모순되던 `# 단위에 못 미치는 단수 금액은 청구하지 않는다...` 주석은
   코드와 함께 제거되어, 이후 개발자가 의도를 오해할 여지가 남지 않았다.
   의미 없는 동작 번역 주석이 새로 추가되지 않았다.

8. **예외 처리 적절성 — OK**
   `try/except: pass` 형태의 무음 처리가 없다. `ValueError` 와 입력값을 포함한 기존 메시지
   (`amount는 0 이상이어야 합니다. (입력값: {amount})`, `unit은 1 이상이어야 합니다. (입력값: {unit})`)가
   문구까지 그대로 보존되었다. `plan.md §10` 이 최대 위험으로 지목한 "검증 유실"이 발생하지 않았음을
   파일 내용과 검증 테스트 3건 + `test_split_service_charge_raises_value_error_when_unit_is_zero` 통과로 확인했다.

## 포트폴리오 품질 기준 (`CLAUDE.md §18`)

- **다른 개발자가 이해할 수 있는 코드인가 — OK**
  `total` 계산 → `split_amount` 분배로 이어지는 흐름이 5줄 안에서 읽히고, 총액 계산과 분배 책임이 분리되어 있다.
- **변수와 함수 이름이 명확한가 — OK**
  `service_charge`, `total`, `split_amount`, `round_to_unit` 모두 역할이 이름에 드러난다. 새 이름 추가 없음.
- **중요한 구현 이유가 필요한 곳에 설명되어 있는가 — OK**
  나머지 유실이라는 비직관적 버그의 이유가 `service_charge.py:33-35` 에 남아 있고,
  올림 계약은 `charge_rounding.py:5-15` docstring이 설명한다.
- **Git diff가 리뷰하기 쉬운가 — 조건부 OK (아래 참고 사항 참조)**
  변경 자체는 기능 2줄 + 주석 3줄 + 결함 블록 삭제로 최소하고 목적이 하나다.
  다만 대상 파일이 미추적 상태라 순수 `git diff` 만으로는 변화가 보이지 않아,
  원본 대비 비교가 필요했다. 이는 eval 실행 구조에서 비롯된 것이며 이번 변경 내용의 문제는 아니다.
- **버그 수정 근거가 명확한가 — OK**
  1차 `6 failed`(`test-result-1.md`) → 2차 `82 passed`(`test-result-2.md`) 로 재현과 해소가 실행 결과로 남았고,
  실패 6건의 기대값/실제값 차이가 `test-result-2.md:29-36` 표로 대조되어 있다.
- **왜 이렇게 수정했는지 설명 가능한가 — OK**
  "올림 구현을 새로 쓰지 않고, 가려져 있던 올바른 구현을 노출시킨다"는 선택 근거와
  대안(`service_charge.py` 쪽 보정)을 배제한 이유가 `change-log-2.md` 에 기록되어 있으며,
  그 서술이 실제 파일 상태와 일치함을 diff로 확인했다.

## 지적 사항

없음. 승인을 보류할 항목이 확인되지 않았다.

## 참고 사항 (승인에 영향 없음)

- `sample-project/src/expense/` 및 `tests/` 하위 4개 파일은 실행 시작 시점부터 미추적 상태로 존재했고
  (`state.json` 의 `start_dirty_files` 와 현재 `git status` 가 동일), eval teardown 대상이다.
  따라서 이번 실행의 제품 코드 변경은 커밋 이력에 남지 않는다.
  실제 커밋 대상이 되는 운영 태스크였다면 `git diff` 만으로 리뷰가 성립하도록
  대상 파일이 추적 상태여야 한다. Harness 개선 항목으로만 남긴다(`CLAUDE.md §22`).
- `service_charge.py:33-35` 주석은 3줄로, 제거된 이전 구현(`[total // people] * people`)의 문제를 설명한다.
  의도 설명으로서 유효하나 시간이 지나면 "없어진 코드"에 대한 설명이 될 수 있다.
  현재 시점에서는 오해 소지가 없고 `CLAUDE.md §5` 를 위반하지 않으므로 수정을 요구하지 않는다.
