# Fault Injection

## Fault ID
env_error_001

## 주입 시각
2026-08-20T16:17:18

## 대상 파일
`sample-project/config/settlement_runtime.json`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 실행 환경 오류 라우팅을 실제 pytest 실행으로 검증하기 위해, 테스트 실행에 필요한
런타임 리소스를 제거한다. `test-result-N.md` 의 `STATUS:` 나 실패 원인 분류 문자열을 임의로
바꾸지 않고, Tester가 실제 실행 결과만 보고 판정하도록 만드는 것이 목적이다.

## 결함 내용
테스트 실행에 필요한 런타임 설정 리소스를 삭제해 pytest 수집 단계에서 실행 환경 오류를 만든다.

## 주입 방식
이번 eval의 setup이 설치한 런타임 리소스 파일 하나를 삭제한다. 제품 코드는 한 글자도 바꾸지
않는다. 제품 코드를 깨뜨리면 `PRODUCT_CODE_DEFECT` 로 분류하는 것이 옳은 판정이 되어
검증하려는 경로를 지나가지 못한다.

## 주입 후 증상
tests/conftest.py 로딩 중 RuntimeError 로 중단되어 테스트가 하나도 수집·실행되지 않는다.

## 삭제 안전장치
| 조건 | 확인 주체 |
| --- | --- |
| `sample-project/` 안의 상대 경로이며 심볼릭 링크가 아님 | `eval_harness.py` |
| Git 추적 파일이 아님 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 이번 eval의 setup이 설치한 파일임 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 파일 내용에 `patchpilot-eval:env_error_001` 표식이 있음 | `env_error_001.precheck_fs` |

하나라도 어긋나면 파일을 지우지 않고 즉시 실패한다.

## 삭제 전 파일 해시 (sha256)
`c550ce4adbb1ee646276243afd8d8cf7618c04602063e6b8d8c20012b8819803`

## 복구 주체
없음. eval teardown이 나머지 fixture와 함께 정리한다.

`ENVIRONMENT_ERROR` 는 재시도 예산을 소비하지 않고 즉시 종료하는 경로이므로
(`CLAUDE.md §20`), Developer 2차가 이 리소스를 되살리는 일 자체가 일어나지 않아야 한다.

## 복구되지 않았는지 확인하는 방법
`sample-project/config/settlement_runtime.json` 이 여전히 존재하지 않는지 확인한다.
`eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
