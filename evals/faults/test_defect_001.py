"""테스트 결함(TEST_DEFECT) 라우팅 검증용 결함 정의 (test_defect_001).

`retry_001` / `plan_defect_001` 과 달리 제품 코드를 건드리지 않고, `env_error_001` 과 달리
파일을 삭제하지도 않는다. 이번 eval이 설치한 **테스트 fixture에 테스트 하나를 추가** 한다.

핵심은 추가된 테스트가 기존 테스트와 **같은 입력에 대해 서로 다른 정확한 반환값** 을
요구한다는 점이다.

    기존: apply_coupon(1000, 3) == [334, 333, 333]
    추가: apply_coupon(1000, 3) == [333, 333, 334]

두 요구는 동시에 만족시킬 수 없다. `apply_coupon` 이 무엇을 반환하든 둘 중 하나는 반드시
실패하므로, **어떤 제품 코드 구현으로도 전체 테스트를 통과시킬 수 없는 상태** 가 된다.
Developer를 몇 번 다시 부르든 해결되지 않고, 계획 범위를 넓혀도 해결되지 않는다.
테스트 자체가 모순이라는 사실을 사람이 판단해야 풀린다.

이것이 `CLAUDE.md §14` 의 `TEST_DEFECT` 정의이며, `CLAUDE.md §20` 은 이 경우 자동으로
테스트를 고치지 않고 즉시 `BLOCKED` 로 종료하도록 정하고 있다.

주입은 파일 끝에 테스트 함수 하나를 덧붙이는 방식이다. 기존 테스트를 수정·삭제·skip 처리하지
않는다. `CLAUDE.md §3-3` 이 금지하는 "테스트 약화" 를 결함 주입 스스로가 저지르면, 이 eval이
검증하려는 상황이 아니라 Harness가 규칙을 어긴 상황이 되기 때문이다.

주입된 테스트는 누구도 제거하지 않는다. `TEST_DEFECT` 는 재시도 예산을 소비하지 않고 즉시
종료하는 경로이므로(`CLAUDE.md §20`), Developer 2차가 존재하지 않는 것이 정상이다.
추가된 테스트는 eval teardown에서 테스트 fixture 전체와 함께 정리된다.
"""

FAULT_ID = "test_defect_001"

# 결함 유형. 제품 코드가 아니라 설치된 테스트 fixture에 테스트를 덧붙인다.
FAULT_KIND = "test_injection"

TARGET_PATH = "sample-project/tests/test_coupon.py"

# 주입 여부와 잔존 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:test_defect_001"

# 주입 전제 조건. 모순의 상대편이 되는 기존 테스트가 없으면 주입하지 않는다.
ANCHOR = "def test_apply_coupon_distributes_remainder_to_earlier_items_first("

# 이 결함으로 새로 실패하게 되는 테스트 이름.
SIGNATURE_TEST = "test_apply_coupon_gives_remainder_to_the_last_item"

DESCRIPTION = (
    "기존 테스트와 같은 입력에 서로 다른 반환값을 요구하는 테스트를 추가해 "
    "어떤 제품 코드로도 전체 테스트를 통과시킬 수 없게 만든다."
)

# 주입 이후 Tester가 실제로 보게 되는 증상.
SYMPTOM = (
    "apply_coupon(1000, 3) 에 대해 [334, 333, 333] 과 [333, 333, 334] 를 각각 요구하는 두 "
    "테스트가 같은 파일에 공존하며, 둘 중 하나는 어떤 구현에서도 반드시 실패한다."
)

FAULT_CODE = f'''

# ref: {MARKER}
def {SIGNATURE_TEST}():
    assert apply_coupon(1000, 3) == [333, 333, 334]
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def precheck_test(context: dict) -> None:
    """테스트 fixture에 테스트를 덧붙여도 되는지 검사한다.

    `eval_harness.py` 도 같은 조건을 독립적으로 검사한다. 결함 정의가 잘못 작성되더라도
    사용자의 실제 테스트가 바뀌지 않도록 두 곳에서 함께 막는 것이 목적이다.

    특히 `fixture_content` 와의 완전 일치를 요구한다. 주입 이전에 이미 누군가 테스트 파일을
    고쳤다면, 그 뒤에 무엇을 주입해도 "기존 테스트는 그대로 두고 하나만 추가했다" 는 전제가
    성립하지 않기 때문이다.

    Args:
        context: 주입 대상의 현재 상태.
            - `target`: 저장소 루트 기준 경로
            - `installed`: 이번 eval의 setup이 설치한 파일 목록
            - `tracked`: Git 추적 대상 여부
            - `exists`: 파일 존재 여부
            - `content`: 파일 내용 (읽을 수 없으면 None)
            - `fixture_content`: 설치 원본인 fixture 파일 내용

    Raises:
        ValueError: 주입해서는 안 되는 대상이거나 전제 조건이 깨진 경우.
    """
    target = context.get("target")

    if not context.get("exists"):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 주입 대상이 존재하지 않습니다. ({target})"
        )
    if context.get("tracked"):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 주입 대상이 Git 추적 파일입니다. ({target})"
        )
    if target not in tuple(context.get("installed") or ()):
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 이번 eval이 설치한 파일이 아닙니다. ({target})"
        )

    content = context.get("content") or ""
    fixture_content = context.get("fixture_content")
    if fixture_content is None:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 설치 원본 fixture 내용을 확인할 수 없습니다. "
            f"({target})"
        )
    if content != fixture_content:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 주입 대상이 설치 시점 fixture와 다릅니다. "
            f"누군가 이미 테스트 파일을 수정했으므로 '기존 테스트를 그대로 두고 하나만 추가한다' "
            f"는 전제가 성립하지 않습니다. ({target})"
        )


def apply(source: str) -> str:
    """대상 파일 내용에 모순 테스트를 덧붙인 새 내용을 반환한다.

    Raises:
        ValueError: 주입 전제 조건을 만족하지 못하거나 이미 주입되어 있는 경우.
    """
    if is_applied(source):
        raise ValueError(f"{FAULT_ID} 결함이 이미 주입되어 있습니다.")
    if ANCHOR not in source:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 대상 파일에서 '{ANCHOR}' 를 찾지 못했습니다. "
            f"모순의 상대편이 되는 기존 테스트가 없으면 주입하지 않습니다."
        )

    return source.rstrip("\n") + "\n" + FAULT_CODE
