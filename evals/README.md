# PatchPilot Harness Eval

Harness 자체를 검증하는 영역이다. 제품 코드를 고치는 것이 목적이 아니라,
**Orchestrator의 재시도 상태 전이가 실제로 일어나는지**를 결정론적으로 확인하는 것이 목적이다.

운영 실행(`/patchpilot`)에서는 버그가 한 번에 고쳐지면 재시도 경로가 한 번도 실행되지 않는다.
그래서 재시도 경로는 "언젠가 실패했을 때" 우연히 검증되는 상태로 남는다.
Eval은 결함을 의도적으로 주입해 그 경로를 **매번 같은 방식으로** 지나가게 만든다.

> 이 디렉터리에는 검증기가 둘 있다. 이 문서는 **실행 검증**(`eval_harness.py`)만 다룬다.
> **구조 검증**(`harness_audit.py`)은 저장소를 실행하지 않고 정지 상태의 통제 계약을
> 채점하는 별개의 도구이며, 계약은 `CLAUDE.md §26` 에 있다.

---

## 1. 검증 대상 전이

시나리오는 여섯 개다. `--scenario` 를 생략하면 `harness-eval-001` 이 실행된다.

### `harness-eval-001` — PRODUCT_CODE_DEFECT 재시도 루프

```text
Planner
  -> Developer 1차
  -> Fault Injection          (계획 범위 안)
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 1
  -> Developer 2차
  -> Tester PASS
  -> Reviewer APPROVED
  -> SUCCESS
```

### `harness-eval-002` — PLAN_DEFECT 재계획 라우팅

```text
Planner 1차
  -> Developer 1차
  -> Fault Injection          (계획 범위 밖)
  -> Tester FAIL
  -> PLAN_DEFECT
  -> retry_count = 1
  -> Planner 2차              (plan.md 갱신)
  -> Developer 2차
  -> Tester PASS
  -> Reviewer APPROVED
  -> SUCCESS
```

### `harness-eval-003` — ENVIRONMENT_ERROR 즉시 종료 라우팅

```text
Planner
  -> Developer 1차
  -> Fault Injection          (테스트 실행에 필요한 런타임 리소스 삭제)
  -> Tester FAIL
  -> ENVIRONMENT_ERROR
  -> retry_count = 0          (재시도 예산을 소비하지 않는다)
  -> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출
  -> BLOCKED                  (blocked_reason = ENVIRONMENT_ERROR)
```

앞의 두 시나리오가 "재시도가 실제로 일어나는가" 를 본다면, 이 시나리오는 반대로
**"재시도가 실제로 일어나지 않는가"** 를 본다. (`CLAUDE.md §20`, `patchpilot.md §5`)

### `harness-eval-004` — RETRY_BUDGET_EXCEEDED 예산 소진 종료

```text
Planner
  -> Developer 1차            (버그 A 수정)
  -> Fault Injection          (결함 B, 계획 범위 안)
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 1
  -> Developer 2차            (결함 B 제거)
  -> Fault Injection          (결함 C, B 제거 확인 후)
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 2
  -> Developer 3차            (결함 C 제거)
  -> Fault Injection          (결함 D, C 제거 확인 후)
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 3 = retry_budget
  -> Developer 4차 / Tester 4차 / Reviewer 미호출
  -> BLOCKED                  (blocked_reason = RETRY_BUDGET_EXCEEDED)
```

`harness-eval-003` 이 "예산을 **쓰지 않고** 끝나는가" 를 본다면, 이 시나리오는
"예산을 **다 쓰면** 멈추는가" 를 본다. 재시도 루프가 도는 것과 제때 멈추는 것은 다른 성질이며,
후자는 지금까지 어떤 실행에서도 도달한 적이 없는 경로다.

### `harness-eval-005` — TEST_DEFECT_NEEDS_HUMAN 즉시 종료 라우팅

```text
Planner
  -> Developer 1차            (버그 수정, 계획 범위 안)
  -> Fault Injection          (기존 테스트와 모순되는 테스트 하나를 추가)
  -> Tester FAIL
  -> TEST_DEFECT
  -> retry_count = 0          (재시도 예산을 소비하지 않는다)
  -> 테스트를 자동으로 고치지 않는다
  -> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출
  -> BLOCKED                  (blocked_reason = TEST_DEFECT_NEEDS_HUMAN)
```

`harness-eval-003` 과 같은 즉시 종료 경로지만 성질이 다르다. 실행 환경 오류는 **테스트를 한 건도
실행할 수 없는** 상태이고, 이 시나리오는 테스트가 전부 정상 실행되는데도 **어떤 제품 코드로도
전부 통과시킬 수 없는** 상태다.

모순은 두 테스트가 같은 입력에 서로 다른 정확한 반환값을 요구하게 만들어 구성한다.

```python
# 설치된 fixture 안에 원래 있던 테스트
assert apply_coupon(1000, 3) == [334, 333, 333]

# 결함 주입이 덧붙인 테스트
assert apply_coupon(1000, 3) == [333, 333, 334]
```

index 0 이 334 이면서 동시에 333 일 수는 없다. Developer를 몇 번 다시 불러도, 계획 범위를
넓혀도 풀리지 않는다. `CLAUDE.md §20` 은 이 경우 자동으로 테스트를 고치는 것을 금지하므로
Harness 안에서는 해소되지 않고 사람의 판단으로 넘어간다. 이 eval이 검증하는 것은 **Harness가
막혔을 때 막혔다고 보고하는가** 다.

실행 절차는 §14에 있다. 앞선 네 시나리오와 떨어져 있는 이유는 §3~§12의 절 번호를 다른 파일이
계약 참조로 쓰고 있어(`harness_audit.py` 의 CheckSpec — D4 가 §4-12, E3 가 §8, E2 가 §10,
E5 가 §11, E1 이 §12, E6 가 §3-12), 중간에 끼워 넣으면 그 참조가 전부 어긋나기 때문이다.
시나리오를 더 추가할 때도 같은 이유로 문서 끝에 §16, §17 순서로 덧붙인다.

### `harness-eval-006` — REVIEW_CHANGES_REQUESTED_NO_BUDGET Reviewer 예산 소진

```text
Planner
  -> Developer 1차            (버그 수정)
  -> Fault Injection          (결함 B, 계획 범위 안 / 테스트 중립)
  -> Tester PASS
  -> Reviewer CHANGES_REQUESTED
  -> retry_count = 1
  -> Developer 2차            (결함 B 제거)
  -> Fault Injection          (결함 C, B 제거 확인 후)
  -> Tester PASS
  -> Reviewer CHANGES_REQUESTED
  -> retry_count = 2
  -> Developer 3차            (결함 C 제거)
  -> Fault Injection          (결함 D, C 제거 확인 후)
  -> Tester PASS
  -> Reviewer CHANGES_REQUESTED
  -> retry_count = 3 = retry_budget
  -> Developer 4차 / Tester 4차 미호출
  -> BLOCKED                  (blocked_reason = REVIEW_CHANGES_REQUESTED_NO_BUDGET)
```

`harness-eval-004` 와 종료 형태가 닮았지만 **예산을 소비한 주체가 다르다.** 그쪽은 Tester가
매번 실패해서 예산이 마르고, 이쪽은 **Tester가 매번 통과하는데도** Reviewer 판정만으로 마른다.

그래서 주입되는 결함은 반환값과 예외 동작을 한 글자도 바꾸지 않는다. 바꾸는 것은 코드 품질뿐이다.

| 회차 | 주입 결함 | 어기는 규칙 |
| --- | --- | --- |
| 1 | 디버깅용 `print()` 잔존 | `CLAUDE.md §9` |
| 2 | 호출되지 않는 죽은 helper 잔존 | `CLAUDE.md §9`, `§17` |
| 3 | `except Exception: pass` 로 오류를 삼킴 | `CLAUDE.md §8` |

세 규칙이 서로 다른 이유는 §3-17에 있다. 실행 절차는 §15에 있다.

여섯 전이 모두 눈으로 확인하지 않는다. `eval_harness.py` 의 `assert` 가 `reports/<run-id>/` 산출물과
제품 코드 상태만 근거로 자동 판정한다.

---

## 2. 구성

```text
evals/
├── README.md                       # 이 문서 (실행 절차)
├── eval_harness.py                 # setup / inject / assert / finish / teardown / promote / selftest
├── fixtures/
│   ├── HARNESS-EVAL-001.md         # eval 전용 고정 Task (PRODUCT_CODE_DEFECT)
│   ├── tip.py                      # 결함이 있는 제품 코드 (설치 대상)
│   ├── test_tip.py                 # 위 결함을 잡는 테스트 (설치 대상)
│   ├── HARNESS-EVAL-002.md         # eval 전용 고정 Task (PLAN_DEFECT)
│   ├── service_charge.py           # 결함이 있는 대상 모듈 (설치 대상)
│   ├── charge_rounding.py          # 정상 동작하는 협력 모듈 (설치 대상)
│   ├── test_service_charge.py      # 대상 모듈 계약 테스트 (설치 대상)
│   ├── test_charge_rounding.py     # 협력 모듈 계약 테스트 (설치 대상)
│   ├── HARNESS-EVAL-003.md         # eval 전용 고정 Task (ENVIRONMENT_ERROR)
│   ├── conftest_settlement_runtime.py  # 런타임 리소스를 읽는 테스트 부트스트랩 (설치 대상)
│   ├── settlement_runtime.json     # 삭제 대상이 되는 런타임 리소스 (설치 대상)
│   ├── HARNESS-EVAL-004.md         # eval 전용 고정 Task (RETRY_BUDGET_EXCEEDED)
│   ├── installment.py              # 결함이 있는 제품 코드 (설치 대상)
│   ├── test_installment.py         # 위 결함과 요구사항을 잡는 테스트 (설치 대상)
│   ├── HARNESS-EVAL-005.md         # eval 전용 고정 Task (TEST_DEFECT)
│   ├── coupon.py                   # 결함이 있는 제품 코드 (설치 대상)
│   ├── test_coupon.py              # 모순 테스트가 주입될 테스트 (설치 대상)
│   ├── HARNESS-EVAL-006.md         # eval 전용 고정 Task (REVIEW_CHANGES_REQUESTED_NO_BUDGET)
│   ├── refund.py                   # 결함이 있는 제품 코드 (설치 대상)
│   └── test_refund.py              # 반환값 계약 테스트 (설치 대상)
└── faults/
    ├── retry_001.py                # 재시도 루프 검증용 결함 정의 (계획 범위 안)
    ├── plan_defect_001.py          # 재계획 라우팅 검증용 결함 정의 (계획 범위 밖)
    ├── env_error_001.py            # 즉시 종료 라우팅 검증용 결함 정의 (리소스 삭제)
    ├── retry_budget_001.py         # 예산 소진 검증용 1차 결함 (앞 회차 우선 배분 위반)
    ├── retry_budget_002.py         # 예산 소진 검증용 2차 결함 (회차 간 차이 1원 위반)
    ├── retry_budget_003.py         # 예산 소진 검증용 3차 결함 (총액 보존 위반)
    ├── test_defect_001.py          # 사람 판단 필요 라우팅 검증용 결함 정의 (모순 테스트 추가)
    ├── review_budget_001.py        # Reviewer 예산 소진 검증용 1차 결함 (디버깅용 print 잔존)
    ├── review_budget_002.py        # Reviewer 예산 소진 검증용 2차 결함 (죽은 코드 잔존)
    └── review_budget_003.py        # Reviewer 예산 소진 검증용 3차 결함 (오류 무시)
```

시나리오별 설치 대상은 다음과 같다. eval 실행 중에만 설치되고 teardown에서 제거된다.
`sample-project/` 에는 평소에 존재하지 않는다.

