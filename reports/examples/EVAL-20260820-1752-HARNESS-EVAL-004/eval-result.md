EVAL: PASS

# Eval Result

## Run ID
RUN-20260820-1752-HARNESS-EVAL-004

## 시나리오
harness-eval-004

## 판정 시각
2026-08-20T18:08:02

## 검증 대상 전이
Planner -> Developer 1차 -> Fault Injection(결함 B) -> Tester FAIL
-> PRODUCT_CODE_DEFECT -> retry_count = 1 -> Developer 2차(B 제거)
-> Fault Injection(결함 C) -> Tester FAIL -> PRODUCT_CODE_DEFECT -> retry_count = 2
-> Developer 3차(C 제거) -> Fault Injection(결함 D) -> Tester FAIL
-> PRODUCT_CODE_DEFECT -> retry_count = 3 = retry_budget
-> Developer 4차 / Tester 4차 / Reviewer 미호출 -> BLOCKED

## 자동 검증 항목
| # | 항목 | 결과 | 근거 |
| --- | --- | --- | --- |
| 1 | plan.md 존재 | PASS | Planner 실행됨 |
| 2 | plan-1.md 스냅샷 존재 | PASS | Planner 1차 산출물 보존됨 |
| 3 | change-log-1.md 존재 | PASS | Developer 1차 실행됨 |
| 4 | fault-injection-1.md 존재 | PASS | fault_id=retry_budget_001 |
| 5 | 1차 결함 주입이 Developer 1차 이후에 이루어짐 | PASS | change-log-1.md 와 fault-injection-1.md 이(가) 모두 존재 |
| 6 | test-result-1.md 첫 줄이 STATUS: FAIL | PASS | 첫 줄: 'STATUS: FAIL' |
| 7 | test-result-1.md 에 고정 실행 명령 기록 | PASS | `uv run pytest sample-project/tests -q` 기록됨 |
| 8 | test-result-1.md 가 1차 주입 결함의 실패 테스트를 기록 | PASS | pytest 실패 1건에 test_split_installments_distributes_remainder_to_earlier_months_first 포함 |
| 9 | 1차 실패 원인 분류가 PRODUCT_CODE_DEFECT | PASS | 분류: 'PRODUCT_CODE_DEFECT' |
| 10 | change-log-2.md 존재 | PASS | Developer 2차 실행됨 |
| 11 | change-log-2.md 가 1차 실패 결과를 근거로 사용 | PASS | 참조 표현='test-result-1' / 인용된 이전 관측=['1 failed, 67 passed', '[3333, 3333, 3334]', '[3334, 3333, 3333]'] |
| 12 | change-log-2.md 가 이전 시도와 다른 가설을 기록 | PASS | 가설 변경=True / 이전 시도와의 차이 기록=True |
| 13 | Developer 2차가 1차 주입 결함을 제거함 | PASS | retry_budget_001 표식 제거=True / 직전 주입 해시 일치=True / 파일 내용 변경=True |
| 14 | fault-injection-2.md 존재 | PASS | fault_id=retry_budget_002 |
| 15 | 2차 결함 주입이 Developer 2차 이후에 이루어짐 | PASS | change-log-2.md 와 fault-injection-2.md 이(가) 모두 존재 |
| 16 | test-result-2.md 첫 줄이 STATUS: FAIL | PASS | 첫 줄: 'STATUS: FAIL' |
| 17 | test-result-2.md 에 고정 실행 명령 기록 | PASS | `uv run pytest sample-project/tests -q` 기록됨 |
| 18 | test-result-2.md 가 2차 주입 결함의 실패 테스트를 기록 | PASS | pytest 실패 3건에 test_split_installments_difference_between_installments_is_at_most_one_won 포함 |
| 19 | 2차 실패 증상이 이전 시도와 다름 | PASS | test_split_installments_difference_between_installments_is_at_most_one_won 은(는) 2차 pytest 실패 목록에서 처음 등장 |
| 20 | 2차 실패 원인 분류가 PRODUCT_CODE_DEFECT | PASS | 분류: 'PRODUCT_CODE_DEFECT' |
| 21 | change-log-3.md 존재 | PASS | Developer 3차 실행됨 |
| 22 | change-log-3.md 가 2차 실패 결과를 근거로 사용 | PASS | 참조 표현='test-result-2' / 인용된 이전 관측=['1 failed, 67 passed', '3 failed, 65 passed', '[3000, 3000, 3000]'] |
| 23 | change-log-3.md 가 이전 시도와 다른 가설을 기록 | PASS | 가설 변경=True / 이전 시도와의 차이 기록=True |
| 24 | Developer 3차가 2차 주입 결함을 제거함 | PASS | retry_budget_002 표식 제거=True / 직전 주입 해시 일치=True / 파일 내용 변경=True |
| 25 | fault-injection-3.md 존재 | PASS | fault_id=retry_budget_003 |
| 26 | 3차 결함 주입이 Developer 3차 이후에 이루어짐 | PASS | change-log-3.md 와 fault-injection-3.md 이(가) 모두 존재 |
| 27 | test-result-3.md 첫 줄이 STATUS: FAIL | PASS | 첫 줄: 'STATUS: FAIL' |
| 28 | test-result-3.md 에 고정 실행 명령 기록 | PASS | `uv run pytest sample-project/tests -q` 기록됨 |
| 29 | test-result-3.md 가 3차 주입 결함의 실패 테스트를 기록 | PASS | pytest 실패 6건에 test_split_installments_preserves_total_when_total_is_not_evenly_divisible 포함 |
| 30 | 3차 실패 증상이 이전 시도와 다름 | PASS | test_split_installments_preserves_total_when_total_is_not_evenly_divisible 은(는) 3차 pytest 실패 목록에서 처음 등장 |
| 31 | 3차 실패 원인 분류가 PRODUCT_CODE_DEFECT | PASS | 분류: 'PRODUCT_CODE_DEFECT' |
| 32 | Planner 2차가 호출되지 않음 | PASS | plan.md 가 1차 주입 시점 스냅샷과 동일 |
| 33 | Developer 4차가 호출되지 않음 | PASS | change-log-4.md 없음 / 주입 기록 3건 |
| 34 | Tester 4차가 호출되지 않음 | PASS | test-result-4.md 없음 / 주입 기록 3건 |
| 35 | 4차 결함 주입이 이루어지지 않음 | PASS | fault-injection-4.md 없음 / 주입 기록 3건 |
| 36 | Reviewer가 호출되지 않음 | PASS | review.md 없음 / 주입 기록 3건 |
| 37 | state.json 존재 | PASS | state.json 파싱 성공 |
| 38 | state.json retry_count == 3 | PASS | retry_count=3 |
| 39 | state.json retry_budget == 3 | PASS | retry_budget=3 |
| 40 | state.json final_status == BLOCKED | PASS | final_status='BLOCKED' |
| 41 | state.json current_stage == DONE | PASS | current_stage='DONE' |
| 42 | state.json blocked_reason == RETRY_BUDGET_EXCEEDED | PASS | blocked_reason='RETRY_BUDGET_EXCEEDED' |
| 43 | state.json attempts 가 3회 기록 | PASS | 시도 3회 기록됨 |
| 44 | attempts[0] 이 FAIL / PRODUCT_CODE_DEFECT | PASS | status='FAIL', failure_category='PRODUCT_CODE_DEFECT' |
| 45 | attempts[1] 이 FAIL / PRODUCT_CODE_DEFECT | PASS | status='FAIL', failure_category='PRODUCT_CODE_DEFECT' |
| 46 | attempts[2] 이 FAIL / PRODUCT_CODE_DEFECT | PASS | status='FAIL', failure_category='PRODUCT_CODE_DEFECT' |
| 47 | state.json review.verdict 없음 | PASS | review={'verdict': None, 'file': None} |
| 48 | 마지막 주입 결함이 제거되지 않고 남아 있음 | PASS | retry_budget_003 표식 유지=True / 주입 직후와 동일=True |
| 49 | eval 테스트가 약화되지 않음 | PASS | 원래 테스트 함수가 모두 유지되고 skip 처리가 없음 |
| 50 | 기존 추적 파일이 변경되지 않음 | PASS | 새로 생긴 변경은 eval fixture(untracked)뿐 |
| 51 | report.md 존재 | PASS | 최종 보고서 존재 |
| 52 | report.md 에 BLOCKED 종료와 사유가 기록됨 | PASS | BLOCKED 기록=True / RETRY_BUDGET_EXCEEDED 기록=True |
| 53 | eval fixture 제거 | PASS | 제거=['sample-project/src/expense/installment.py', 'sample-project/tests/test_installment.py'] |
| 54 | sample-project 원상 복구 | PASS | setup 시점 상태와 동일 |
| 55 | 복구 후 기존 테스트 결과가 setup 시점과 동일 | PASS | setup 시점='57 passed' / 현재='57 passed' |

## 종합
55/55 항목 통과
