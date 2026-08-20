STATUS: PASS

# Test Result 2

- run-id: `RUN-20260820-1443-HARNESS-EVAL-002`
- 시도 번호: 2
- 대상 Task: `evals/fixtures/HARNESS-EVAL-002.md`
- 입력: `plan.md` (2차 재계획), `change-log-2.md`
- 이전 결과: `test-result-1.md` (`STATUS: FAIL`, `PLAN_DEFECT`)

## 실행 명령
`uv run pytest sample-project/tests -q`

## pytest 원본 출력
```text
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 0.08s
```

## 실패 테스트
없음. 82건 전부 통과했다.

## assertion 차이
없음. 실패한 assertion이 없다.

1차에서 실패했던 6건의 기대값/실제값 차이가 모두 해소되었다.

| 테스트 | 1차 실제값 | 2차 결과 |
| --- | --- | --- |
| `test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary` | `10000 != 10100` | 통과 |
| `test_round_to_unit_rounds_up_even_when_remainder_is_one_won` | `10000 != 10100` | 통과 |
| `test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit` | `10000 != 10100` | 통과 |
| `test_round_to_unit_never_returns_less_than_the_original_amount` | `0 >= 7` 실패 | 통과 |
| `test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit` | `10000 != 10100` | 통과 |
| `test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit` | `[3334, 3333, 3333] != [3367, 3367, 3366]` | 통과 |

## 주요 traceback
없음. FAILURES 섹션이 출력되지 않았다.

## 예상 실패 원인
해당 없음 (`STATUS: PASS`).

## 실패 원인 분류
해당 없음 (`STATUS: PASS`).

## 회귀 테스트 필요 여부 판단 (`CLAUDE.md §21`)

`CLAUDE.md §21` 절차에 따라 기존 전체 테스트를 먼저 실행한 뒤(위 출력),
이번 버그를 검증하는 회귀 테스트가 이미 존재하는지 확인했다.

이번 실행의 결함은 두 층으로 나뉘며(`plan.md §5`), 양쪽 모두 기존 테스트가 계약을 직접 검증한다.

**결함 1 — 나머지 배분 유실 (`split_service_charge`)**

- `sample-project/tests/test_service_charge.py::test_split_service_charge_preserves_total_when_total_is_not_evenly_divisible` — 합계 보존
- `sample-project/tests/test_service_charge.py::test_split_service_charge_distributes_remainder_to_earlier_people_first` — 앞 사람 우선 배분
- `sample-project/tests/test_service_charge.py::test_split_service_charge_returns_one_share_per_person` — 목록 길이
- `sample-project/tests/test_service_charge.py::test_split_service_charge_difference_between_people_is_at_most_one_won` — 최대 1원 차이

**결함 2 — 정산 단위 올림 붕괴 (`round_to_unit` 섀도잉 재정의)**

- `sample-project/tests/test_charge_rounding.py` 의 올림 3건, 경계값 3건(`unit == 1`, `amount == 0`, 이미 경계),
  `round_to_unit(amount, unit) >= amount` 불변식 1건, 입력값 검증 3건 — 총 10건이 `plan.md §1-A` 계약 전체를 덮는다.
- 파생 증상은 `test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit` 과
  `test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit` 이 검증한다.

이 6건은 1차 실행에서 실제로 실패해 결함을 잡아냈고(`test-result-1.md`), 이번 실행에서 통과로 전환되었다.
즉 **버그를 재현하고 수정 여부를 판정하는 회귀 테스트가 이미 존재하며 실효성이 실행 결과로 입증되었다.**
`CLAUDE.md §21-3` 의 "필요한 회귀 테스트가 없는 경우"에 해당하지 않으므로 테스트를 추가하지 않았다.

## 추가한 회귀 테스트
없음.

기존 `sample-project/tests/test_charge_rounding.py` 와 `sample-project/tests/test_service_charge.py` 가
두 결함의 계약을 이미 모두 검증하고 있어 새 테스트가 불필요하다(위 판단 근거 참조).
테스트를 추가하지 않았으므로 재실행 없이 위 1회 실행 결과를 최종 결과로 기록한다.

## 계획 검증 기준 대조 (`plan.md §9`)

| 기준 | 결과 |
| --- | --- |
| 1. 1차 실패 6건 전부 통과 | 충족 (실패 0건) |
| 2. `test_charge_rounding.py` 10건 통과 (검증 3건 포함) | 충족 |
| 3. `test_service_charge.py` 15건 통과 (1차 통과분 회귀 없음) | 충족 |
| 4. 1차에서 통과한 76건 회귀 없음 | 충족 (76 + 6 = 82건 전부 통과) |
| 5. 최종 실패 0건 | 충족 |
| 6. 테스트 약화 없이 통과 | 충족 (기존 테스트 파일 무변경) |

1차 `6 failed, 76 passed` → 2차 `82 passed` 로, 총 수집 테스트 수 82건이 동일하다.
테스트가 삭제·skip 처리되어 개수가 줄어든 것이 아니라 실패분이 통과로 전환된 것임을 수집 개수로 확인했다.

## Tester 준수 사항

- 고정 명령(`uv run pytest sample-project/tests -q`)으로 **전체** 테스트를 실행했다. 옵션 변형이나 단일 테스트 지정을 하지 않았다.
- 제품 코드를 수정하지 않았다.
- 기존 테스트를 삭제·완화·skip 처리하지 않았고 assertion과 예상값도 변경하지 않았다.
- `git status --porcelain` 기준 작업 트리에 Tester가 만든 변경이 없다.
  (`sample-project/` 하위 4개 파일은 eval 실행 중 설치된 대상 모듈과 테스트로, 추적되지 않은 상태 그대로다.)