`harness-eval-001`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/tip.py` | `sample-project/src/expense/tip.py` |
| `fixtures/test_tip.py` | `sample-project/tests/test_tip.py` |

`harness-eval-002`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/charge_rounding.py` | `sample-project/src/expense/charge_rounding.py` |
| `fixtures/service_charge.py` | `sample-project/src/expense/service_charge.py` |
| `fixtures/test_charge_rounding.py` | `sample-project/tests/test_charge_rounding.py` |
| `fixtures/test_service_charge.py` | `sample-project/tests/test_service_charge.py` |

`harness-eval-003`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/tip.py` | `sample-project/src/expense/tip.py` |
| `fixtures/test_tip.py` | `sample-project/tests/test_tip.py` |
| `fixtures/conftest_settlement_runtime.py` | `sample-project/tests/conftest.py` |
| `fixtures/settlement_runtime.json` | `sample-project/config/settlement_runtime.json` |

`harness-eval-004`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/installment.py` | `sample-project/src/expense/installment.py` |
| `fixtures/test_installment.py` | `sample-project/tests/test_installment.py` |

`harness-eval-005`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/coupon.py` | `sample-project/src/expense/coupon.py` |
| `fixtures/test_coupon.py` | `sample-project/tests/test_coupon.py` |

`harness-eval-006`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/refund.py` | `sample-project/src/expense/refund.py` |
| `fixtures/test_refund.py` | `sample-project/tests/test_refund.py` |

`harness-eval-004` 는 앞의 세 시나리오와 설치 경로가 겹치지 않는 전용 모듈을 쓴다. 결함 세 개가
각각 **다른 요구사항** 을 깨뜨려야 하므로, 그 요구사항 분리를 fixture 설계 단계에서 보장해야
하기 때문이다.

`harness-eval-005` 도 전용 모듈을 쓴다. 결함 주입이 **테스트 파일 자체** 를 대상으로 하므로,
설치 경로를 다른 시나리오와 공유하면 주입 대상이 어느 시나리오의 것인지 기계적으로 구분할 수
없기 때문이다.

`harness-eval-003` 은 제품 버그와 그 테스트를 `harness-eval-001` 과 공유한다. 이 시나리오가
바꾸는 변수는 제품 버그가 아니라 결함의 종류 하나이기 때문이다. 시나리오는 동시에 실행되지
않고 `setup` 은 설치 대상이 이미 존재하면 거부하므로, 설치 경로를 공유해도 서로 간섭하지 않는다.

`sample-project/config/` 처럼 setup이 새로 만든 디렉터리는 상태 파일의 `created_dirs` 에
기록되고 teardown에서 비어 있을 때 함께 제거된다. 빈 디렉터리는 `git status` 에 나타나지
않으므로 상태 비교만으로는 복구 여부를 확인할 수 없기 때문이다.

`evals/.eval-run/state.json` 은 실행 중 상태(시나리오, 설치 목록, 원상태 스냅샷, 설치 전 테스트
기준선, 주입 기록)를 담는 임시 파일이며 Git에 커밋하지 않는다.

---

## 3. 설계 결정

### 3-1. 결함 제거는 Harness가 아니라 Developer 2차가 한다

`eval_harness.py` 는 결함을 **주입만** 하고 되돌리지 않는다.
Harness가 스스로 되돌리면 재수정 주체가 Developer가 아니게 되어
`FAIL -> 분석 -> 재수정 -> PASS` 전이의 검증 의미가 사라지기 때문이다.

Developer 2차는 `test-result-1.md` 를 읽고 실제 제품 코드 결함을 진단해 제거해야 한다.
제거 여부는 `assert` 가 결함 표식(`patchpilot-eval:retry_001`)의 부재와 파일 해시 변경으로 판정한다.

### 3-2. FAIL은 문자열 조작이 아니라 실제 테스트 실패로 만든다

`test-result-N.md` 의 `STATUS:` 를 임의로 `FAIL` 로 바꾸지 않는다.
Tester는 언제나 고정 명령 `uv run pytest sample-project/tests -q` 를 실제로 실행하고 그 결과를 기록한다.
`assert` 는 `test-result-1.md` 에 고정 실행 명령과 실패 테스트 이름이 남아 있는지도 함께 확인한다.

### 3-3. 운영 Harness는 건드리지 않는다

이 eval은 `.claude/agents/*.md` 와 `.claude/commands/patchpilot.md` 를 수정하지 않는다.
Agent는 자신이 eval 중이라는 사실을 모른 채 평소와 동일한 규칙으로 동작한다.
결함 주입 시점만 Orchestrator가 절차상 한 번 끼워 넣는다.

### 3-4. 결함 주입은 구현 세부사항에 의존하지 않는다

`faults/retry_001.py` 는 `tip.py` 끝에 후처리 래퍼를 덧붙인다.
Developer 1차가 함수 본문을 어떻게 고쳤든 모듈 최상위에 `def split_tip(` 정의만 있으면
동일하게 적용되므로 주입 결과가 결정론적이다. 전제 조건이 깨지면 주입하지 않고 실패한다.

### 3-5. PLAN_DEFECT는 Planner의 실수를 기다려서 만들지 않는다

`harness-eval-002` 의 핵심은 **plan 1차의 좁은 범위가 실수가 아니라 정답** 이라는 데 있다.

Planner 1차 시점에 `charge_rounding.py` 는 정상 동작한다. 결함은 `service_charge.py` 에만
있으므로, `CLAUDE.md §17`(최소 변경)과 `planner.md §3-4`(범위를 가능한 한 좁힌다)에 따르면
수정 허용 파일 목록은 `service_charge.py` 하나로 수렴한다. 어떤 성실한 Planner가 와도 같다.

그 뒤 Harness가 **허용 목록 밖** 인 `charge_rounding.py` 에 결함을 주입한다. 이 순간
plan.md의 원인 분석이 현재 코드 기준으로 사실이 아니게 된다. `harness-eval-001` 이 제품 코드를
사후적으로 깨뜨리는 것과 같은 방식으로, 여기서는 **계획이 사후적으로 불완전해진다.**

`faults/plan_defect_001.py` 는 주입 전에 `precheck` 로 plan 1차의 허용 목록을 읽고,
주입 대상이 이미 목록 안에 있으면 **주입하지 않고 실패시킨다.** 전제가 깨진 채로 eval이
조용히 통과하는 일을 막기 위해서다.

### 3-6. Developer만으로는 고칠 수 없다는 것이 구조로 보장된다

`tests/test_charge_rounding.py` 는 협력 모듈의 `round_to_unit` 을 **직접** 호출해 검증한다.
따라서 `service_charge.py` 안에서 무엇을 해도 이 테스트는 통과시킬 수 없다.

Developer는 `CLAUDE.md §3-2` 에 따라 허용 목록 밖 파일을 수정할 수 없으므로, 같은 plan.md로
Developer를 다시 부르면 change-log에 "범위 밖 수정 필요" 만 남기고 중단한다.
이것이 `CLAUDE.md §14` 의 `PLAN_DEFECT` 정의 — 같은 계획으로는 요구사항을 만족할 수 없어
Planner를 다시 불러야 하는 상태 — 와 정확히 일치한다.

### 3-7. Planner 재호출 증거는 Harness가 스냅샷으로 남긴다

Planner는 운영과 동일하게 `plan.md` **하나만** 쓴다. 운영 `/patchpilot` 의 규칙은 바뀌지 않는다.

재호출을 증명하기 위해 Harness가 두 시점의 `plan.md` 를 복사해 둔다.

| 산출물 | 복사 시점 |
| --- | --- |
| `plan-1.md` | `inject` 실행 시 (Developer 1차 종료 후, Planner 2차 호출 전) |
| `plan-2.md` | `assert` / `finish` 실행 시 |

`assert` 는 두 파일의 해시, 수정 허용 파일 목록, 예상 원인 본문이 실제로 달라졌는지 판정한다.

`harness-eval-003` 은 같은 스냅샷을 반대 방향으로 쓴다. 결함 주입 시점의 `plan-1.md` 와
종료 시점의 `plan.md` 해시가 **같다는 것** 이 Planner가 다시 호출되지 않았다는 증거가 된다.

### 3-8. ENVIRONMENT_ERROR 도 실제 실행 결과로만 만든다

`test-result-N.md` 의 `STATUS:` 나 실패 원인 분류 문자열을 Harness가 대신 써 넣지 않는다는
원칙은 세 시나리오 모두 같다. `harness-eval-003` 에서 Tester가 실제로 겪는 것은 다음이다.

```text
ImportError while loading conftest 'sample-project/tests/conftest.py'.
E   RuntimeError: 정산 런타임 설정 리소스를 찾을 수 없습니다: sample-project/config/settlement_runtime.json
```

pytest는 종료 코드 4로 끝나고 테스트는 한 건도 수집되지 않는다. "코드가 틀렸다" 가 아니라
"실행 환경이 준비되지 않아 실행 자체가 불가능하다" 는 상태가 실행 결과로 드러난다.
(`tester.md §3` 의 `ENVIRONMENT_ERROR` 기준)

### 3-9. 실행 환경 오류는 제품 코드를 깨뜨려서 만들지 않는다

`env_error_001` 은 제품 코드를 한 글자도 고치지 않는다. 제품 코드를 깨뜨리면
`PRODUCT_CODE_DEFECT` 로 분류하는 것이 **옳은 판정** 이 되어 검증하려는 경로를 지나가지 못한다.

대신 테스트 실행에 필요한 런타임 리소스(`sample-project/config/settlement_runtime.json`)를
지운다. 이 리소스는 제품 코드가 아니라 실행 환경이 배치하는 파일이고, 없으면 수집 단계에서
실행이 중단되므로 원인이 제품 코드 바깥에 있다는 것이 실행 결과만으로 드러난다.

### 3-10. 삭제는 이번 eval이 설치한 untracked 리소스로만 제한한다

파일 삭제는 되돌릴 수 없으므로 결함 정의와 Harness가 같은 조건을 **각각** 검사한다.
하나라도 어긋나면 지우지 않고 즉시 실패한다.

| 조건 | 확인 주체 |
| --- | --- |
| `sample-project/` 안의 상대 경로 (절대 경로·상위 경로 참조 거부) | `eval_harness.py` |
| 심볼릭 링크가 아님 | `eval_harness.py` |
| Git 추적 파일이 아님 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 이번 eval의 `setup` 이 설치한 파일임 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 파일 내용에 `patchpilot-eval:env_error_001` 표식이 있음 | `env_error_001.precheck_fs` |

실제 삭제는 결함 정의가 아니라 `eval_harness.py` 한 곳에서만 수행한다. 파일을 지우는 코드가
여러 곳에 흩어지면 안전 조건을 한곳에서 보장할 수 없기 때문이다.

### 3-11. 즉시 종료 전이는 "일어나지 않은 일" 로 판정한다

`harness-eval-001` / `harness-eval-002` 는 재시도가 일어났다는 증거(2차 산출물)를 찾는다.
`harness-eval-003` 은 반대로 다음이 **하나도 없어야** 통과한다.

* `change-log-2.md` (Developer 2차)
* `test-result-2.md` (Tester 2차)
* `review.md` (Reviewer)
* `plan.md` 의 변경 (Planner 2차)
* `state.json` 의 `retry_count > 0`, `attempts` 2건, `review.verdict` 값

