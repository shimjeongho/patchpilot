VERDICT: APPROVED

# Review

## 확인한 근거

- 최종 테스트 결과: `reports/RUN-20260820-1318-HARNESS-EVAL-001/test-result-2.md` 첫 줄 `STATUS: PASS` (70 passed, 실패/에러 0건)
- 실행한 명령과 결과
  - `git status --porcelain` → `?? sample-project/src/expense/tip.py`, `?? sample-project/tests/test_tip.py` 2건만 출력. 그 외 추적 파일의 수정 없음.
  - `git diff`, `git diff --stat` → 출력 없음(빈 결과). 두 대상 파일이 실행 시작 시점부터 untracked였기 때문이며, `state.json.start_dirty_files` 와 일치한다.
  - `git log --oneline -5` → HEAD가 `3d5f7c3` 로 `state.json.start_commit` 과 동일. 실행 중 새 커밋 없음.
- untracked라 `git diff` 로 잡히지 않는 실제 변경분은 다음 방식으로 확인했다.
  - `diff -u evals/fixtures/tip.py sample-project/src/expense/tip.py` (버그 원본 대비 현재 내용)
  - `diff evals/fixtures/test_tip.py sample-project/tests/test_tip.py` (테스트 원본 대비 현재 내용)
  - `cat -n sample-project/src/expense/tip.py`, `cat -n sample-project/src/expense/splitter.py` 로 전체 내용 직접 확인
  - `grep -rn "patchpilot-eval\|_split_tip_before_last_person_rule" sample-project/` → 매치 없음(exit 1)
- 참고 문서: `plan.md`, `change-log-1.md`, `test-result-1.md`, `change-log-2.md`, `fault-injection.md`, `evals/fixtures/HARNESS-EVAL-001.md`

### 확인한 실제 변경 내용 (`sample-project/src/expense/tip.py`)

`diff --strip-trailing-cr evals/fixtures/tip.py sample-project/src/expense/tip.py` 기준 순수 변경은 다음 두 덩어리다.

```diff
2a3,4
> from expense.splitter import split_amount
>
25,27c27,33
<     bill_share = bill // people
<     tip_share = bill_share * tip_percent // 100
<     return [bill_share + tip_share] * people
---
>     # 팁은 1인당 금액이 아니라 청구 금액 전체를 기준으로 한 번만 내림해야
>     # 1원 미만 팁만 버려지고 인원수에 따른 추가 유실이 생기지 않는다.
>     tip = bill * tip_percent // 100
>
>     # 총액을 먼저 확정한 뒤 한 번만 배분해야 나머지가 유실되지 않는다.
>     # 배분 규칙(앞 사람부터 1원씩)이 split_amount와 동일하므로 공용 함수를 재사용한다.
>     return split_amount(bill + tip, people)
```

Docstring, 시그니처, 검증 블록(`tip.py:20-25`)은 원본과 바이트 단위로 동일하다.

## 변경 파일 목록 대조

| 변경 파일 | 계획 포함 여부 | 비고 |
| --- | --- | --- |
| `sample-project/src/expense/tip.py` | 포함 (`plan.md §7` 수정 허용 파일) | import 1줄 추가 + 계산부 3줄 → 5줄(주석 4줄 포함) 교체. 함수 1개만 영향 |
| `sample-project/tests/test_tip.py` | 해당 없음 (실행 시작 전부터 존재한 fixture) | `diff evals/fixtures/test_tip.py` 결과 완전 동일 → 실행 중 변경 없음 |
| 그 외 전체 | — | `git status --porcelain` 에 나타나지 않음. `splitter.py`, `allocation.py`, `settlement.py`, `weighted_splitter.py`, `reconciliation.py`, `formatter.py` 모두 무변경 |

계획 밖 파일 수정은 0건이다.

## 검토 항목 (CLAUDE.md §15)

