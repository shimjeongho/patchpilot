EVAL: PASS

# Eval Result

## Run ID
RUN-20260827-1136-HARNESS-EVAL-005

## 시나리오
harness-eval-005

## 판정 시각
2026-08-27T11:43:19

## 검증 대상 전이
Planner -> Developer 1차 -> Fault Injection(모순 테스트 추가) -> Tester FAIL
-> TEST_DEFECT -> 재시도 예산 미소비(retry_count = 0) -> 테스트 자동 수정 없음
-> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출
-> BLOCKED (TEST_DEFECT_NEEDS_HUMAN)

## 자동 검증 항목
| # | 항목 | 결과 | 근거 |
| --- | --- | --- | --- |
| 1 | plan.md 존재 | PASS | Planner 실행됨 |
| 2 | plan-1.md 스냅샷 존재 | PASS | Planner 1차 산출물 보존됨 |
| 3 | change-log-1.md 존재 | PASS | Developer 1차 실행됨 |
| 4 | fault-injection.md 존재 | PASS | fault_id=test_defect_001 |
| 5 | 결함 주입이 Developer 1차 이후에 이루어짐 | PASS | change-log-1.md 와 결함 주입 기록이 모두 존재 |
| 6 | test-result-1.md 첫 줄이 STATUS: FAIL | PASS | 첫 줄: 'STATUS: FAIL' |
| 7 | test-result-1.md 에 고정 실행 명령 기록 | PASS | `uv run pytest sample-project/tests -q` 기록됨 |
| 8 | test-result-1.md 가 주입된 결함의 실패 테스트를 기록 | PASS | test_apply_coupon_gives_remainder_to_the_last_item 관련 실패가 기록됨 |
| 9 | 실패 원인 분류가 TEST_DEFECT | PASS | 분류: 'TEST_DEFECT' |
| 10 | Planner 2차가 호출되지 않음 | PASS | plan.md 가 결함 주입 시점 스냅샷과 동일 |
| 11 | Developer 2차가 호출되지 않음 | PASS | change-log-2.md 없음 |
| 12 | Tester 2차가 호출되지 않음 | PASS | test-result-2.md 없음 |
| 13 | Reviewer가 호출되지 않음 | PASS | review.md 없음 |
| 14 | state.json 존재 | PASS | state.json 파싱 성공 |
| 15 | state.json retry_count == 0 | PASS | retry_count=0 |
| 16 | state.json retry_budget == 3 | PASS | retry_budget=3 |
| 17 | state.json unknown_retry_used == false | PASS | unknown_retry_used=False |
| 18 | state.json final_status == BLOCKED | PASS | final_status='BLOCKED' |
| 19 | state.json current_stage == DONE | PASS | current_stage='DONE' |
| 20 | state.json blocked_reason == TEST_DEFECT_NEEDS_HUMAN | PASS | blocked_reason='TEST_DEFECT_NEEDS_HUMAN' |
| 21 | state.json attempts 가 1회 기록 | PASS | 시도 1회 기록됨 |
| 22 | attempts[0] 이 FAIL / TEST_DEFECT | PASS | status='FAIL', failure_category='TEST_DEFECT' |
| 23 | state.json review.verdict 없음 | PASS | review={'verdict': None, 'file': None} |
| 24 | 주입된 모순 테스트가 그대로 남아 있고 기존 테스트가 변경되지 않음 | PASS | 설치 원본 fixture + 주입 코드와 내용이 완전히 일치 |
| 25 | eval 테스트가 약화되지 않음 | PASS | 원래 테스트 함수가 모두 유지되고 skip 처리가 없음 |
| 26 | 기존 추적 파일이 변경되지 않음 | PASS | 새로 생긴 변경은 eval fixture(untracked)뿐 |
| 27 | report.md 존재 | PASS | 최종 보고서 존재 |
| 28 | report.md 에 BLOCKED 종료와 사유가 기록됨 | PASS | BLOCKED 기록=True / TEST_DEFECT_NEEDS_HUMAN 기록=True |
| 29 | eval fixture 제거 | PASS | 제거=['sample-project/src/expense/coupon.py', 'sample-project/tests/test_coupon.py'] |
| 30 | sample-project 원상 복구 | PASS | setup 시점 상태와 동일 |
| 31 | 복구 후 기존 테스트 결과가 setup 시점과 동일 | PASS | setup 시점='57 passed' / 현재='57 passed' |

## 종합
31/31 항목 통과