산출물이 없다는 사실만으로는 "Agent가 호출되지 않았다" 와 "호출됐지만 파일을 쓰지 않았다" 를
구분할 수 없다. 그래서 `state.json` 의 `retry_count` / `attempts` / `review` 기록을 함께 본다.
Orchestrator는 어떤 경로로 끝나든 `state.json` 과 `report.md` 를 남겨야 하므로
(`patchpilot.md §10`), 이 세 값이 비어 있다는 것은 라우팅이 실제로 즉시 종료됐다는 뜻이다.

### 3-12. 같은 결함을 반복 주입하지 않는다

`harness-eval-004` 는 시도마다 **다른** 결함을 주입한다. 선택지는 네 가지였다.

| 방식 | 결정론 | Developer 재수정 검증 | 채택 |
| --- | --- | --- | --- |
| 같은 결함을 매 시도 재주입 | 높음 | 불가능 | X |
| 시도별 다른 결함 (제거 확인 없음) | 높음 | 약함 | X |
| 시도별 다른 결함 + 직전 결함 제거 확인 | 높음 | 강함 | **O** |
| 같은 함수의 독립 결함을 순차 주입 | 높음 | 위와 병행 | **O** |

같은 결함을 다시 주입하면 Developer가 무엇을 고쳤는지와 무관하게 매번 같은 실패가 난다.
그것은 "Harness가 Developer의 수정을 몰래 되돌리는 구조" 와 구분되지 않으므로, 재시도 루프가
실제로 돌았는지 판정할 수 없다.

그래서 `split_installments` 의 **서로 다른 요구사항** 을 하나씩 깨뜨리는 결함 세 개를 쓴다.

| 순번 | 결함 | 깨뜨리는 요구사항 | 새로 실패하는 테스트 |
| --- | --- | --- | --- |
| 1 | `retry_budget_001` | 나머지는 앞 회차부터 배분 | `..._distributes_remainder_to_earlier_months_first` |
| 2 | `retry_budget_002` | 회차 간 차이는 최대 1원 | `..._difference_between_installments_is_at_most_one_won` |
| 3 | `retry_budget_003` | 회차별 금액의 합계 = 총액 | `..._preserves_total_when_total_is_not_evenly_divisible` |

세 결함은 실패 증상이 겹치지 않도록 배치되어 있다. `assert` 는 N차 실패 테스트가 **이전
시도에는 없었다는 것** 까지 확인하므로, 같은 실패의 반복으로는 통과할 수 없다.

이때 실패의 근거는 pytest 요약 줄(`FAILED <path>::<test_name>`)에서 뽑은 실패 테스트 집합뿐이다.
(`failed_test_names`) Tester가 설명 절에 적은 테스트 이름 — 예를 들어 "이미 존재하는 회귀 테스트
목록" — 은 실패 증거로 보지 않는다. 문서 전체를 문자열로 훑으면 통과한 테스트가 실패로 잡혀
판정이 무너진다.

### 3-13. 다음 결함은 직전 결함이 제거된 뒤에만 주입한다

`inject --attempt N` (N ≥ 2)은 주입 **직전에** 다음을 확인하고, 하나라도 어긋나면 결함을
주입하지 않고 즉시 실패한다.

| 조건 | 확인 방법 |
| --- | --- |
| 직전 결함 표식이 사라졌다 | `patchpilot-eval:retry_budget_00N` 문자열 부재 |
| 대상 파일 내용이 실제로 바뀌었다 | 직전 주입 직후 sha256 과 현재 sha256 비교 |
| Developer N차가 실행됐다 | `change-log-N.md` 존재 |
| Developer N차가 이전 실패를 근거로 삼았다 | 이전 시도 참조 표현 + 이전 실행에서 관측된 값 인용 (아래) |
| 결함 정의의 연결이 맞다 | `PREVIOUS_FAULT_ID` 가 실제 직전 주입 결함과 일치 |

근거 사용 여부는 파일 이름 문자열 하나로 판정하지 않는다. `previous_failure_reference` 가 두
신호를 함께 본다.

1. 이전 시도를 가리키는 참조 표현 — `test-result-2`, `2차 실패`, `이전 실패` 등
2. 이전 `test-result` 에서 실제로 관측된 값의 인용 — 실패 테스트 이름, pytest 집계 줄
   (`3 failed, 65 passed`), assertion 에 나온 정수 목록(`[3001, 3000, 2999]`)

1번만 있으면 "이전 실패를 확인했다" 는 형식 문구로 통과하고, 2번만 있으면 이전 결과와 무관하게
우연히 같은 값을 적은 경우와 구분되지 않는다. 둘을 함께 요구하면 표현 차이(`2차 실패` vs
`test-result-2.md`) 때문에 실제 근거 사용이 탈락하는 일도, 형식만 갖춘 기록이 통과하는 일도 없다.

이 게이트가 있으면 **Developer가 아무것도 고치지 못하는 구조** 가 성립할 수 없다.
Developer가 직전 결함을 남겨두면 다음 결함이 주입되지 않고 eval이 그 자리에서 실패한다.

확인 결과는 `fault-injection-N.md` 의 "직전 결함 제거 확인" 절과 실행 상태 파일의
`injections[N-1]` 에 남고, `assert` 가 그 기록을 근거로 다시 판정한다.

### 3-14. 마지막 결함은 아무도 제거하지 않는다

`retry_budget_003` 은 Tester 3차를 실패시킨 뒤 예산이 소진되므로 제거 주체가 없다.
종료 시점까지 이 결함이 대상 파일에 **그대로 남아 있다는 사실** 이, 예산 소진 이후 Developer가
호출되지 않았다는 물리적 증거가 된다. (표식 존재 + 주입 직후 sha256 과 동일)

`harness-eval-003` 의 "삭제된 리소스가 복구되지 않음" 과 같은 논법이다.
결함은 teardown이 fixture 파일과 함께 통째로 제거한다.

### 3-15. 테스트에 주입하되 기존 테스트는 건드리지 않는다

`test_defect_001` 은 유일하게 **테스트 파일** 을 주입 대상으로 삼는다. `CLAUDE.md §3-3` 이
금지하는 테스트 약화를 결함 주입 스스로가 저지르면, 검증 대상 상황이 아니라 Harness가 규칙을
어긴 상황이 되므로 주입은 **덧붙이기만** 한다.

이 전제는 선언으로 두지 않고 양쪽에서 기계로 강제한다.

* **주입 전** — 대상이 이번 eval이 설치한 `sample-project/tests/` 안의 untracked 파일이고,
  내용이 설치 원본 fixture와 **완전히 같을** 때만 주입한다. 이미 누가 손댄 파일이라면
  "기존 테스트를 그대로 두고 하나만 추가했다" 가 성립하지 않으므로 주입하지 않고 실패시킨다.
* **주입 후** — 판정은 표식 존재 여부가 아니라 **설치 원본 fixture + 주입 코드** 와의 완전
  비교다. 표식만 보면 "주입된 테스트는 남겨 두고 기존 테스트를 고친" 경우를 놓친다.
  완전 비교는 삭제·assertion 변경·skip 추가·rename 을 한 번에 배제한다.

### 3-16. TEST_DEFECT 분류를 프롬프트로 알려주지 않는다

Tester에게 "이것은 테스트 결함이다" 라고 알려주면 검증 대상이 사라진다. Tester가 실제로 받는
것은 고정 실행 명령과 산출물 경로뿐이고, 분류는 `tester.md` 의 기준으로 스스로 내린다.

그래서 모순은 **기계적으로 관측 가능한 형태** 로 만든다. 같은 입력에 대한 두 개의 정확한
반환값 요구는 코드를 읽으면 양립 불가능하다는 것이 드러나고, 판단에 추측이 필요 없다.

### 3-17. Reviewer 경로의 결함은 계획 범위 **안** 에 둔다

`harness-eval-006` 을 설계할 때 처음 떠오르는 구성은 "계획 허용 목록 **밖** 파일에 결함을 두고,
Developer가 지우려 하면 `guard_plan_scope.py` 가 막는다" 였다. 이 구성은 성립하지 않는다.

Developer가 범위 밖 수정이 필요하다고 판단하면 `developer.md §3` 에 따라 수정하지 않고 그
사유만 change-log에 적고 중단한다. 그러면 `patchpilot.md §3` 이 그 상태를 그대로 집어낸다.

> change-log의 "범위 밖 수정 필요 여부" 에 수정이 필요하다고 적혀 있고 실제 코드 변경이 없다
> → `BLOCKED` (사유: `SCOPE_OUT_OF_PLAN`)

즉 `retry_count = 1` 시점에 **다른 종료 경로** 로 끝난다. `REVIEW_CHANGES_REQUESTED_NO_BUDGET`
에는 도달할 수 없다.

그래서 결함을 계획 허용 목록 **안** 에 둔다. Developer가 매 회차 실제로 제거할 수 있어야
Developer → Tester → Reviewer 루프가 3회 돌고 예산이 Reviewer 지적으로만 소진된다.
이 전제는 각 결함의 `precheck` 가 `plan.md` 를 읽어 직접 검사하며, 어긋나면 주입하지 않는다.

### 3-18. Reviewer에게 기대 판정을 알려주지 않는다

Tester에게 실패 분류를 알려주지 않는 것과 같은 이유다(§3-16). Reviewer가 받는 것은 run-id,
task 경로, 필수 입력 경로, `git diff` 를 직접 확인하라는 지시, 그리고 실행 시작 시점의
`start_commit` / `start_dirty_files` 뿐이다. 이것은 `patchpilot.md §7` 이 정한 프롬프트
구성 그대로이며 eval 전용 항목이 하나도 없다.

판정의 결정론성은 프롬프트가 아니라 **상황** 에서 나온다. 세 결함은 각각 `CLAUDE.md` 가
금지 예시나 완료 확인 항목으로 **문서에 그대로 적어 둔** 위반이다. 특히 3차 결함
(`except Exception: pass`)은 `CLAUDE.md §8` 이 금지 예시로 같은 형태를 인용하고 있다.

회차마다 다른 규칙을 어기게 만든 이유도 여기에 있다. 같은 지적이 세 번 반복되면 Reviewer가
그 회차의 코드를 실제로 다시 검토한 것인지, 직전 판정을 되풀이한 것인지 구분할 수 없다.

---

## 4. 실행 절차 — `harness-eval-001` (PRODUCT_CODE_DEFECT)

Orchestrator(메인 Claude Code 세션)가 아래 순서를 그대로 수행한다.
Agent 호출 규칙, `state.json` 필드, FAIL 라우팅, 재시도 예산은
`.claude/commands/patchpilot.md` 와 `CLAUDE.md §14 / §16 / §19 / §20` 을 그대로 따른다.

### 4-0. 사전 조건

`git status --porcelain -- sample-project` 가 깨끗한 상태에서 시작하는 것을 권장한다.
(더러워도 실행은 되지만, 복구 판정은 setup 시점 스냅샷과의 비교로 이루어진다.)

### 4-1. setup

```bash
uv run python evals/eval_harness.py setup
```

fixture를 설치하고 `sample-project/` 원상태를 스냅샷한다.
`--scenario` 를 생략하면 `harness-eval-001` 이 실행된다.

### 4-2. Planner

`.claude/commands/patchpilot.md §1~§2` 절차대로 run-id를 만들고 `reports/<run-id>/` 를 생성한 뒤
`planner` 를 호출한다. Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-001.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-001` 이 된다.

`reports/<run-id>/plan.md` 확인 후 진행한다.

### 4-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 4-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

`reports/<run-id>/fault-injection.md` 가 생성된다.

### 4-5. Tester 1차

`tester` 를 시도 번호 `N = 1` 로 호출한다.
`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `PRODUCT_CODE_DEFECT` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester는 평소처럼 실행 결과만 보고 판정한다.

### 4-6. FAIL 라우팅