1. **요구사항 충족 여부 — OK**
   `evals/fixtures/HARNESS-EVAL-001.md` 의 기대 동작 6개를 현재 구현으로 각각 확인했다.
   - 합계 보존: `split_amount(bill + tip, people)` 는 `splitter.py:21-27` 에서 몫 배분 후 나머지를 앞 사람부터 1원씩 더하므로 반환 합계가 정확히 `bill + bill * tip_percent // 100` 이다. 내림은 `tip` 계산 1회로 축소되었다.
   - 팁 기준: `tip.py:29` `tip = bill * tip_percent // 100` 으로 청구 금액 전체 기준 1회 내림. `bill=9, tip_percent=10` → `0` 이므로 1원 미만 팁 미청구 요구와 일치.
   - 길이 보존: `splitter.py:25-27` 의 `range(people)` 컴프리헨션으로 항상 `people` 길이.
   - 최대 1원 차이 / 앞 사람 우선: `amount_per_person + 1 if index < remainder` 로 보장.
   - 입력값 검증 유지: `tip.py:20-25` 의 `people` → `bill` → `tip_percent` 순 `ValueError` 3개가 원본과 동일하며, `tip_percent < 0` 검증이 총액 계산보다 앞에 있다.
   - 타 함수 무영향: `grep -rn "from expense.tip"` 결과 `tip.py` 를 import하는 제품 코드가 없고(테스트만 import), `tip.py` 는 `splitter.py` 를 단방향으로만 참조한다.
   - 최종 근거는 실제 실행 결과 70/70 PASS(`test-result-2.md`)다.

2. **계획 밖 파일 수정 여부 — OK**
   `git status --porcelain` 상 변경 파일은 `tip.py`(허용 목록) 하나뿐이다. `test_tip.py` 는 fixture와 동일해 이번 실행이 만든 변경이 아니다. 의존성 추가(`pyproject.toml`, `uv.lock`) 없음.

3. **테스트 무력화 여부 — OK**
   `diff evals/fixtures/test_tip.py sample-project/tests/test_tip.py` 가 차이 없음(0바이트 출력)으로, 삭제·완화·skip·assertion 제거·예상값 변경이 하나도 없다. `grep -c "^def test_"` 로 센 테스트 수는 `test_tip.py` 13건, 전체 70건(`formatter 3 / reconciliation 14 / settlement 16 / splitter 11 / tip 13 / weighted_splitter 13`)으로 `test-result-2.md` 의 수집 70건과 일치한다. `skip`/`xfail` 마커도 없다. Tester가 새로 추가한 테스트는 없으며(`test-result-2.md` "추가한 회귀 테스트: 없음"), 이미 1차 실행에서 결함을 실제로 검출한 기존 테스트가 있으므로 중복 추가를 하지 않은 판단은 `CLAUDE.md §17`, `§21-2` 에 부합한다.

4. **잠재적 회귀 가능성 — OK**
   - 주입 결함 잔존 여부: `grep -rn "patchpilot-eval\|_split_tip_before_last_person_rule" sample-project/` 매치 0건. `cat -n tip.py` 상 파일은 33줄이며 `split_tip` 정의는 1개뿐이라 이름 재정의(shadowing)가 없다.
   - 공용 함수 오염 없음: `splitter.py` 는 무변경이므로 `test_splitter.py` 등 타 모듈 테스트에 회귀 요인이 없고, 실제로 70건 전부 통과했다.
   - 경계값: `bill=0` → `split_amount(0, n)` → `[0]*n`; `people=1` → `[bill+tip]`; 총액 < people(`9,3,10`) → `[3,3,3]`. 음수 인자는 `tip.py` 자체 검증이 먼저 걸러 `split_amount` 의 `amount` 기준 예외 메시지가 사용자에게 노출되지 않는다(`bill >= 0`, `tip >= 0` 이므로 `bill + tip >= 0` 항상 성립).
   - 남은 결합도: `tip.py` → `splitter.py` 의존이 새로 생겨 `split_amount` 의 배분 규칙이 바뀌면 `split_tip` 도 영향을 받는다. 다만 두 함수의 배분 규칙이 동일하다는 것이 요구사항 자체이고, `change-log-1.md` 에 이 위험이 명시되어 있어 추적 가능하다. 회귀로 볼 수준은 아니다.

5. **불필요한 변경 여부 — OK**
   변경은 import 1줄과 계산부 교체에 한정된다. 함수명·시그니처·Docstring·검증 블록·에러 메시지 모두 원본 유지. 포맷팅 전면 변경, 리네이밍, 추상화 추가, 의존성 추가 없음. 사용하지 않는 import(`split_amount` 는 `tip.py:33` 에서 사용), 디버깅 `print()`(`grep -rn "print(\|breakpoint(" sample-project/src/` → 0건) 모두 없음. `CLAUDE.md §17` 최소 변경 원칙에 부합한다.

6. **코드 컨벤션 준수 여부 — OK** (`CLAUDE.md §4`, `§6`, `§7`)
   4칸 들여쓰기, `snake_case` 변수(`tip`), 축약어 없음, 함수 책임 1개 유지. 타입 힌트 `(bill: int, people: int, tip_percent: int) -> list[int]` 그대로 유지. Docstring은 이미 정확했으므로 재작성하지 않았고 실제 동작과 이제 일치한다. `settlement.py` 가 `allocation.py` 를 재사용하는 기존 프로젝트 스타일과도 일관된다(`CLAUDE.md §4` "기존 프로젝트 스타일 우선"). 표준 라이브러리·내부 모듈만 사용해 새 의존성 없음.

