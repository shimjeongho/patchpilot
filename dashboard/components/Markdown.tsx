import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Harness 산출물 렌더링.
 *
 * 산출물은 GFM 표를 많이 쓴다(`eval-result.md` 의 자동 검증 항목, `fault-injection.md` 의
 * 해시 표). remark-gfm 없이는 그 표가 그대로 파이프 문자로 보인다.
 */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}