`PRODUCT_CODE_DEFECT` 이므로 `retry_count` 를 1 증가시키고 Developer를 다시 호출한다.
(`CLAUDE.md §20`)

### 4-7. Developer 2차

`developer` 를 시도 번호 `N = 2` 로 호출한다.
프롬프트에 `test-result-1.md` 와 `change-log-1.md` 를 필수 입력으로 전달한다.
Developer 2차가 주입된 결함을 제거해야 한다.

### 4-8. Tester 2차

`tester` 를 시도 번호 `N = 2` 로 호출한다. `test-result-2.md` 가 `STATUS: PASS` 여야 한다.

### 4-9. Reviewer

`reviewer` 를 호출한다. `review.md` 가 `VERDICT: APPROVED` 여야 한다.

### 4-10. 보고서와 상태 마감

`report.md` 와 `state.json` 을 작성한다. 최종 상태는 `SUCCESS` 다.

### 4-11. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 검증이 실패하거나 검증 중 예외가 나더라도 `finally` 에서 teardown을 수행한다.
따라서 eval이 실패해도 `sample-project/` 는 정리된다.

* 종료 코드 `0` → eval PASS
* 종료 코드 `1` → eval FAIL (판정 근거는 `reports/<run-id>/eval-result.md`)

검증만 하고 teardown을 미루려면 `assert` 를, 정리만 하려면 `teardown` 을 쓴다.

```bash
uv run python evals/eval_harness.py assert --run-id <run-id>
uv run python evals/eval_harness.py teardown
uv run python evals/eval_harness.py status
```

Agent 실행 없이 harness 자체의 회귀만 확인하려면 `selftest` 를 쓴다. (§10)

```bash
uv run python evals/eval_harness.py selftest
```

### 4-12. 대표 결과 승격 (선택)

일반 실행 결과인 `reports/<run-id>/` 는 `.gitignore` 로 커밋되지 않는다.
검증에 통과한 대표 실행 하나만 골라 커밋 대상으로 복사한다.

```bash
uv run python evals/eval_harness.py promote --run-id <run-id>
```

`reports/examples/EVAL-<YYYYMMDD-HHMM>-HARNESS-EVAL-001/` 에 다음 파일이 복사된다.
`eval-result.md` 의 첫 줄이 `EVAL: PASS` 가 아니면 승격을 거부한다.

```text
fault-injection.md
change-log-1.md
test-result-1.md
change-log-2.md
test-result-2.md
review.md
report.md
state.json
plan.md          (있으면 함께 복사)
eval-result.md   (있으면 함께 복사)
```

폴더 이름을 직접 지정하려면 `--name EVAL-RETRY-001` 처럼 넘긴다.

---

## 5. 실행 절차 — `harness-eval-002` (PLAN_DEFECT)

§4와 다른 부분만 적는다. 나머지는 동일하다.

### 5-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-002
```

모듈 2개와 테스트 2개를 설치한다. 이 시점의 `charge_rounding.py` 는 **정상** 이다.

### 5-2. Planner 1차

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-002.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-002` 가 된다.

`plan.md` 의 수정 허용 파일 목록은 `sample-project/src/expense/service_charge.py` 하나여야 한다.
이 시점에는 그것이 **옳은 계획** 이다. (§3-5)

### 5-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 5-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

이때 두 가지가 함께 일어난다.

1. `reports/<run-id>/plan-1.md` 에 Planner 1차 산출물이 복사된다.
2. `plan-1.md` 의 수정 허용 파일 목록을 `precheck` 로 검사한 뒤, 목록 **밖** 인
   `charge_rounding.py` 에 결함을 주입한다.

### 5-5. Tester 1차

`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `PLAN_DEFECT` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester가 실제로 보게 되는 것은 다음이다.

* `tests/test_charge_rounding.py` 4건 실패 — 협력 모듈을 직접 호출하는 계약 테스트
* `tests/test_service_charge.py` 2건 실패 — 정산 단위 올림이 관여하는 경우만
* 나머지 통과 — Developer 1차가 고친 나머지 배분 동작은 정상이다

즉 "Developer의 수정은 계획대로 동작하는데, 계획이 범위에 넣지 않은 파일 때문에 요구사항을
만족할 수 없다" 는 상태가 실제 실행 결과로 드러난다.

### 5-6. FAIL 라우팅

`PLAN_DEFECT` 이므로 `retry_count` 를 1 증가시키고 `current_stage` 를 `PLANNING` 으로 되돌린 뒤
**Planner** 를 다시 호출한다. (`CLAUDE.md §20`, `patchpilot.md §5`)

### 5-7. Planner 2차

`planner` 를 재계획 사유와 함께 호출한다. 필수 입력은 다음이다.

* 기존 `reports/<run-id>/plan.md`
* `reports/<run-id>/test-result-1.md`
* 현재 코드

갱신된 `plan.md` 는 수정 허용 파일 목록에 `charge_rounding.py` 를 추가하고, 이전 계획의 어느
판단이 부족했는지를 명시해야 한다. (`planner.md §3`)

### 5-8. Developer 2차 이후

시도 번호 `N = 2` 로 Developer → Tester → Reviewer 를 §4-7 ~ §4-10과 동일하게 진행한다.
Developer 2차가 주입된 결함을 제거해야 한다.

### 5-9. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 판정 직전에 현재 `plan.md` 를 `plan-2.md` 로 복사한 뒤 1차와 비교한다.

---

## 6. 실행 절차 — `harness-eval-003` (ENVIRONMENT_ERROR)

§4와 다른 부분만 적는다. 나머지는 동일하다.

### 6-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-003
```

제품 모듈과 테스트(001과 동일), 테스트 부트스트랩 `conftest.py`, 런타임 리소스
`config/settlement_runtime.json` 네 개를 설치한다. 이 시점에는 리소스가 **정상적으로 존재** 하며
`test_tip.py` 만 제품 버그로 실패한다.

### 6-2. Planner

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-003.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-003` 이 된다.

### 6-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 6-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

이때 두 가지가 함께 일어난다.

1. `reports/<run-id>/plan-1.md` 에 Planner 1차 산출물이 복사된다.
   (Planner가 다시 호출되지 않았음을 나중에 해시로 판정하기 위한 기준이다)
2. §3-10의 조건을 모두 통과한 경우에만 런타임 리소스를 삭제한다.

### 6-5. Tester 1차

`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `ENVIRONMENT_ERROR` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester가 실제로 보게 되는 것은 conftest 로딩 실패로
테스트가 한 건도 수집되지 않는 pytest 출력뿐이다. (§3-8)

### 6-6. FAIL 라우팅 — 여기서 끝난다

`ENVIRONMENT_ERROR` 는 코드 결함이 아니므로 **`retry_count` 를 증가시키지 않고** 즉시
`BLOCKED` 로 종료한다. (`CLAUDE.md §20`, `patchpilot.md §5`)

Developer도 Planner도 Reviewer도 다시 호출하지 않는다. Orchestrator는 `report.md` 와
`state.json` 만 마감한다. `blocked_reason` 은 `ENVIRONMENT_ERROR` 다.

### 6-7. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 검증 결과와 무관하게 teardown을 수행한다. 삭제된 런타임 리소스는 복구하지 않는다.
teardown이 나머지 fixture와 함께 정리하고, setup이 만든 `sample-project/config/` 디렉터리도
비어 있으면 제거한다.

---

## 7. 실행 절차 — `harness-eval-004` (RETRY_BUDGET_EXCEEDED)

§4와 다른 부분만 적는다. 나머지는 동일하다.

이 시나리오만 **결함 주입이 3회** 다. Developer 호출과 Tester 호출 사이마다 한 번씩 들어간다.

### 7-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-004
```

제품 모듈과 테스트를 설치하고, fixture 설치 **전** 의 전체 테스트 결과를 기준선으로 기록한다.
teardown 이후 이 결과(`57 passed`)로 돌아와야 한다.

### 7-2. Planner

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-004.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-004` 가 된다.

`plan.md` 의 수정 허용 파일 목록에 `sample-project/src/expense/installment.py` 가 있어야 한다.
결함 정의가 주입 전에 `precheck` 로 이 조건을 확인하고, 없으면 주입하지 않고 실패시킨다.
주입 대상이 계획 범위 **안** 이어야 세 번의 실패가 모두 `PRODUCT_CODE_DEFECT` 로 분류된다.
(`harness-eval-002` 의 정확한 반대 조건이다)

### 7-3. 시도 1 ~ 3 반복

`N = 1, 2, 3` 에 대해 다음을 반복한다.

1. **Developer N차** 호출 → `change-log-N.md`
   * `N = 1`: 버그 A(총액 유실)를 수정한다.
   * `N >= 2`: `test-result-{N-1}.md` 를 근거로 직전에 주입된 결함을 제거한다.
2. **결함 주입** — Tester를 호출하기 **전에** 한 번 실행한다.

   ```bash
   uv run python evals/eval_harness.py inject --run-id <run-id> --attempt N
   ```

   * `--attempt` 는 필수다. 생략하거나 순서가 어긋나면 주입하지 않고 실패한다.
   * `N >= 2` 이면 직전 결함이 제거됐는지 먼저 확인한다. (§3-13)
   * 산출물은 `fault-injection-N.md` 다. `N = 1` 에서는 `plan-1.md` 스냅샷도 함께 남는다.
3. **Tester N차** 호출 → `test-result-N.md`
   * `STATUS: FAIL`, 실패 원인 분류는 `PRODUCT_CODE_DEFECT` 가 되어야 한다.
   * Tester에게 결함 주입 사실을 알리지 않는다.
4. **FAIL 라우팅** (`patchpilot.md §5`, `§6`)
   * `retry_count += 1`
   * `retry_count < 3` → Developer를 다시 호출한다. (1로 돌아간다)
   * `retry_count >= 3` → 여기서 끝난다. (7-4로 간다)

### 7-4. 예산 소진 — 여기서 끝난다

Tester 3차의 FAIL로 `retry_count` 가 3이 되어 예산이 모두 소비된다.

Developer 4차도, Tester 4차도, Reviewer도 호출하지 않는다. 4차 결함 주입도 하지 않는다.
Orchestrator는 `report.md` 와 `state.json` 만 마감한다. `blocked_reason` 은
`RETRY_BUDGET_EXCEEDED` 다.

마지막으로 주입된 `retry_budget_003` 은 제품 코드에 **남은 채로** 종료된다. (§3-14)

### 7-5. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

teardown은 결함이 남아 있는 fixture 파일을 통째로 제거하고, 전체 테스트 결과가 setup 시점
기준선으로 돌아왔는지까지 확인한다.

> `harness-eval-005` (TEST_DEFECT) 의 실행 절차는 §14,
> `harness-eval-006` (REVIEW_CHANGES_REQUESTED_NO_BUDGET) 의 실행 절차는 §15에 있다.

---

## 8. 자동 검증 항목

`assert` / `finish` 가 판정하는 항목이다. 하나라도 실패하면 eval은 FAIL이다.

### 8-1. 재시도 후 성공하는 시나리오 공통 (`harness-eval-001` 기준 25항목 + teardown 2항목 = 27항목)

