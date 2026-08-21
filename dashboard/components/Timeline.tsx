import Link from 'next/link'
import { Fragment, type ReactNode } from 'react'

import { Badge, RetryGauge } from '@/components/Ui'
import type { EventActor, Timeline as TimelineModel, TimelineEvent } from '@/lib/timeline'

const ACTOR_LABEL: Record<EventActor, string> = {
  PLANNER: 'Planner',
  DEVELOPER: 'Developer',
  FAULT: 'Fault',
  TESTER: 'Tester',
  ORCHESTRATOR: 'Orchestrator',
  REVIEWER: 'Reviewer',
  SKIPPED: '미호출',
  TERMINAL: '종료',
}

const ACTOR_MARK: Record<EventActor, string> = {
  PLANNER: 'P',
  DEVELOPER: 'D',
  FAULT: '!',
  TESTER: 'T',
  ORCHESTRATOR: 'O',
  REVIEWER: 'R',
  SKIPPED: '×',
  TERMINAL: '■',
}

/** 종료 노드는 결과 자체가 정보라서 글자 마크 대신 판정 기호를 쓴다. */
function markOf(event: TimelineEvent): string {
  if (event.actor === 'TERMINAL') return event.tone === 'ok' ? '✓' : '✕'
  return ACTOR_MARK[event.actor]
}

/**
 * 본문에 섞인 산출물·소스 파일명을 코드 조각으로 세운다.
 *
 * EVAL-002의 재계획 노드는 "2차에서 추가된 파일: ...charge_rounding.py" 한 줄이 핵심인데
 * 문장 안에 묻히면 읽히지 않는다. 문구는 그대로 두고 표시만 바꾼다.
 */
const FILE_TOKEN = /([\w./-]+\.(?:py|md|json))/g

function renderLine(line: string): ReactNode {
  const parts = line.split(FILE_TOKEN)
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <code key={index} className="tl__file">
        {part}
      </code>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  )
}

export function Timeline({
  timeline,
  evalId,
}: {
  timeline: TimelineModel
  evalId: string
}) {
  return (
    <div className="timeline">
      {!timeline.retryMatchesState ? (
        <p className="timeline__warning">
          합성한 retry_count({timeline.derivedRetryCount})가 state.json 의 값과 다릅니다. 표시값을
          덮어쓰지 않고 그대로 드러냅니다.
        </p>
      ) : null}

      <ol className="timeline__list">
        {timeline.events.map((event) => {
          // 재계획과 예산 소진은 흐름의 분기점이라 표시 강조만 따로 준다. 판정은 그대로다.
          const isReplan = event.actor === 'PLANNER' && event.badge === '재계획'
          const isExhausted =
            event.retryConsumed &&
            event.retryAfter !== null &&
            timeline.retryBudget > 0 &&
            event.retryAfter >= timeline.retryBudget

          const modifiers = [isReplan ? 'is-replan' : '', isExhausted ? 'is-exhausted' : '']
            .filter(Boolean)
            .join(' ')

          return (
            <li
              key={event.seq}
              className={`tl tl--${event.tone} tl--${event.actor.toLowerCase()} ${modifiers}`}
            >
              <span className="tl__mark" aria-hidden="true">
                {markOf(event)}
              </span>

              <div className="tl__body">
                <div className="tl__head">
                  <span className="tl__actor">{ACTOR_LABEL[event.actor]}</span>
                  <span className="tl__label">{event.label}</span>
                  {event.badge ? <Badge tone={event.tone}>{event.badge}</Badge> : null}
                  {event.actor === 'SKIPPED' ? (
                    <span className="tl__flag">실행되지 않은 단계</span>
                  ) : null}
                </div>

                {event.lines.map((line, index) => (
                  <p key={index} className="tl__line">
                    {renderLine(line)}
                  </p>
                ))}

                {event.links.length > 0 ? (
                  <div className="tl__links">
                    {event.links.map((link) => (
                      <Link
                        key={link.slug}
                        className="tl__link"
                        href={`/evals/${evalId}/artifacts/${link.slug}/`}
                      >
                        {link.file}
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="tl__retry">
                {event.retryBefore !== null && event.retryAfter !== null ? (
                  <>
                    <span className="tl__retry-label">retry</span>
                    <span className="tl__retry-delta">
                      {event.retryBefore} <span aria-hidden="true">→</span>{' '}
                      <b>{event.retryAfter}</b>
                    </span>
                    <RetryGauge count={event.retryAfter} budget={timeline.retryBudget} compact />
                  </>
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
