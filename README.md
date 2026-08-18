# 🔧 PatchPilot

> **Harness Engineering 기반 AI 자율 버그 분석 및 수정 시스템**

PatchPilot은 개발자가 버그 또는 수정 요구사항을 전달하면 AI Agent가 프로젝트의 코드를 분석하고, 수정 계획을 수립한 뒤 **코드 수정 → 테스트 → 검증 → 리뷰** 과정을 반복적으로 수행하도록 설계하는 Harness Engineering 프로젝트입니다.

단순히 LLM에게 코드를 생성하도록 요청하는 것을 넘어, AI가 실제 개발 작업을 안정적으로 수행할 수 있도록 **역할, 규칙, 도구, 테스트 및 검증 환경을 구조화하는 것**을 목표로 합니다.

---

## 📌 Project Overview

일반적인 AI Coding Assistant는 개발자의 요청을 받아 코드를 생성하거나 수정하는 방식으로 동작합니다.

```text
Developer
    ↓
AI Coding Assistant
    ↓
Code Generation
```

PatchPilot은 여기에 개발 프로세스를 제어하는 Harness를 구성합니다.

```text
Bug / Requirement
        ↓
   Planner Agent
        ↓
 Developer Agent
        ↓
   Tester Agent
        ↓
   Test Result
     ↙     ↘
  Failed   Passed
    ↓        ↓
 Re-Fix   Reviewer Agent
    ↓        ↓
 Re-Test   Final Report
```

이를 통해 AI가 단순히 코드를 생성하는 것에서 끝나는 것이 아니라 **계획 → 구현 → 테스트 → 실패 분석 → 재수정 → 리뷰**의 개발 사이클을 수행하도록 만드는 것이 목표입니다.

---

## 🎯 Goals

PatchPilot의 주요 목표는 다음과 같습니다.

* AI Agent의 역할과 책임 분리
* 프로젝트 개발 규칙을 AI에게 지속적으로 제공
* 버그 요구사항 기반 코드 분석 및 수정
* 코드 수정 후 자동 테스트
* 테스트 실패 원인 분석 및 재수정
* 코드 리뷰를 통한 최종 검증
* Agent 실행 과정 기록
* Harness 적용 전후 AI 개발 성능 비교

최종적으로 다음 질문을 실험을 통해 확인하고자 합니다.

> **"잘 설계된 Harness가 AI Coding Agent의 개발 성공률과 안정성을 실제로 향상시킬 수 있는가?"**

---

## 🤖 Agent Architecture

PatchPilot에서는 개발 작업을 역할별 Agent로 분리합니다.

### Planner Agent

사용자의 버그 또는 요구사항을 분석하고 작업 계획을 수립합니다.

**Responsibilities**

* 요구사항 분석
* 관련 코드 탐색
* 수정 범위 결정
* 작업 단계 생성

### Developer Agent

Planner가 작성한 계획을 기반으로 실제 코드를 수정합니다.

**Responsibilities**

* 기존 코드 분석
* 버그 수정
* 기능 구현
* 기존 프로젝트 구조 및 Coding Convention 준수

### Tester Agent

수정된 코드가 정상적으로 동작하는지 검증합니다.

**Responsibilities**

* 기존 테스트 실행
* 필요한 테스트 케이스 작성
* 실패 테스트 분석
* Regression 확인

### Reviewer Agent

수정된 코드의 최종 품질을 검토합니다.

**Responsibilities**

* 코드 품질 검토
* 불필요한 변경 확인
* 잠재적인 버그 확인
* 요구사항 충족 여부 확인

---

## 🏗 Harness Architecture

```text
                   ┌─────────────────┐
                   │ Bug Requirement │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Planner Agent  │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ Developer Agent │◀─────────┐
                   └────────┬────────┘          │
                            │                   │
                            ▼                   │
                   ┌─────────────────┐          │
                   │  Tester Agent   │          │
                   └────────┬────────┘          │
                            │                   │
                       Test Result              │
                       /         \              │
                    FAIL         PASS           │
                     │             │            │
                     └─────────────┘            │
                     Re-Fix ────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │ Reviewer Agent  │
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  Final Report   │
                          └─────────────────┘
```