| 구분 | 항목 |
| --- | --- |
| 산출물 | `plan.md`, `change-log-1.md`, `change-log-2.md`, `report.md` 존재 |
| 결함 주입 | `fault-injection.md` 존재, 주입이 Developer 1차 이후에 이루어짐 |
| Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| Tester 1차 | 주입된 결함의 실패 테스트 기록 (001 `test_tip` / 002 `test_charge_rounding`) |
| 라우팅 | 실패 원인 분류가 시나리오의 기대 분류와 일치 (001 `PRODUCT_CODE_DEFECT` / 002 `PLAN_DEFECT`) |
| Developer 2차 | `change-log-2.md` 가 `test-result-1.md` 를 근거로 참조 |
| Tester 2차 | 첫 줄이 `STATUS: PASS`, 고정 실행 명령 기록 |
| Reviewer | 첫 줄이 `VERDICT: APPROVED` |
| 상태 | `state.json` 의 `retry_count == 1` |
| 상태 | `state.json` 의 `final_status == SUCCESS`, `current_stage == DONE`, `blocked_reason` 없음 |
| 상태 | `attempts` 2건, `[0]` 이 FAIL/기대 분류, `[1]` 이 PASS |
| 결함 제거 | 결함 표식이 사라지고 대상 파일 해시가 실제로 변경됨 |
| 테스트 무결성 | fixture 테스트 함수가 하나도 사라지지 않고 `skip` 이 추가되지 않음 |
| 범위 | eval 실행이 기존 추적 파일을 변경하지 않음 |
| 복구 | teardown 후 설치한 eval fixture 가 전부 제거됨 |
| 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |

### 8-2. `harness-eval-002` 추가 항목 (10항목, 총 35 + teardown 2 = 37항목)

| 구분 | 항목 |
| --- | --- |
| Planner 1차 | `plan-1.md` 스냅샷 존재 |
| 주입 전제 | 주입 대상이 `plan-1.md` 의 수정 허용 파일 목록 **밖** |
| 주입 전제 | `plan-1.md` 의 수정 허용 파일 목록이 `service_charge.py` 하나로 한정됨 |
| Planner 2차 | `plan-2.md` 스냅샷 존재 |
| Planner 2차 | `plan-1.md` 와 `plan-2.md` 의 내용(sha256)이 실제로 다름 |
| Planner 2차 | `plan-2.md` 가 1차 허용 목록을 유지하면서 주입 대상 파일을 추가 |
| Planner 2차 | `plan-2.md` 가 `test-result-1.md` 를 재계획 근거로 참조 |
| Planner 2차 | `plan-1.md` 와 `plan-2.md` 의 "예상 원인" 본문이 다름 |
| Developer 2차 | `change-log-2.md` 의 변경 파일에 주입 대상 파일이 포함됨 |
| 범위 준수 | Developer가 바꾼 파일이 모두 `plan-2.md` 의 수정 허용 목록 안에 있음 |

`plan-1.md` / `plan-2.md` 는 `promote` 시 대표 결과에도 함께 복사된다.

### 8-3. `harness-eval-003` 항목 (26항목 + teardown 2 = 28항목)

즉시 종료 시나리오는 §8-1의 "재시도 성공" 항목들(Developer 2차 / Tester 2차 / Reviewer /
`final_status == SUCCESS`)을 쓰지 않는다. 판정 항목 전체는 다음과 같다.

| # | 구분 | 항목 |
| --- | --- | --- |
| 1 | 산출물 | `plan.md` 존재 |
| 2 | 산출물 | `plan-1.md` 스냅샷 존재 |
| 3 | 산출물 | `change-log-1.md` 존재 |
| 4 | 결함 주입 | `fault-injection.md` 존재 |
| 5 | 결함 주입 | 주입이 Developer 1차 이후에 이루어짐 |
| 6 | Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| 7 | Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| 8 | Tester 1차 | 주입된 실행 환경 오류 증상(`settlement_runtime.json`) 기록 |
| 9 | 라우팅 | 실패 원인 분류가 `ENVIRONMENT_ERROR` |
| 10 | 미호출 | Planner 2차가 호출되지 않음 (`plan.md` 해시가 `plan-1.md` 와 동일) |
| 11 | 미호출 | Developer 2차가 호출되지 않음 (`change-log-2.md` 없음) |
| 12 | 미호출 | Tester 2차가 호출되지 않음 (`test-result-2.md` 없음) |
| 13 | 미호출 | Reviewer가 호출되지 않음 (`review.md` 없음) |
| 14 | 상태 | `state.json` 존재 |
| 15 | 상태 | `retry_count == 0` (재시도 예산 미소비) |
| 16 | 상태 | `final_status == BLOCKED` |
| 17 | 상태 | `current_stage == DONE` |
| 18 | 상태 | `blocked_reason == ENVIRONMENT_ERROR` |
| 19 | 상태 | `attempts` 1건 |
| 20 | 상태 | `attempts[0]` 이 FAIL / `ENVIRONMENT_ERROR` |
| 21 | 상태 | `review.verdict` 없음 |
| 22 | 무결성 | 삭제된 런타임 리소스가 복구되지 않음 |
| 23 | 무결성 | eval 테스트가 약화되지 않음 |
| 24 | 범위 | 기존 추적 파일이 변경되지 않음 |
| 25 | 산출물 | `report.md` 존재 |
| 26 | 산출물 | `report.md` 에 BLOCKED 종료와 사유가 기록됨 |
| 27 | 복구 | eval fixture 제거 (teardown) |
| 28 | 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |

`plan-1.md` 는 `promote` 시 대표 결과에도 함께 복사된다. 이 시나리오의 승격 필수 목록에는
`change-log-2.md` / `test-result-2.md` / `review.md` 가 들어가지 않는다. 존재하지 않는 것이
정상이기 때문이다.

### 8-4. `harness-eval-004` 항목 (52항목 + teardown 3 = 55항목)

시도 1~3에 대해 같은 항목 묶음이 반복된다. 판정 항목 전체는 다음과 같다.

| # | 구분 | 항목 |
| --- | --- | --- |
| 1 | 산출물 | `plan.md` 존재 |
| 2 | 산출물 | `plan-1.md` 스냅샷 존재 |
| 3 | Developer 1차 | `change-log-1.md` 존재 |
| 4 | 결함 주입 1 | `fault-injection-1.md` 존재 |
| 5 | 결함 주입 1 | 1차 주입이 Developer 1차 이후에 이루어짐 |
| 6 | Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| 7 | Tester 1차 | 고정 실행 명령 기록 |
| 8 | Tester 1차 | 1차 결함의 실패 테스트(`..._distributes_remainder_...`) 기록 |
| 9 | 라우팅 1 | 실패 원인 분류가 `PRODUCT_CODE_DEFECT` |
| 10 | Developer 2차 | `change-log-2.md` 존재 |
| 11 | Developer 2차 | 1차 실패 결과를 근거로 사용 (참조 표현 + 관측값 인용) |
| 12 | Developer 2차 | 이전 시도와 다른 가설을 기록 |
| 13 | Developer 2차 | **1차 주입 결함을 제거함** (표식 부재 + 해시 변경) |
| 14 | 결함 주입 2 | `fault-injection-2.md` 존재 |
| 15 | 결함 주입 2 | 2차 주입이 Developer 2차 이후에 이루어짐 |
| 16 | Tester 2차 | 첫 줄이 `STATUS: FAIL` |
| 17 | Tester 2차 | 고정 실행 명령 기록 |
| 18 | Tester 2차 | 2차 결함의 실패 테스트(`..._difference_between_...`) 기록 |
| 19 | Tester 2차 | **실패 증상이 1차와 다름** (해당 테스트가 1차에는 없었음) |
| 20 | 라우팅 2 | 실패 원인 분류가 `PRODUCT_CODE_DEFECT` |
| 21 | Developer 3차 | `change-log-3.md` 존재 |
| 22 | Developer 3차 | 2차 실패 결과를 근거로 사용 (참조 표현 + 관측값 인용) |
| 23 | Developer 3차 | 이전 시도와 다른 가설을 기록 |
| 24 | Developer 3차 | **2차 주입 결함을 제거함** (표식 부재 + 해시 변경) |
| 25 | 결함 주입 3 | `fault-injection-3.md` 존재 |
| 26 | 결함 주입 3 | 3차 주입이 Developer 3차 이후에 이루어짐 |
| 27 | Tester 3차 | 첫 줄이 `STATUS: FAIL` |
| 28 | Tester 3차 | 고정 실행 명령 기록 |
| 29 | Tester 3차 | 3차 결함의 실패 테스트(`..._preserves_total_...`) 기록 |
| 30 | Tester 3차 | **실패 증상이 1·2차와 다름** |
| 31 | 라우팅 3 | 실패 원인 분류가 `PRODUCT_CODE_DEFECT` |
| 32 | 미호출 | Planner 2차가 호출되지 않음 (`plan.md` 해시가 `plan-1.md` 와 동일) |
| 33 | 미호출 | Developer 4차가 호출되지 않음 (`change-log-4.md` 없음) |
| 34 | 미호출 | Tester 4차가 호출되지 않음 (`test-result-4.md` 없음) |
| 35 | 미주입 | 4차 결함 주입이 이루어지지 않음 (`fault-injection-4.md` 없음 / 주입 기록 3건) |
| 36 | 미호출 | Reviewer가 호출되지 않음 (`review.md` 없음) |
| 37 | 상태 | `state.json` 존재 |
| 38 | 상태 | `retry_count == 3` |
| 39 | 상태 | `retry_budget == 3` |
| 40 | 상태 | `final_status == BLOCKED` |
| 41 | 상태 | `current_stage == DONE` |
| 42 | 상태 | `blocked_reason == RETRY_BUDGET_EXCEEDED` |
| 43 | 상태 | `attempts` 3건 |
| 44 | 상태 | `attempts[0]` 이 FAIL / `PRODUCT_CODE_DEFECT` |
| 45 | 상태 | `attempts[1]` 이 FAIL / `PRODUCT_CODE_DEFECT` |
| 46 | 상태 | `attempts[2]` 이 FAIL / `PRODUCT_CODE_DEFECT` |
| 47 | 상태 | `review.verdict` 없음 |
| 48 | 무결성 | **마지막 주입 결함이 제거되지 않고 남아 있음** |
| 49 | 무결성 | eval 테스트가 약화되지 않음 |
| 50 | 범위 | 기존 추적 파일이 변경되지 않음 |
| 51 | 산출물 | `report.md` 존재 |
| 52 | 산출물 | `report.md` 에 BLOCKED 종료와 `RETRY_BUDGET_EXCEEDED` 사유가 기록됨 |
| 53 | 복구 | eval fixture 제거 (teardown) |
| 54 | 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |
| 55 | 복구 | teardown 후 전체 테스트 결과가 setup 시점 기준선과 동일 |

13번과 24번이 이 시나리오의 핵심이다. 이 두 항목이 없으면 "Developer가 아무것도 고치지 못한
채 실패만 반복했다" 와 "매번 새 결함을 제거했지만 그때마다 다른 결함이 주입됐다" 를 구분할 수
없다. 두 항목의 근거는 `inject` 가 다음 결함을 주입하기 직전에 남긴 기록이다. (§3-13)

승격 필수 목록에는 시도 3회분 산출물이 모두 들어가고 `review.md` 는 들어가지 않는다.

---

### 8-5. `harness-eval-005` 항목 (28항목 + teardown 3 = 31항목)

`harness-eval-003` 과 같은 즉시 종료 골격이며, 다른 것은 세 가지다.
예산이 온전히 남았는지(15·16·17), 무엇이 남아 있어야 하는지(24), 실패 증상이 무엇인지(8).

