import Link from 'next/link'
import { notFound } from 'next/navigation'

import { Markdown } from '@/components/Markdown'
import { Badge, Section } from '@/components/Ui'
import { getEval, getEvals } from '@/lib/evals'
import { readExampleFile } from '@/lib/parse'
import type { Artifact, EvalDetail } from '@/lib/types'

export function generateStaticParams() {
  return getEvals().flatMap((item) =>
    item.artifacts.map((artifact) => ({ evalId: item.id, slug: artifact.slug })),
  )
}

/** 사이드바를 파이프라인 순서로 묶는다. `plan.md` 는 별칭이므로 항목으로 세우지 않는다. */
function groupArtifacts(detail: EvalDetail): { title: string; items: Artifact[] }[] {
  const groups: { title: string; items: Artifact[] }[] = []
  const listed = detail.artifacts.filter((artifact) => !artifact.isFinalPlanAlias)

  const plans = listed.filter((item) => item.kind === 'plan' || item.kind === 'plan-final')
  if (plans.length > 0) groups.push({ title: 'Plan', items: plans })

  const attempts = [...new Set(detail.state.attempts.map((attempt) => attempt.n))]
  for (const n of attempts) {
    const items = listed.filter(
      (item) =>
        item.attempt === n &&
        (item.kind === 'fault-injection' ||
          item.kind === 'change-log' ||
          item.kind === 'test-result'),
    )
    if (items.length > 0) groups.push({ title: `Attempt ${n}`, items })
  }

  const results = listed.filter((item) =>
    ['review', 'report', 'state', 'eval-result'].includes(item.kind),
  )
  if (results.length > 0) groups.push({ title: 'Result', items: results })

  return groups
}

export default async function ArtifactPage({
  params,
}: {
  params: Promise<{ evalId: string; slug: string }>
}) {
  const { evalId, slug } = await params
  const detail = getEval(evalId)
  const artifact = detail.artifacts.find((item) => item.slug === slug)
  if (!artifact) notFound()

  const text = readExampleFile(detail.dir, artifact.file)
  if (text === null) notFound()

  const groups = groupArtifacts(detail)
  const aliasFor = detail.artifacts.find((item) => item.isFinalPlanAlias)
  const lastPlanSnapshot = detail.plans[detail.plans.length - 1]

  return (
    <>
      <p className="breadcrumb">
        <Link href="/">Overview</Link> / <Link href={`/evals/${detail.id}/`}>{detail.shortId}</Link>{' '}
        / {artifact.file}
      </p>

      <div className="viewer">
        <nav className="sidebar">
          {groups.map((group) => (
            <div key={group.title} className="sidebar__group">
              <p className="sidebar__title">{group.title}</p>
              {group.items.map((item) => (
                <Link
                  key={item.slug}
                  href={`/evals/${detail.id}/artifacts/${item.slug}/`}
                  className={`sidebar__item ${item.slug === artifact.slug ? 'is-active' : ''}`}
                >
                  {item.file}
                </Link>
              ))}
              {group.title === 'Plan' && aliasFor && lastPlanSnapshot ? (
                <p className="sidebar__alias">
                  plan.md = {lastPlanSnapshot.file} (최종 계획, 내용 동일)
                </p>
              ) : null}
            </div>
          ))}
        </nav>

        <div>
          <div className="page-head">
            <h1 className="page-head__title page-head__title--file">
              {artifact.file}
              {artifact.attempt ? <Badge tone="muted">attempt {artifact.attempt}</Badge> : null}
            </h1>
            <p className="page-head__meta">
              reports/examples/{detail.dir}/{artifact.file}
            </p>
          </div>

          {artifact.kind === 'state' ? (
            <Section title="state.json">
              <div className="prose prose--raw">
                <pre>
                  <code>{text}</code>
                </pre>
              </div>
            </Section>
          ) : (
            <Markdown text={text} />
          )}
        </div>
      </div>
    </>
  )
}
