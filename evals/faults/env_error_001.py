"""실행 환경 오류 라우팅 검증용 결함 정의 (env_error_001).

`retry_001` / `plan_defect_001` 과 달리 제품 코드를 고치지 않는다. 테스트 실행에 필요한
런타임 리소스(`sample-project/config/settlement_runtime.json`)를 **삭제** 해서, Tester가
실제 pytest 실행에서 수집 단계 중단을 겪도록 만든다.

제품 코드를 깨뜨리지 않는 것이 핵심이다. 제품 코드 결함으로 실패시키면 Tester가
`PRODUCT_CODE_DEFECT` 로 분류하는 것이 옳다. 여기서 검증하려는 것은 "코드가 아니라 실행
환경이 준비되지 않아 테스트를 하나도 실행할 수 없는 상태" 이므로, 실패의 원인이 제품 코드
바깥에 있어야 한다.

주입 결과:

    tests/conftest.py 로딩 실패 -> 테스트 0건 수집 -> pytest 비정상 종료

주입 방식은 파일 삭제지만, 실제 삭제는 이 모듈이 아니라 `eval_harness.py` 가 수행한다.
파일을 지우는 코드가 여러 곳에 흩어지면 안전장치를 한곳에서 보장할 수 없기 때문이다.
이 모듈은 **무엇을 지울지와 지워도 되는 조건** 만 선언하고, 조건 검사는 `precheck_fs` 로
수행한다. (`evals/README.md §9`)

주입된 리소스는 누구도 복구하지 않는다. `ENVIRONMENT_ERROR` 는 재시도 예산을 소비하지 않고
즉시 종료하는 경로이므로(`CLAUDE.md §20`), Developer 2차가 존재하지 않는 것이 정상이다.
리소스는 eval teardown에서 나머지 fixture와 함께 정리된다.
"""

FAULT_ID = "env_error_001"

# 결함 유형. 제품 코드 문자열을 고치는 대신 설치된 런타임 리소스를 삭제한다.
FAULT_KIND = "resource_removal"

TARGET_PATH = "sample-project/config/settlement_runtime.json"

# 삭제 대상이 이번 eval이 설치한 fixture 사본인지 내용으로 확인하기 위한 표식.
MARKER = "patchpilot-eval:env_error_001"

DESCRIPTION = (
    "테스트 실행에 필요한 런타임 설정 리소스를 삭제해 pytest 수집 단계에서 실행 환경 오류를 만든다."
)

# 주입 이후 Tester가 실제로 보게 되는 증상.
SYMPTOM = (
    "tests/conftest.py 로딩 중 RuntimeError 로 중단되어 테스트가 하나도 수집·실행되지 않는다."
)


def precheck_fs(context: dict) -> None:
    """삭제 전제 조건을 검사한다. 하나라도 어긋나면 삭제하지 않고 실패시킨다.

    `eval_harness.py` 도 같은 조건을 독립적으로 검사한다. 결함 정의가 잘못 작성되더라도
    사용자의 실제 파일이 지워지지 않도록 두 곳에서 함께 막는 것이 목적이다.

    Args:
        context: 삭제 대상의 현재 상태.
            - `target`: 저장소 루트 기준 경로
            - `installed`: 이번 eval의 setup이 설치한 파일 목록
            - `tracked`: Git 추적 대상 여부
            - `exists`: 파일 존재 여부
            - `content`: 파일 내용 (읽을 수 없으면 None)

    Raises:
        ValueError: 삭제해서는 안 되는 대상이거나 전제 조건이 깨진 경우.
    """
    target = context.get("target")

    if not context.get("exists"):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 삭제 대상이 존재하지 않습니다. ({target})"
        )
    if context.get("tracked"):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 삭제 대상이 Git 추적 파일입니다. ({target})"
        )
    if target not in tuple(context.get("installed") or ()):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 이번 eval이 설치한 파일이 아닙니다. ({target})"
        )
    if MARKER not in (context.get("content") or ""):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 삭제 대상에서 '{MARKER}' 표식을 찾지 못했습니다. "
            f"({target})"
        )


def is_applied(context: dict) -> bool:
    """이 결함이 이미 주입되어 있는지(=리소스가 이미 사라졌는지) 판정한다."""
    return not context.get("exists")