| # | 구분 | 항목 |
| --- | --- | --- |
| 1 | 산출물 | `plan.md` 존재 |
| 2 | 산출물 | `plan-1.md` 스냅샷 존재 |
| 3 | 산출물 | `change-log-1.md` 존재 |
| 4 | 결함 주입 | `fault-injection.md` 존재 |
| 5 | 결함 주입 | 주입이 Developer 1차 이후에 이루어짐 |
| 6 | Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| 7 | Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| 8 | Tester 1차 | 주입된 결함의 실패 테스트(`..._gives_remainder_to_the_last_item`) 기록 |
| 9 | 라우팅 | 실패 원인 분류가 `TEST_DEFECT` |
| 10 | 미호출 | Planner 2차가 호출되지 않음 (`plan.md` 해시가 `plan-1.md` 와 동일) |
| 11 | 미호출 | Developer 2차가 호출되지 않음 (`change-log-2.md` 없음) |
| 12 | 미호출 | Tester 2차가 호출되지 않음 (`test-result-2.md` 없음) |
| 13 | 미호출 | Reviewer가 호출되지 않음 (`review.md` 없음) |
| 14 | 상태 | `state.json` 존재 |
| 15 | 상태 | `retry_count == 0` (재시도 예산 미소비) |
| 16 | 상태 | `retry_budget == 3` (예산이 있었는데도 쓰지 않았다) |
| 17 | 상태 | `unknown_retry_used == false` |
| 18 | 상태 | `final_status == BLOCKED` |
| 19 | 상태 | `current_stage == DONE` |
| 20 | 상태 | `blocked_reason == TEST_DEFECT_NEEDS_HUMAN` |
| 21 | 상태 | `attempts` 1건 |
| 22 | 상태 | `attempts[0]` 이 FAIL / `TEST_DEFECT` |
| 23 | 상태 | `review.verdict` 없음 |
| 24 | 무결성 | 주입된 모순 테스트가 그대로 남아 있고 기존 테스트가 변경되지 않음 |
| 25 | 무결성 | eval 테스트가 약화되지 않음 |
| 26 | 범위 | 기존 추적 파일이 변경되지 않음 |
| 27 | 산출물 | `report.md` 존재 |
| 28 | 산출물 | `report.md` 에 BLOCKED 종료와 사유가 기록됨 |
| 29 | 복구 | eval fixture 제거 (teardown) |
| 30 | 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |
| 31 | 복구 | teardown 후 전체 테스트 결과가 setup 시점 기준선(`57 passed`)과 동일 |

15·16·17 을 함께 두는 이유는, 예산 미소비가 "예산이 없어서 못 썼다" 와 구별되어야 하기
때문이다. 예산이 3으로 남아 있고 `UNKNOWN` 재시도도 쓰이지 않았을 때만 "예산 판정을 지나가지
않고 끝났다" 가 성립한다.

24는 표식 존재 여부가 아니라 설치 원본 fixture와의 완전 비교다. (§3-15)

### 8-6. `harness-eval-006` 항목 (54항목 + teardown 3 = 57항목)

시도 1~3에 대해 같은 항목 묶음이 반복된다. `harness-eval-004` 와 다른 곳만 굵게 적는다.

| # | 구분 | 항목 |
| --- | --- | --- |
| 1 | 산출물 | `plan.md` 존재 |
| 2 | 산출물 | `plan-1.md` 스냅샷 존재 |
| 3~9 | 시도 1 | `change-log-1.md` 존재 / `fault-injection-1.md` 존재 / 주입이 Developer 1차 이후 / **주입 결함이 `review_budget_001`** / **`test-result-1.md` 첫 줄이 `STATUS: PASS`** / 고정 실행 명령 기록 / **주입 결함이 테스트를 깨뜨리지 않음** |
| 10~20 | 시도 2 | 위 7항목 + **`change-log-2.md` 가 Reviewer 지적을 재수정 근거로 사용** / 이전 시도와 다른 가설 / Developer 2차가 1차 결함 제거 / **2차 주입 결함이 이전 시도와 다름** |
| 21~31 | 시도 3 | 시도 2와 동일 구성 |
| 32 | 예산 | **재시도 예산을 소비한 주체가 Reviewer 임** |
| 33 | Reviewer | **`review.md` 첫 줄이 `VERDICT: CHANGES_REQUESTED`** |
| 34 | 미호출 | Planner 2차가 호출되지 않음 |
| 35~37 | 미호출 | Developer 4차 / Tester 4차 / 4차 결함 주입 없음 |
| 38 | 상태 | `state.json` 존재 |
| 39~44 | 상태 | `retry_count == 3` / `retry_budget == 3` / **`unknown_retry_used == false`** / `final_status == BLOCKED` / `current_stage == DONE` / **`blocked_reason == REVIEW_CHANGES_REQUESTED_NO_BUDGET`** |
| 45 | 상태 | `attempts` 3건 |
| 46~48 | 상태 | **`attempts[0..2]` 이 각각 PASS / 실패 원인 분류 없음** |
| 49 | 상태 | **`review.verdict == CHANGES_REQUESTED`** |
| 50 | 무결성 | 마지막 주입 결함이 제거되지 않고 남아 있음 |
| 51 | 무결성 | eval 테스트가 약화되지 않음 |
| 52 | 범위 | 기존 추적 파일이 변경되지 않음 |
| 53~54 | 산출물 | `report.md` 존재 / `report.md` 에 BLOCKED 종료와 사유가 기록됨 |
| 55~57 | 복구 | teardown 3항목 (기준선 `57 passed` 복귀 포함) |

32번이 이 시나리오의 핵심 주장이다. 판정 근거는 연역이며, 그 연역이 성립하는 이유는 다음과 같다.

`CLAUDE.md §16` 이 정한 예산 소비 항목은 네 가지다. `PRODUCT_CODE_DEFECT`, `PLAN_DEFECT`,
`UNKNOWN`, 그리고 Reviewer의 `CHANGES_REQUESTED`. 앞의 셋은 **Tester가 `STATUS: FAIL` 을 내야만**
발생한다(`CLAUDE.md §14`). 시도 3회가 모두 `STATUS: PASS` 이고 `attempts` 세 건 모두
`failure_category` 가 비어 있으면 앞의 셋은 성립할 수 없다. `unknown_retry_used == false` 가
`UNKNOWN` 경로를 한 번 더 좁힌다. 남는 것은 Reviewer의 `CHANGES_REQUESTED` 뿐이고,
`retry_count == 3` 이므로 정확히 3회 발생했다.

`review.md` 는 회차마다 덮어써지므로 최종 판정 하나만 남는다. 1차와 2차 판정이 실재했다는
증거는 `fault-injection-2.md` / `fault-injection-3.md` 에 있다. 다음 결함을 주입하기 전에
Harness가 그 시점의 `review.md` 첫 줄과 직전 `test-result` 첫 줄을 읽어 기록하기 때문이다.
관측한 시점에 남기지 않으면 사라지는 증거라서 주입 기록에 함께 넣는다.

## 9. 실패했을 때

`reports/<run-id>/eval-result.md` 의 표에서 `FAIL` 인 행의 "근거" 열을 먼저 본다.

| 증상 | 확인할 곳 |
| --- | --- |
| `test-result-1.md` 가 `STATUS: PASS` | 결함 주입이 Developer 1차 이후에 실행됐는지 (`fault-injection.md` 시각) |
| 실패 원인 분류가 기대 분류와 다름 | `test-result-1.md` 의 pytest 원본 출력과 Tester 판단 근거 |
| `retry_count != 1` | Orchestrator가 `CLAUDE.md §20` 라우팅을 따랐는지 |
| 결함이 제거되지 않음 | `change-log-2.md` 의 수정 가설과 주입 대상 파일의 실제 내용 |
| `plan 1차와 2차의 내용이 실제로 다름` 이 FAIL | Planner 2차가 호출됐는지, `plan.md` 를 덮어썼는지 |
| `plan 1차 수정 허용 파일 목록이 계획대로 한정됨` 이 FAIL | Planner 1차가 범위를 넓게 잡았는지 (`plan-1.md` §7) |
| 복구 실패 | `git status --porcelain -- sample-project` 를 직접 확인 |
| `실패 원인 분류가 ENVIRONMENT_ERROR` 가 FAIL | Tester가 실행 환경 오류를 제품 코드 결함으로 봤는지 (`tester.md §3`) |
| `Developer 2차가 호출되지 않음` 이 FAIL | Orchestrator가 `ENVIRONMENT_ERROR` 를 재시도 경로로 라우팅했는지 (`patchpilot.md §5`) |
| `삭제된 런타임 리소스가 복구되지 않음` 이 FAIL | Agent가 실행 환경을 임의로 되살렸는지 |
| `Developer N차가 N-1차 주입 결함을 제거함` 이 FAIL | `change-log-N.md` 의 수정 내용과 대상 파일의 실제 상태 |
| `N차 실패 증상이 이전 시도와 다름` 이 FAIL | 같은 실패가 반복됐는지. 주입 순서가 어긋났을 가능성 (`fault-injection-N.md` 의 fault_id) |
| `Developer 4차가 호출되지 않음` 이 FAIL | Orchestrator가 예산 소진 후에도 재호출했는지 (`patchpilot.md §6` 의 증가/비교 순서) |
| `retry_count == 3` 이 FAIL | 실패 시 `retry_count` 를 올리기 전에 비교했는지 (off-by-one) |
| `마지막 주입 결함이 제거되지 않고 남아 있음` 이 FAIL | 예산 소진 이후 누가 제품 코드를 고쳤는지 |
| `복구 후 기존 테스트 결과가 setup 시점과 동일` 이 FAIL | Tester가 회귀 테스트를 추가했는지, 캐시가 남았는지 |

`inject` 가 `주입 전제 조건 위반` 으로 실패하는 경우는 두 가지다. 어느 쪽이든 결함을 주입하지
않고 중단하므로 제품 코드는 그대로 남는다.

* `ANCHOR` 를 찾지 못함 → Developer 1차가 대상 함수를 모듈 최상위에 유지하지 않았다.
* `precheck` 거부 → Planner 1차가 주입 대상을 이미 수정 허용 파일 목록에 넣었다.
  `harness-eval-002` 의 전제(계획 범위 밖 결함)가 성립하지 않는다는 뜻이다.
* `precheck_fs` 거부 또는 Harness 삭제 조건 위반 → 삭제 대상이 §3-10의 조건을 만족하지 않는다.
  파일을 지우지 않고 중단하므로 `sample-project/` 는 그대로 남는다.
* 직전 결함 미제거 → Developer가 이전 결함을 그대로 두었다. 연쇄 주입의 전제(§3-13)가 깨졌으므로
  다음 결함을 주입하지 않는다.
* 주입 순서 불일치 / `--attempt` 누락 → 연쇄 주입 시나리오에서 시도 번호를 지정하지 않았거나
  순서가 어긋났다. 어느 쪽이든 결함을 주입하지 않는다.

---

## 10. selftest — harness 자체의 회귀 확인

시나리오가 늘어나면 `eval_harness.py` 의 판정 코드가 공유된다. 이때 가장 큰 위험은
**이미 검증된 시나리오의 판정이 조용히 달라지는 것** 이다.

```bash
uv run python evals/eval_harness.py selftest
```

Agent를 실행하지 않고 수 초 안에 다음을 확인한다.