7. **주석 정책 준수 여부 — OK** (`CLAUDE.md §5`)
   추가된 주석 2블록은 모두 "무엇" 이 아니라 "왜" 를 설명한다. `tip.py:27-28` 은 팁 기준을 1인당 금액이 아닌 청구 금액 전체로 잡아야 하는 이유(추가 유실 방지)를, `tip.py:31-32` 는 총액 확정 후 1회 배분해야 하는 이유와 `split_amount` 재사용 근거를 남긴다. 둘 다 코드만 봐서는 의도를 오해하기 쉬운 지점이라 §5의 "필요한 경우" 에 해당한다. 의미 없는 반복 주석은 없다.

8. **예외 처리 적절성 — OK** (`CLAUDE.md §8`)
   `try/except pass` 형태의 무시가 없다. 구체 예외 `ValueError` 와 입력값을 포함한 메시지(`"people은 1 이상이어야 합니다. (입력값: {people})"`)를 원본 그대로 유지했고, 검증 순서도 보존되어 음수 `tip_percent` 가 총액 계산에 도달하지 않는다. `test_tip.py:44-56` 의 예외 테스트 3건이 통과해 계약 유지가 실증되었다.

## 포트폴리오 품질 기준 (CLAUDE.md §18)

- **다른 개발자가 이해할 수 있는 코드인가 — OK**
  검증 → 팁 계산 → 총액 배분의 3단계 흐름이 선형이며, 본문이 검증 제외 3줄이라 읽는 비용이 낮다.
- **변수와 함수 이름이 명확한가 — OK**
  `tip`, `bill`, `people`, `tip_percent`, `split_amount` 모두 도메인 용어를 그대로 쓴다. 오해를 부르던 `bill_share`/`tip_share`(1인당 값에 팁률을 적용하던 변수)가 사라져 이름과 의미의 불일치가 해소되었다.
- **중요한 구현 이유가 필요한 곳에 설명되어 있는가 — OK**
  이번 버그의 핵심(내림 2회 → 1회, 잔여분 배분 필요)이 정확히 해당 두 줄 위에 주석으로 남아 있다.
- **Git diff가 리뷰하기 쉬운가 — OK**
  실질 변경이 import 1줄 + 계산부 1블록으로 리뷰 단위가 작다.
  참고로 현재 `tip.py` 는 작업 트리에서 CRLF 개행이며(`tr -dc '\r' | wc -c` → 33), 다른 제품/테스트 파일은 LF다. 다만 `git config core.autocrlf` 가 `true` 이고, `git hash-object --path sample-project/src/expense/tip.py sample-project/src/expense/tip.py` 결과(`d489b01…`)가 LF 정규화 내용의 해시와 동일함을 확인했으므로 커밋되는 blob은 LF로 정규화되어 diff가 전체 파일로 부풀지 않는다. 판정에 영향을 주지 않는 참고 사항으로만 기록한다.
- **버그 수정 근거가 명확한가 — OK**
  `test-result-1.md`(FAIL, 8건) → `change-log-2.md`(원인 진단) → `test-result-2.md`(PASS, 70/70) 로 재현·수정·검증이 파일로 추적된다. 특히 2차 진단은 "앞쪽 원소는 기대값과 일치하고 마지막 원소만 0", "`people == 1` 에서 `[0]` 은 배분 계산으로 설명 불가", "나누어떨어지는 입력까지 실패" 라는 실제 실행 근거에서 출발해 1차 가설을 반복하지 않았다(`CLAUDE.md §16` 준수).
- **왜 이렇게 수정했는지 설명 가능한가 — OK**
  "내림이 두 번 일어나 나머지가 두 번 유실된다 → 총액을 먼저 확정해 내림을 1회로 줄이고, 이미 동일 배분 규칙을 구현한 공용 함수를 재사용한다" 로 한 문장 설명이 가능하며, 중복 구현 대신 재사용을 택한 근거도 `change-log-1.md` 에 기록되어 있다.

## 지적 사항

없음.

차단 사유에 해당하는 항목(계획 밖 파일 수정, 테스트 무력화, 주입 결함 잔존, 테스트 실패)이 하나도 확인되지 않았고, 최종 테스트가 `STATUS: PASS` 이므로 `CLAUDE.md §15` 에 따라 승인한다.
