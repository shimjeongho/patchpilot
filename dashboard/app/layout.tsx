import type { Metadata } from 'next'
import Link from 'next/link'
import type { ReactNode } from 'react'

import './globals.css'

export const metadata: Metadata = {
  title: 'PatchPilot — Harness Evaluation Dashboard',
  description:
    'Fault Injection으로 검증한 PatchPilot Harness의 상태 전이와 Eval 결과를 reports/examples 에서 직접 읽어 보여줍니다.',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="site-header">
          <div className="site-header__inner">
            <Link href="/" className="brand">
              <span className="brand__mark" aria-hidden="true">
                PP
              </span>
              <span className="brand__text">
                <span className="brand__name">PatchPilot</span>
                <span className="brand__tagline">Harness Evaluation Dashboard</span>
              </span>
            </Link>

            <span className="site-header__meta">
              <span className="chip">
                <span className="chip__dot" aria-hidden="true" />
                static build
              </span>
              <span>
                데이터 원천 <code>reports/examples/</code> · 읽기 전용
              </span>
            </span>
          </div>
        </header>

        <main className="container">{children}</main>

        <footer className="site-footer">
          정적 빌드 산출물입니다. 서버·DB·인증 없이 빌드 타임에 Markdown/JSON을 직접 읽습니다.
        </footer>
      </body>
    </html>
  )
}
