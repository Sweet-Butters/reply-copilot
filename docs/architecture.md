# 아키텍처: reply-copilot

작성 2026-09-28. "메일·댓글에 답장할 초안을 만들어 주되, 보내는 건 사람이 한다"는 도구의 첫 버전 설계.

## 1. 무엇을 만드는가

```
채널 어댑터(읽기 전용)  →  전처리(서명·인용문 제거, 개인정보 마스킹)
   →  판단(Jev: 의도·긴장도 0–9·지금 답해야 하나·상대가 원하는 것·스팸/악성)
   →  분기: 스팸·악성·답장 불필요면 여기서 멈춤 (초안 LLM 호출 없음)
   →  초안(LLM이 후보 3개)  →  후보 필터(중복·앵무새·빈 문자열 제거)
   →  순위(Jev가 3개 중 가장 적절한 것 선택, 확률 포함)
   →  보관: 메일은 Gmail "임시보관함 초안" 1건, 댓글은 로컬 승인 대기열
   →  사람이 검토하고 직접 보냄
```

설계 원칙은 [jev-chat-jarvis](https://github.com/jev-chat/jev-chat-jarvis)와 Windows판([jev-chat-windows](https://github.com/jev-chat/jev-chat-windows))에서 가져왔다.

- **판단 먼저, 작성은 나중.** jarvis README의 첫 번째 주장. 판단 결과가 초안 프롬프트의 "참고 메모"로 들어가고, 판단이 "답할 필요 없음"이면 초안 모델을 아예 부르지 않는다.
- **판단/작성/순위를 서로 다른 모델이 맡는다.** jarvis는 판단·회신·시각 세 경로를 따로 설정한다. 여기서는 판단(=순위)과 작성 두 경로.
- **채널 = 작은 어댑터 하나.** jarvis는 앱마다 "제목 + 메시지 목록"만 돌려주는 수십 줄짜리 어댑터를 쓴다. 여기서도 어댑터는 `fetch()`(새 메시지 읽기)와 `stage()`(초안 보관) 두 함수만 가진다.
- **자동 발송 금지.** jarvis는 입력창에 채우기만 하고 전송 버튼은 사람이 누른다. 이 프로젝트의 코드에는 메일 발송(`messages.send`)도, 댓글 게시(`comments.insert`, `POST /replies`)도 **구현되어 있지 않다.**
- **후보 출구 필터.** Windows판 `draft.py`처럼, 들어온 메시지를 그대로 따라 한 후보나 중복 후보는 버린다(프롬프트 인젝션 방어의 마지막 줄).

## 2. 검토한 선택지

### 2.1 실행 형태

| 선택지 | 장점 | 단점 | 결론 |
|---|---|---|---|
| **A. 순수 Python 패키지 + CLI, 로컬 PC에서 실행 (필요하면 Windows 작업 스케줄러)** | 원문·토큰이 내 PC 밖으로 안 나감. 의존성 최소(코어는 표준 라이브러리만). 테스트·모의 실행 쉬움. OAuth 설치형 앱 흐름 그대로 사용 | PC가 꺼져 있으면 안 돎. 실시간 아님 | **채택** |
| B. GitHub Actions cron (mail-notifier 방식) | 서버 불필요, 무료 | 메일 원문이 CI 러너를 거침. Gmail/Meta 토큰을 저장소 Secret에 둬야 함. 상태(본 메시지 ID)를 커밋하거나 캐시해야 함. "원문은 로컬에" 원칙과 충돌 | 기각. 알림만 필요할 땐 여전히 좋은 선택 |
| C. 서버리스(Cloud Run/Lambda) + Gmail Pub/Sub push + Instagram Webhook | 실시간. 폴링 비용 없음 | 공개 HTTPS 엔드포인트, Pub/Sub 토픽, Meta 웹훅 검증, 비밀 관리가 필요. 1인용 v1에 과함 | 기각(나중에 실시간이 꼭 필요하면 재검토) |

### 2.2 오케스트레이션

| 선택지 | 결론 |
|---|---|
| **고정된 함수 파이프라인 (`pipeline.py` 한 파일)** | **채택.** 단계가 항상 같다(판단→분기→작성→순위). 모델이 도구를 골라 쓰는 열린 문제가 아니다 |
| 에이전트 프레임워크(LangGraph, Pydantic AI, Claude Agent SDK 등) | 기각. 루프·도구 선택이 없는 작업에 프레임워크를 얹으면 의존성과 디버깅 비용만 는다. 또 "에이전트가 스스로 보낸다"는 실수의 여지를 원천적으로 없애는 게 목적이다 |

### 2.3 상태 저장

| 선택지 | 결론 |
|---|---|
| **SQLite (`data/state.db`, 표준 라이브러리 `sqlite3`)** | **채택.** 본 메시지 ID(중복 처리 방지), 판단·후보 기록, 댓글 승인 대기열을 한 파일에. 트랜잭션·조회가 됨 |
| JSON 파일(mail-notifier의 `last_seen_id.txt` 방식) | 기각. 대기열 상태 변경(대기→승인→완료)과 동시 실행에 약함 |

`data/`는 `.gitignore`에 들어 있다. 원문은 여기에만 남는다.

## 3. 채택한 구조

```
reply_copilot/
  models.py        Message / Judgment / Candidate / Outcome 데이터 클래스
  config.py        환경변수 → Settings (파일에서 키를 읽지 않음)
  privacy.py       인용문·서명 제거, 이메일·전화번호 마스킹, 로그용 비밀 가리기
  questions.py     Jev 질문 세트(영어 지시문, 본문은 한국어 그대로)와 순위 질문
  pipeline.py      judge_first() 와 draft_direct()(비교용 기준선)
  store.py         SQLite: seen / outcomes / queue
  providers/
    base.py        Judge, Drafter 프로토콜 + 사용량(토큰·지연·비용) 기록
    typesafe.py    Jev: TypeSafe 직결 / OpenRouter / Vercel / OpenCode Zen (요청 형태 동일)
    openai_compat.py  DeepSeek / OpenRouter / OpenAI 호환 chat completions
    anthropic.py   Claude (공식 SDK, 설치돼 있을 때만)
    mock.py        키 없이 도는 규칙 기반 판단 + 템플릿 초안
    __init__.py    이름 → 공급자 생성 (환경변수로 교체)
  adapters/
    base.py        Adapter 프로토콜: fetch(), stage()
    fixtures.py    eval/fixtures/*.json 을 메시지로
    gmail.py       Gmail 읽기 + 초안 저장(drafts.create). 발송 없음
    youtube.py     내 채널 댓글 읽기(commentThreads.list). 게시 없음 → 대기열
    instagram.py   내 프로페셔널 계정 댓글 읽기(Instagram Login API). 게시 없음 → 대기열
  evaluation.py    오프라인 평가: judge_first vs draft_direct
  cli.py           run / review / eval / auth
```

### 3.1 새 채널 추가

`adapters/`에 파일 하나를 만들고 두 함수를 구현한 뒤 `adapters/__init__.py`의 표에 한 줄 추가한다.

```python
class MyAdapter:
    name = "mychannel"
    def fetch(self, limit: int) -> list[Message]: ...        # 읽기 전용
    def stage(self, msg: Message, reply: str, store) -> str: ...  # 초안 보관(보내지 않음)
```

판단·작성·순위·저장·평가 코드는 건드리지 않는다.

### 3.2 공급자 교체

| 역할 | 환경변수 | 값 |
|---|---|---|
| 판단·순위 | `REPLY_JUDGE` | `typesafe`(기본, `TYPESAFE_API_KEY`) · `openrouter`(`OPENROUTER_API_KEY`, `/api/alpha/decisions`) · `vercel` · `opencode` · `mock` |
| 작성 | `REPLY_DRAFTER` | `anthropic`(`ANTHROPIC_API_KEY`) · `deepseek`(`DEEPSEEK_API_KEY`) · `openrouter` · `openai` · `mock` |
| 모델 | `JEV_MODEL`, `DRAFT_MODEL` | 공급자별 기본값 있음 |

키가 없는 공급자를 고르면 자동으로 `mock`으로 떨어지고 그 사실을 출력한다(`--strict`면 오류). 판단 실패 시 파이프라인은 "판단 없음"으로 초안만 만들고 순위는 생략한다 — contest-tracker의 `jev.py`처럼 Jev는 보조이지 단일 장애점이 아니다.

### 3.3 Jev 질문 설계

jarvis/Windows판 질문 세트는 연인·친구 대화용(`confirm_you_care`, 최후통첩 등)이라 메일·댓글에 맞게 다시 썼다. Jev는 영어에 최적화돼 있으므로(공식 문서) 지시문과 기준은 영어, 본문은 한국어 그대로 둔다.

| 이름 | 형 | 쓰임 |
|---|---|---|
| `needs_reply` | noul | 0.35 미만이면 초안 생략 |
| `spam` | noul | 0.7 이상이면 "무시/숨김 제안", 초안 생략 |
| `abusive` | noul | 0.7 이상이면 "대응하지 않음/숨김 검토", 초안 생략 |
| `reply_now` | noul | 우선순위 정렬 |
| `intent` | choice | question / request / scheduling / invitation / complaint / feedback / thanks_or_fyi / promotion |
| `sender_wants` | choice | information / decision / commitment / apology / acknowledgement / nothing |
| `best_action` | choice | answer / accept / decline_politely / ask_clarification / acknowledge / ignore / escalate |
| `tension` | score(10단계) | 0–9. 7 이상은 "직접 쓰세요" 표시 |
| `best_reply` | choice | 순위 단계. 후보 3개를 기준(criteria)으로 넣고 확률을 받음 |

비용: Jev는 입력 100만 토큰당 $0.042, 출력 무료(docs.typesafe.ai/models). 한 번 판단이 1천 토큰 안팎이면 약 $0.00004.

## 4. 안전 규칙이 코드 어디에 있나

| 규칙 | 위치 |
|---|---|
| 자동 발송 금지 | 발송/게시 API를 호출하는 코드가 없음. `tests/test_safety.py`가 소스 전체에서 `messages().send`, `comments().insert`, `/replies` POST 등을 찾아 실패시킴 |
| 메일은 초안만 | `adapters/gmail.py: stage()` → `users.drafts.create`. `run`에 `--stage` 를 줘야만 호출, `--dry-run`이면 절대 호출 안 함 |
| 댓글은 승인 대기열 | `store.enqueue()`만 호출. `review` 명령으로 보고 복사해서 직접 올림 |
| 내 메일함·내 계정만 | Gmail `userId="me"`, YouTube `channels.list(mine=True)`, Instagram `/me` 만 사용. 남의 채널 ID를 받는 옵션 없음 |
| 공급자로 보내는 양 최소화 | `privacy.prepare()`: 인용 이력·서명 제거, 이메일·전화번호 → `[EMAIL]`/`[PHONE]`, 본문 2,000자 제한, 보낸 사람은 표시 이름만 |
| 원문은 로컬 | `data/state.db`(gitignore). 평가 결과 파일에는 가상 픽스처만 |
| 비밀을 로그에 남기지 않음 | 키는 환경변수에서만 읽음. `privacy.redact_secrets()`가 오류 메시지에서 키 값을 지움 |
| OAuth 토큰 | `~/.reply-copilot/tokens/`(저장소 밖). Instagram 장기 토큰은 환경변수 `IG_ACCESS_TOKEN` |

## 5. 테스트와 평가

- `tests/`: 표준 `unittest` (pytest로도 실행 가능). 네트워크 없이 HTTP를 가짜로 바꿔 TypeSafe 요청 형태, Gmail MIME 초안, YouTube/Instagram 파싱을 확인.
- `python -m reply_copilot eval`: 가상 한국어 픽스처 10개로 "판단 먼저"와 "바로 작성"을 비교. 키가 없으면 mock(하네스가 돈다는 것만 증명), 키가 있으면 `--real`로 실제 지연·토큰·비용 기록.

## 6. 알려진 한계

- Jev는 한국어 정확도가 영어보다 낮다(공식 문서). 임계값(0.35, 0.7)은 추정치이며 실제 메일 50건 정도로 보정해야 한다.
- Gmail 앱을 "테스트" 상태로 두면 refresh token이 7일마다 만료된다. 개인용이면 "프로덕션"으로 게시하고 미인증 경고를 감수하는 편이 낫다(`docs/channels.md`).
- 폴링 방식이라 실시간이 아니다.
