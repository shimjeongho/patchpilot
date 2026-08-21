# PatchPilot Dashboard

PatchPilot Harness의 Eval 결과를 한 화면에서 보여주는 정적 대시보드입니다.

`reports/examples/` 에 보존된 대표 실행 결과의 Markdown/JSON을 **빌드 타임에 직접 읽어**
정적 HTML로 내보냅니다. 서버, DB, API, 인증이 없습니다.

## 실행

```bash
cd dashboard
npm install
npm run dev      # http://localhost:3000
```

정적 빌드:

```bash
npm run build    # out/ 에 정적 HTML 생성
npm run typecheck
```

## 저장소 경계

이 디렉터리는 Harness 영역(`CLAUDE.md`, `.claude/`, `tasks/`, `evals/`)도 아니고
수정 대상 영역(`sample-project/`)도 아닙니다. **Harness 산출물의 읽기 전용 소비자**입니다.

- `reports/examples/` 를 **읽기만** 합니다. 쓰기 계열 fs 함수를 import 하지 않습니다.
- `evals/eval_harness.py` 를 import 하거나 수정하지 않습니다. 같은 파일 계약을 독립 구현합니다.
- Python 의존성을 추가하지 않습니다. `pyproject.toml` / `uv.lock` 과 무관합니다.
- `uv run pytest sample-project/tests -q` 의 수집 대상에 `.py` 파일이 하나도 없습니다.

## 데이터 계약

Dashboard가 의존하는 것은 `CLAUDE.md` 가 이미 규정한 산출물 계약입니다.

| 파일 | 읽는 값 | 근거 |
| --- | --- | --- |
| `state.json` | `final_status` · `retry_count` · `retry_budget` · `attempts[]` · `review` · `blocked_reason` | §19 |
| `test-result-N.md` | 첫 줄 `STATUS:` · `## 실행 명령` · `## 실패 원인 분류` | §14 |
| `review.md` | 첫 줄 `VERDICT:` | §15 |
| `plan[-N].md` | `## 수정 허용 파일 목록` | §13 |
| `eval-result.md` | 첫 줄 `EVAL:` · `## 검증 대상 전이` · `## 자동 검증 항목` · `## 종합` | `evals/README.md` |
| `fault-injection[-N].md` | `## Fault ID` · `## 대상 파일` · `## 결함 내용` | `evals/README.md` |

계약을 어긴 데이터는 조용히 넘기지 않고 **빌드를 실패시킵니다**. 잘못 읽은 값으로 요약을
보여주는 것이 이 대시보드에서 가장 나쁜 실패 모드이기 때문입니다.

`review.md` 가 없는 것처럼 **정상적인 부재**는 예외가 아닙니다. `eval-result.md` 가
"Reviewer가 호출되지 않음"을 자동 검증 항목으로 판정해 두었으므로, 그 판정을 읽어
"미호출 (자동 검증됨)"으로 표시합니다.

## 구조

```text
dashboard/
├── app/
│   ├── page.tsx                                 Overview (Summary + Eval 목록)
│   ├── evals/[evalId]/page.tsx                  Eval 상세 (Timeline · Attempts · 자동 검증)
│   └── evals/[evalId]/artifacts/[slug]/page.tsx Artifact 뷰어
├── components/  Ui · Timeline · Markdown
└── lib/         types · parse · evals · timeline
```

## Timeline

`state.json` 만으로는 상태 전이를 그릴 수 없습니다. EVAL-002의 Planner 재호출은
`state.json` 어디에도 없고 `plan-2.md` 라는 산출물의 존재로만 드러납니다.
그래서 `lib/timeline.ts` 는 다음 세 가지를 합성합니다.

1. `state.json` 의 `attempts[]`
2. 산출물 존재 여부 (`plan-N.md` → Planner 재호출, `review.md` → Reviewer 호출)
3. `fault-injection[-N].md` 의 결함 주입 기록

재시도 예산 누적은 `CLAUDE.md` §16 을 그대로 따릅니다.
`PRODUCT_CODE_DEFECT` · `PLAN_DEFECT` · `UNKNOWN` 은 예산을 소비하고,
`ENVIRONMENT_ERROR` · `TEST_DEFECT` 는 소비하지 않습니다.

합성한 누적값은 마지막에 `state.json` 의 `retry_count` 와 대조합니다.
어긋나면 표시값을 덮어쓰지 않고 화면에 경고로 드러냅니다.
