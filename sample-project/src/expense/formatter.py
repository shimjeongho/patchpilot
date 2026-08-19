"""분배 결과를 사람이 읽기 쉬운 문자열로 변환하는 기능."""


def format_split(amounts: list[int]) -> str:
    """분배 결과를 '<순번>번: <금액>원' 형태의 줄 단위 문자열로 변환한다.

    순번은 1부터 시작하며, 금액은 천 단위 구분 기호를 포함한다.
    """
    lines = [f"{index}번: {amount:,}원" for index, amount in enumerate(amounts, start=1)]
    return "\n".join(lines)