| 항목 | 근거 |
| --- | --- |
| `harness-eval-001` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_001_CHECK_NAMES` (25항목) |
| `harness-eval-002` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_002_CHECK_NAMES` (35항목) |
| `harness-eval-003` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_003_CHECK_NAMES` (26항목) |
| `harness-eval-004` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_004_CHECK_NAMES` (52항목) |
| `harness-eval-005` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_005_CHECK_NAMES` (28항목) |
| `harness-eval-006` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_006_CHECK_NAMES` (54항목) |
| 보존된 대표 결과 6건이 현재 판정 코드에서도 전부 PASS | `reports/examples/` 의 `EVAL-…-HARNESS-EVAL-001` ~ `-006` |
| 모든 시나리오의 task / fault / fixture 파일 존재 | `SCENARIOS` 정의 |
| 시나리오별 설치 경로가 서로 겹치지 않음 | `SCENARIOS` 정의 |
| `replan_checks` 시나리오의 결함이 `precheck` 를 갖고 계획 범위 밖을 대상으로 함 | 결함 정의 |
| 즉시 종료 시나리오의 삭제 대상이 설치 목록 안이고 `precheck_fs` 를 갖춤 | 결함 정의 |
| 테스트 결함 주입 대상이 설치 목록 안 `sample-project/tests/` 이고 `precheck_test` 를 갖춤 | 결함 정의 |
| 즉시 종료 시나리오의 기대 종료 상태가 라우팅 규칙과 일치 | `SCENARIOS` 정의 |
| 예산 소진 시나리오의 결함이 시도 수만큼 **서로 다르게** 정의됨 | `SCENARIOS` 정의 |
| 예산 소진 시나리오의 결함이 순서대로 직전 결함을 가리킴 (`PREVIOUS_FAULT_ID`) | 결함 정의 |
| 예산 소진 시나리오의 모든 결함이 계획 범위 **안** 전제를 `precheck` 로 검사 | 결함 정의 |
| 예산 소진 시나리오의 시도별 실패 증상이 서로 다르고 `SIGNATURE_TEST` 와 일치 | 결함 정의 |
| 예산 소진 시나리오의 기대 종료 상태가 예산 판정과 일치 (`retry_count == retry_budget`) | `SCENARIOS` 정의 |
| Reviewer 예산 소진 시나리오의 결함이 계획 범위 **안** 을 대상으로 함 | 결함 정의 |
| Reviewer 예산 소진 시나리오의 결함이 서로 다른 규칙(`VIOLATED_RULE`)을 어김 | 결함 정의 |
| Reviewer 예산 소진 시나리오가 Tester 실패를 기대하지 않음 | `SCENARIOS` 정의 |
| Reviewer 예산 소진 시나리오의 승격 필수 목록에 `review.md` 가 포함됨 | `SCENARIOS` 정의 |
| plan / change-log 파서가 목록 항목만 인식 | 보존된 대표 결과의 실제 산출물 |
| 실패 테스트 파서가 pytest 요약 줄만 인식 | 보존된 대표 결과의 실제 산출물 |
| 실패 테스트 파서가 설명 문장의 테스트 이름을 실패로 보지 않음 | 합성 입력 |
| 근거 참조 판정이 자연어 지칭과 관측값 인용을 인정 | 보존된 대표 결과 + 합성 입력 |
| 근거 참조 판정이 형식 문구만으로는 통과하지 않음 | 합성 입력 |
| 근거 참조 판정이 참조 없는 값 인용만으로는 통과하지 않음 | 합성 입력 |

결함 제거·잔존 여부, 테스트 약화 여부, git 상태는 실행 환경에 의존하므로 replay 대상이 아니다.
항목 이름과 순서만 유지하고 판정은 건너뛴다. 이 항목들은 라이브 실행으로만 검증된다.
제외 개수는 시나리오마다 다르다. (001 · 002 · 003 · 005 는 각 3항목, 004 · 006 은 결함 제거
확인이 2회 더 있어 5항목)

현재는 여섯 시나리오 모두 대표 결과가 보존되어 있고 `REGRESSION_EXAMPLES` 에 등록되어 replay
대상이다. (`harness-eval-001` 25항목 / `harness-eval-002` 35항목 / `harness-eval-003` 26항목 /
`harness-eval-004` 52항목 / `harness-eval-005` 28항목 / `harness-eval-006` 54항목,
`selftest` 전체 63항목)
대표 결과가 아직 없는 시나리오를 새로 추가하면
그 시나리오는 정의가 실제 파일 및 운영 라우팅 규칙과 맞물려 있는지만 확인하고, 대표 결과를 승격한
뒤 `REGRESSION_EXAMPLES` 에 골든 목록과 함께 추가한다.

승격된 대표 결과에 시나리오가 요구하는 산출물이 빠져 있으면 판정 replay는 성립하지 않는다.
이때는 조용히 넘어가지 않고 `판정 replay 범위` 항목에 무엇이 없어서 어디까지만 대조했는지를
남긴다. 현재 등록된 대표 결과 6건은 모두 필요한 산출물을 갖추고 있어 이 경로로 빠지지 않는다.
(과거 `harness-eval-002` 대표 결과에 `plan-1.md` / `plan-2.md` 가 빠져 있던 적이 있고,
그때 이 항목이 축소된 대조 범위를 드러냈다. 이후 승격을 다시 해 해소됐다.)

---

## 11. 새로운 결함 추가

`evals/faults/<fault_id>.py` 에 다음을 정의하면 `--fault <fault_id>` 로 선택할 수 있다.
결함 유형은 두 가지다. `FAULT_KIND` 를 생략하면 제품 코드 주입(`code_injection`)으로 본다.

### 11-1. `code_injection` — 제품 코드에 결함을 덧붙인다

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `FAULT_ID` | O | 결함 식별자 |
| `TARGET_PATH` | O | 주입 대상 파일 경로 (저장소 루트 기준) |
| `MARKER` | O | 주입/제거 여부를 문자열 비교로 판정하기 위한 표식 |
| `ANCHOR` | O | 주입 전제 조건이 되는 문자열 |
| `DESCRIPTION` | O | 결함 내용 한 줄 설명 |
| `FAULT_CODE` | O | 주입되는 코드 |
| `is_applied(source)` | O | 이미 주입되어 있는지 판정 |
| `apply(source)` | O | 주입된 새 내용을 반환. 전제 조건 위반 시 `ValueError` |
| `precheck(plan_allowed_files)` | | 있으면 주입 전에 호출된다. `plan.md` 의 수정 허용 파일 목록을 받아 계획 범위에 대한 전제를 검사하고, 위반 시 `ValueError` 를 낸다 |
| `PREVIOUS_FAULT_ID` | | 연쇄 주입에서 이 결함보다 먼저 주입된 결함. 주입 전에 그 결함이 제거됐는지 확인하는 데 쓴다 (§3-13) |
| `SIGNATURE_TEST` | | 이 결함으로 **새로** 실패하게 되는 테스트 이름. 시나리오의 `expected_failing_tokens` 와 대조된다 |
| `VIOLATED_RULE` | | 이 결함이 어기는 규칙 한 줄. 테스트를 깨뜨리지 않고 품질 기준만 어기는 결함(§3-17)에 쓰며, `fault-injection-N.md` 의 주입 방식 절에 인용된다 |

`retry_001` 처럼 `precheck` 가 없으면 호출되지 않으므로 기존 결함 정의는 그대로 동작한다.

### 11-2. `resource_removal` — 설치된 런타임 리소스를 삭제한다

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `FAULT_KIND` | O | `"resource_removal"` |
| `FAULT_ID` | O | 결함 식별자 |
| `TARGET_PATH` | O | 삭제 대상 경로. `sample-project/` 안이어야 하고 `installs` 에 있어야 한다 |
| `MARKER` | O | 삭제 대상이 이번 eval의 fixture 사본인지 내용으로 확인하기 위한 표식 |
| `DESCRIPTION` | O | 결함 내용 한 줄 설명 |
| `SYMPTOM` | | 주입 이후 Tester가 보게 되는 증상. `fault-injection.md` 에 기록된다 |
| `precheck_fs(context)` | O | 삭제 전제 조건 검사. 위반 시 `ValueError` |
| `is_applied(context)` | | 이미 삭제되었는지 판정 |

`context` 는 `target` / `installed` / `tracked` / `exists` / `content` 를 담은 dict다.
실제 삭제는 `eval_harness.py` 가 §3-10의 조건을 함께 확인한 뒤 수행한다.
결함 정의는 무엇을 지울지와 지워도 되는 조건만 선언한다.

### 11-3. `test_injection` — 설치된 테스트 fixture에 테스트를 덧붙인다

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `FAULT_KIND` | O | `"test_injection"` |
| `FAULT_ID` | O | 결함 식별자 |
| `TARGET_PATH` | O | 주입 대상 경로. `sample-project/tests/` 안이어야 하고 `installs` 에 있어야 한다 |
| `MARKER` | O | 주입 여부를 문자열 비교로 판정하기 위한 표식 |
| `ANCHOR` | O | 주입 전제 조건이 되는 문자열. 모순의 상대편이 되는 기존 테스트 |
| `DESCRIPTION` | O | 결함 내용 한 줄 설명 |
| `FAULT_CODE` | O | 덧붙일 테스트 코드. 기존 테스트를 고치는 코드를 넣지 않는다 |
| `SYMPTOM` | | 주입 이후 Tester가 보게 되는 증상 |
| `SIGNATURE_TEST` | | 이 결함으로 새로 실패하게 되는 테스트 이름 |
| `precheck_test(context)` | O | 주입 전제 조건 검사. 위반 시 `ValueError` |
| `is_applied(source)` | O | 이미 주입되어 있는지 판정 |
| `apply(source)` | O | 주입된 새 내용을 반환. 전제 조건 위반 시 `ValueError` |

`context` 는 `resource_removal` 의 다섯 키에 `fixture_content`(설치 원본 fixture 내용)를
더한 dict다. 주입 직전 파일이 설치 시점과 완전히 같은지 확인하는 데 쓴다. (§3-15)

`apply` 는 **덧붙이기만** 해야 한다. 기존 테스트를 수정·삭제·skip 처리하는 결함 정의는
`CLAUDE.md §3-3` 위반이며, 주입 후 완전 비교 판정에서 FAIL 로 잡힌다.

---

## 12. 새로운 시나리오 추가

`eval_harness.py` 의 `SCENARIOS` 에 `Scenario` 항목 하나를 추가한다. 절차 코드는 고치지 않는다.

| 필드 | 설명 |
| --- | --- |
| `scenario_id` | `--scenario` 로 지정하는 식별자 |
| `task` | eval 전용 고정 Task 경로 |
| `fault` | 기본 주입 결함 (연쇄 주입에서는 1차 결함) |
| `fault_sequence` | 시도 순서대로 주입할 결함 목록 (선택). 비우면 `fault` 하나만 1회 주입한다 |
| `expected_failing_tokens` | 시도마다 새로 실패해야 하는 테스트 이름 (선택) |
| `expected_retry_budget` | 예산 소진 시나리오에서 기대하는 `retry_budget` (선택, 기본값 3) |
| `installs` | (fixture 파일명, 설치 경로) 목록 |
| `expected_category` | Tester 1차가 기록해야 하는 실패 원인 분류 |
| `expected_failing_token` | `test-result-1.md` 에 남아야 하는 실패 테스트 식별 문자열 |
| `transition` | `eval-result.md` 에 기록할 검증 대상 전이 |
| `outcome` | 종료 형태 (선택, 기본값 `SUCCESS_AFTER_RETRY`). 즉시 종료는 `BLOCKED`, Tester 실패로 예산이 마르면 `BLOCKED_AFTER_RETRIES`, Reviewer 지적으로 마르면 `BLOCKED_AFTER_REVIEW` |
| `expected_retry_count` | `state.json` 의 기대 `retry_count` (선택, 기본값 1) |
| `expected_attempts` | `state.json` 의 기대 `attempts` 개수 (선택, 기본값 2) |
| `expected_blocked_reason` | 즉시 종료 시 기대 `blocked_reason` (선택) |
| `forbidden_artifacts` | 즉시 종료 시 존재하면 안 되는 (산출물, 주체) 목록 (선택) |
| `verify_budget_untouched` | 예산이 있었는데도 쓰이지 않았다는 사실을 판정할지 (선택). `retry_budget` 과 `unknown_retry_used` 항목이 추가된다 |
| `failing_token_check_name` | 실패 증상 기록 항목의 이름 (선택) |
| `expected_plan1_allowed` | Planner 1차가 확정해야 하는 수정 허용 파일 목록 (선택) |
| `snapshot_plan` | inject 시점에 `plan-1.md` 스냅샷을 남길지 (선택) |
| `replan_checks` | Planner 재호출(재계획) 전이를 검증할지 (선택, `snapshot_plan` 전제) |
| `promoted_files` | 승격 시 필수인 산출물 (선택, 비우면 기본 목록) |
| `extra_promoted_files` | 승격 시 함께 복사할 추가 산출물 (선택) |