---

## 🛠 Tech Stack

현재 계획 중인 기술 구성입니다.

| Category          | Technology                          |
| ----------------- | ----------------------------------- |
| AI Coding Agent   | Claude Code                         |
| Harness           | CLAUDE.md, Subagents, Skills, Hooks |
| Backend           | Python, FastAPI                     |
| Frontend          | Next.js                             |
| Testing           | Pytest                              |
| Agent Integration | MCP                                 |
| Container         | Docker                              |
| Version Control   | Git, GitHub                         |

> 기술 스택은 MVP 구현 과정에서 변경될 수 있습니다.

---

## 📁 Project Structure

```text
patchpilot/
│
├── CLAUDE.md
│
├── .claude/
│   ├── agents/
│   │   ├── planner.md
│   │   ├── developer.md
│   │   ├── tester.md
│   │   └── reviewer.md
│   │
│   └── skills/
│
├── sample-project/
│
├── tests/
│
├── reports/
│
└── README.md
```

---

## 🔄 Development Roadmap

### Phase 1 — Harness MVP

* [ ] 프로젝트 기본 구조 구성
* [ ] `CLAUDE.md` 개발 규칙 정의
* [ ] Planner Agent 구현
* [ ] Developer Agent 구현
* [ ] Tester Agent 구현
* [ ] Reviewer Agent 구현
* [ ] Sample Project 구축

### Phase 2 — Automated Validation

* [ ] 자동 테스트 실행
* [ ] 테스트 실패 결과 Agent 전달
* [ ] 실패 시 자동 재수정
* [ ] 최대 재시도 횟수 제어
* [ ] Agent 실행 로그 저장

### Phase 3 — GitHub Integration

* [ ] GitHub Issue 연동
* [ ] Issue 기반 작업 생성
* [ ] 수정 결과 Git Diff 생성
* [ ] Pull Request 자동화 검토

### Phase 4 — Observability

* [ ] Agent 실행 Dashboard
* [ ] Agent별 작업 상태 표시
* [ ] 테스트 결과 시각화
* [ ] 실행 시간 측정
* [ ] Token 사용량 측정

### Phase 5 — Evaluation

Harness 적용 전후 동일한 Bug Task를 수행하여 성능을 비교합니다.

평가 지표:

* Task Success Rate
* Test Pass Rate
* 평균 수정 횟수
* 평균 실행 시간
* Token Usage
* 잘못된 파일 수정 횟수

---

## 📊 Evaluation Plan

```text
             Baseline                PatchPilot
                 │                       │
                 ▼                       ▼
        Claude Code Only         Claude Code + Harness
                 │                       │
                 └──────────┬────────────┘
                            │
                    Same Bug Dataset
                            │
                            ▼
                       Evaluation
```

동일한 버그 데이터셋을 대상으로 기본 Claude Code 환경과 PatchPilot Harness 환경을 비교하여 Harness Engineering의 효과를 측정할 예정입니다.

---

## 🚀 Current Status

**Phase 1 — Harness MVP 설계 및 개발 진행 중**

현재 프로젝트 구조와 Agent 역할을 정의하고 있으며, 작은 Sample Project를 대상으로 Harness의 기본 개발 루프를 구현할 예정입니다.

---

## 🔮 Future Work

향후 다음 기능을 추가할 예정입니다.

* GitHub Issue 기반 자동 Bug Fix
* Pull Request 자동 생성
* MCP 기반 외부 개발 도구 연동
* Agent Memory
* 실행 과정 Dashboard
* 다양한 프로젝트 및 언어에 대한 Harness 평가
* Agent별 성능 및 비용 분석

---

## 💡 Key Point

PatchPilot의 핵심은 **AI가 코드를 얼마나 많이 생성하는가**가 아닙니다.

AI Coding Agent가 실제 개발 환경에서 더 안정적으로 작업할 수 있도록 **Context, Rules, Tools, Validation, Feedback Loop를 어떻게 설계할 것인가**를 실험하고 구현하는 것이 이 프로젝트의 핵심입니다.
