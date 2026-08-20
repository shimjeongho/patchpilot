"""재시도 루프 검증용 결함 정의 (retry_001).

Developer 1차가 `split_tip` 을 수정해 정상 동작하게 만든 직후, 이 결함을 제품 코드에
주입해 Tester가 실제 pytest 실행으로 `STATUS: FAIL` 을 기록하도록 만든다.

주입 방식은 파일 끝에 후처리 래퍼를 덧붙이는 것이다. Developer 1차가 함수 본문을 어떻게
구현했는지와 무관하게 모듈 최상위의 `split_tip` 이름만 존재하면 동작하므로, 주입 결과가
Developer의 구현 세부사항에 좌우되지 않는다.

주입된 결함을 제거하는 주체는 Harness가 아니라 Developer 2차다. Harness가 스스로 되돌리면
`FAIL -> 분석 -> 재수정 -> PASS` 전이의 재수정 주체가 Developer가 아니게 되어 검증 의미가
사라진다.
"""

FAULT_ID = "retry_001"

TARGET_PATH = "sample-project/src/expense/tip.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:retry_001"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_tip("

DESCRIPTION = "split_tip 결과의 마지막 사람 몫을 0으로 덮어써 총액 보존을 깨뜨린다."

FAULT_CODE = f'''

# 마지막 사람은 팁 정산 대상에서 제외한다는 요구로 추가된 후처리. (ref: {MARKER})
_split_tip_before_last_person_rule = split_tip


def split_tip(bill: int, people: int, tip_percent: int) -> list[int]:
    shares = _split_tip_before_last_person_rule(bill, people, tip_percent)
    return shares[:-1] + [0]
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def apply(source: str) -> str:
    """대상 파일 내용에 결함을 주입한 새 내용을 반환한다.

    Raises:
        ValueError: 주입 전제 조건을 만족하지 못하거나 이미 주입되어 있는 경우.
    """
    if is_applied(source):
        raise ValueError(f"{FAULT_ID} 결함이 이미 주입되어 있습니다.")
    if ANCHOR not in source:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 대상 파일에서 '{ANCHOR}' 를 찾지 못했습니다."
        )

    return source.rstrip("\n") + "\n" + FAULT_CODE