추가한 뒤에는 반드시 `selftest` 로 기존 시나리오의 회귀를 확인한다.

---

## 13. Stop Gate 검증

`Stop` Hook(`.claude/hooks/guard_stop_gate.py`)은 결함 주입 전이가 아니므로
`eval_harness.py` 의 `SCENARIOS` 에 넣지 않는다. `harness-eval-00N` 번호를 부여하지 않는다.
검증은 오프라인 단위 테스트와 수동 라이브 확인 두 층으로 나눈다.

### 13-1. 오프라인 — `evals/tests/test_guard_stop_gate.py`

다른 가드와 같은 방식이다. `decide()` 를 직접 호출해 판정만 확인한다.

```bash
uv run pytest evals/tests -q
```

검증 대상은 G1~G21 각각의 정상/위반 경계, fail-open 조건, reason 계약,
`main()` 의 stdout JSON + exit 0 전달 계약이다.

`G20~G21` 은 `UNKNOWN_TWICE` 종료 선언이 그 경로를 실제로 지나온 상태인지 대조한다.
`unknown_retry_used` 가 참인지(G20), `attempts` 에 `UNKNOWN` 실패가 2건 이상이고 마지막
시도가 `FAIL` / `UNKNOWN` 인지(G21)를 본다. `patchpilot.md §5` 의 UNKNOWN 분기는 시도
번호를 보지 않으므로 `attempts` 길이나 `retry_count` 를 특정 숫자로 못박지 않는다.
1차 `PRODUCT_CODE_DEFECT` -> 2차 `UNKNOWN` -> 3차 `UNKNOWN` 도 정상 경로이기 때문이다.
`test-result-N.md` 에서 실패 원인 분류를 다시 파싱하지도 않는다. (`CLAUDE.md §25`)

이 경로는 아직 **Live Eval 로 검증되지 않았다.** `UNKNOWN` 은 저장소 상태가 아니라 Tester 의
확신 부재를 가리키는 fallback 분류라서(`tester.md §3`), 특정 verdict 를 강제하는 결정론적
fixture 를 만들 수 없다. G20~G21 이 보강한 것은 유발 가능성이 아니라 **관측성** 이다.

`UNKNOWN_TWICE` 는 세 층을 구분해서 읽는다. 셋을 뭉뚱그리면 "구현했다"와 "검증했다"가 섞인다.

| 층 | 상태 |
| --- | --- |
| 라우팅 계약 (`CLAUDE.md §16` · `§20`, `patchpilot.md §5`) | 구현됨 |
| Stop Gate 관측성 (`G20` · `G21` + `evals/tests/test_guard_stop_gate.py`) | 구현됨 |
| 결정론적 Live Eval | **미검증** — 현재 계약에서 불가능 |

Tester 에게 `UNKNOWN` 판정을 지시하면 실행은 만들 수 있지만, 그 순간 검증 대상이던 Agent 의
분류 능력이 검증에서 빠진다. 강제된 verdict 로 만든 실행을 "경로를 검증했다"고 기록하지 않기 위해
`SCENARIOS` 에 `harness-eval-007` 을 만들지 않고 미검증 상태를 유지한다.
그 결과 `harness_audit.py` 의 `E4b` 는 FAIL(-2점)로 남고, 검증된 종료 경로는 **7개 중 6개** 다.
이 감점은 결함이 아니라 의도된 기록이다.

상태를 바꾸려면 `CLAUDE.md §14` 의 `UNKNOWN` 정의를 저장소 상태로 판정 가능한 조건으로 좁혀야
하고, 그것은 분류 계약 변경이므로 이 문서가 아니라 rubric 버전과 함께 다룬다.

다음 항목은 **필수 회귀 계약**이다. 지우면 무한 루프가 열린다.

```text
stop_hook_active == true  ->  ALLOW
```

### 13-2. 라이브 — 수동 확인 절차

임시 run 을 만들어 실제 Claude Code 경로에서 확인한다.
`reports/examples/` 의 보존된 대표 결과는 **절대 사용하지 않는다.**

임시 run 은 `reports/RUN-LIVECHECK-*` 형태로 만들고, `state.json` 의 `session_id` 를
검사에 쓸 세션 UUID 로 채운다. 세션은 `claude -p --session-id <uuid>` 로 고정한다.

| 확인 | 준비 | 기대 |
| --- | --- | --- |
| A | 정합한 SUCCESS run | Stop ALLOW (차단 없음) |
| B | 정합한 BLOCKED run | Stop ALLOW |
| C | SUCCESS 인데 `review.md` 없음 | Stop BLOCK, reason 에 `[G9]` |
| D | C 와 동일 | `Stop hook feedback:` 으로 reason 이 assistant 에게 전달됨 |
| E | C 와 동일 | Stop 훅이 **다시 호출**되고 두 번째 payload 의 `stop_hook_active == true`, Gate 가 ALLOW |
| F | 같은 세션에서 다음 user prompt | 같은 모순에 다시 1회 차단 (prompt 마다 예산이 리셋됨) |

E 를 확인하려면 payload 를 기록하는 관찰용 훅을 `--settings` 로 함께 등록한다.
관찰용 훅과 임시 run 은 확인이 끝나면 전부 삭제한다.

확인 후 `reports/RUN-LIVECHECK-*` 를 삭제하고 `git status --short` 로 저장소가
깨끗한지 확인한다. (`reports/*` 는 `.gitignore` 대상이지만 남겨 두지 않는다.)

---

## 14. 실행 절차 — `harness-eval-005` (TEST_DEFECT)

§4와 다른 부분만 적는다. 나머지는 동일하다.

### 14-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-005
```

결함이 있는 제품 모듈 `coupon.py` 와 그 계약 테스트 `test_coupon.py` 두 개를 설치한다.
이 시점에는 테스트에 모순이 없고 제품 버그 때문에 5건이 실패한다.

### 14-2. Planner

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-005.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-005` 가 된다.

### 14-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.
이 단계가 끝나면 제품 버그가 해결되어 전체 테스트가 통과하는 상태가 된다.

### 14-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

이때 두 가지가 함께 일어난다.

1. `reports/<run-id>/plan-1.md` 에 Planner 1차 산출물이 복사된다.
2. §3-15의 조건을 모두 통과한 경우에만 `test_coupon.py` 끝에 모순 테스트 하나가 덧붙는다.

주입 직후 실패는 정확히 1건이다. 기존 테스트는 전부 통과한 채로 주입된 테스트만 실패한다.

### 14-5. Tester 1차

`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `TEST_DEFECT` 가 되어야 한다.

Tester에게 결함 주입 사실이나 기대 분류를 알리지 않는다. (§3-16)

### 14-6. FAIL 라우팅 — 여기서 끝난다

`TEST_DEFECT` 는 자동 수정 대상이 아니므로 **`retry_count` 를 증가시키지 않고** 즉시
`BLOCKED` 로 종료한다. (`CLAUDE.md §20`, `patchpilot.md §5`)

Developer도 Planner도 Reviewer도 다시 호출하지 않는다. Orchestrator는 `report.md` 와
`state.json` 만 마감한다. `blocked_reason` 은 `TEST_DEFECT_NEEDS_HUMAN` 이다.

`report.md` 에는 사람이 무엇을 판단해야 하는지(어느 배분 방향이 옳은 명세인지) 기록한다.

### 14-7. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

주입된 테스트는 복구하지 않는다. teardown이 테스트 fixture와 함께 통째로 제거한다.

---

---

## 15. 실행 절차 — `harness-eval-006` (REVIEW_CHANGES_REQUESTED_NO_BUDGET)

§4·§7과 다른 부분만 적는다. 나머지는 동일하다.

### 15-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-006
```

결함이 있는 제품 모듈 `refund.py` 와 그 반환값 계약 테스트 `test_refund.py` 두 개를 설치한다.
이 시점에는 제품 버그 때문에 4건이 실패한다.

### 15-2. Planner

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-006.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-006` 이 된다.

Planner가 확정한 수정 허용 파일 목록에 `sample-project/src/expense/refund.py` 가 **포함되어야**
한다. 빠져 있으면 결함의 `precheck` 가 주입을 거부하고 eval이 중단된다. Planner 산출물을
목록에 맞춰 고치지 않는다. (§3-17)

### 15-3. 시도 1 ~ 3 반복

각 시도 `N` 에서 다음 순서를 지킨다.

1. `developer` 를 시도 번호 `N` 으로 호출한다. 산출물은 `change-log-N.md` 다.
   * `N >= 2` 이면 프롬프트에 `review.md` 경로와 "Reviewer 지적사항 반영" 이라는 재수정 사유를
     포함한다. (`patchpilot.md §7-2`)
2. 결함을 주입한다.

   ```bash
   uv run python evals/eval_harness.py inject --run-id <run-id> --attempt N
   ```

   * `N >= 2` 이면 주입 전에 네 가지를 확인한다. 하나라도 어긋나면 주입하지 않고 실패시킨다.
     직전 결함이 실제로 제거됐는지(§3-13), 직전 `test-result-{N-1}.md` 첫 줄이 `STATUS: PASS`
     인지, 현재 `review.md` 첫 줄이 `VERDICT: CHANGES_REQUESTED` 인지, `change-log-N.md` 가
     Reviewer 지적을 재수정 근거로 적고 있는지.
   * 이 확인 결과는 `fault-injection-N.md` 에 기록된다. `review.md` 는 회차마다 덮어써지므로
     **그 시점에 남기지 않으면 사라지는 증거**다.
3. `tester` 를 호출한다. 결과는 `STATUS: PASS` 여야 한다. 주입된 결함은 반환값과 예외 동작을
   바꾸지 않으므로 전체 테스트가 통과하는 것이 정상이다.
4. `reviewer` 를 호출한다. 프롬프트는 `patchpilot.md §7` 구성 그대로이며 eval 전용 항목을
   넣지 않는다. (§3-18)
5. `review.md` 첫 줄이 `VERDICT: CHANGES_REQUESTED` 이면 `retry_count += 1` 후 §6 예산 판정을
   적용한다. (`patchpilot.md §7-2`)

### 15-4. 예산 소진 — 여기서 끝난다

Reviewer 3차의 `CHANGES_REQUESTED` 로 `retry_count` 가 3이 되어 `retry_budget` 에 도달한다.
Developer 4차와 Tester 4차를 **호출하지 않고** 종료한다.

`blocked_reason` 은 `REVIEW_CHANGES_REQUESTED_NO_BUDGET` 이다. `RETRY_BUDGET_EXCEEDED` 가
아니다. `patchpilot.md §6` 이 이 경우만 사유 코드를 따로 정하고 있다.

마지막으로 주입된 `review_budget_003` 은 제품 코드에 **남은 채로** 종료된다. (§3-14)

### 15-5. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`review.md` 는 승격 필수 목록에 포함된다. 종료 사유의 근거가 그 파일이기 때문이며,
`guard_stop_gate.py` 의 G16도 같은 것을 요구한다.
