# reply-copilot

내 Gmail과 내 SNS(YouTube·Instagram) 댓글에 답장할 때, **먼저 판단하고 그다음에 초안을 쓰는** 도구입니다.
보내는 건 언제나 사람이 합니다.

```
새 메시지 → 전처리(인용문·서명 제거, 이메일·전화번호 가림)
  → Jev 판단: 의도 · 긴장도 0–9 · 지금 답해야 하나 · 상대가 원하는 것 · 스팸/악성
  → 스팸·악플·답장 불필요면 여기서 멈춤 (초안 모델 호출 없음)
  → LLM이 후보 3개 작성 → Jev가 순위
  → 메일: Gmail 임시보관함에 초안 1건 / 댓글: 로컬 승인 대기열
  → 사람이 검토하고 직접 보냄
```

설계는 [jev-chat-jarvis](https://github.com/jev-chat/jev-chat-jarvis)의 "판단 먼저, 작성은 나중" 흐름을 메일·댓글에 옮긴 것입니다. 자세한 선택 이유는 [docs/architecture.md](docs/architecture.md).

## 지금 바로 해 보기 (키 없이)

Python 3.10+만 있으면 됩니다. 코어는 표준 라이브러리만 씁니다.

```
python -m reply_copilot run --dry-run      # 가상 메시지 10개로 판단→초안→순위, 아무것도 쓰지 않음
python -m reply_copilot eval               # "판단 먼저" vs "바로 작성" 비교 (mock)
python -m pytest -q                        # 또는 python -m unittest discover -s tests
```

키가 없으면 자동으로 mock 판단(키워드 규칙)과 mock 초안(템플릿)을 씁니다. mock 결과는 파이프라인이 돈다는 것만 보여 줍니다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `run --channel {fixtures,gmail,youtube,instagram} [--limit N]` | 새 메시지를 읽고 판단·초안·순위를 출력. 기본은 드라이런(아무것도 저장 안 함) |
| `run ... --stage` | 최선 후보를 보관: Gmail은 임시보관함 초안, 댓글은 로컬 대기열. 처리한 메시지는 다시 보지 않음 |
| `review` | 승인 대기 중인 댓글 답글 목록과 링크 |
| `mark <번호> done\|dismissed` | 대기열 항목 처리 표시 |
| `eval [--real]` | 픽스처로 두 파이프라인 비교, `eval/results/`에 저장 |
| `auth gmail\|youtube` | Google OAuth 최초 로그인 |
| 공통 옵션 `--mock`, `--strict` | mock 강제 / 키 없으면 mock 대신 실패 |

## 설정 (환경변수만)

`.env.example` 참고. 키를 파일에 두지 마세요.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `REPLY_JUDGE` | `typesafe` | `typesafe` · `openrouter` · `vercel` · `opencode` · `mock` |
| `REPLY_DRAFTER` | `anthropic` | `anthropic` · `deepseek` · `openrouter` · `openai` · `mock` |
| `JEV_MODEL`, `DRAFT_MODEL` | 공급자별 | 예: `jev-latest`, `claude-opus-5` |
| `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | | 모델 키 |
| `OWNER_NAME`, `OWNER_EMAIL`, `OWNER_STYLE` | | 초안 말투, 내 메일 건너뛰기 |
| `SKIP_NO_REPLY_BELOW`, `SPAM_ABOVE`, `ABUSIVE_ABOVE`, `HAND_WRITE_TENSION` | 0.35 · 0.7 · 0.7 · 7 | 분기 임계값 |

채널 연결(OAuth 앱, 스코프, 계정 조건, 비용)은 [docs/channels.md](docs/channels.md).

## 안전 장치

- 메일 발송·댓글 게시 코드가 없습니다. 테스트가 소스 전체를 검사해서 생기면 실패합니다.
- 내 메일함(`userId=me`), 내 채널(`mine=true`), 내 계정(`/me`)만 읽습니다.
- 모델 공급자에게는 정리된 본문(최대 2,000자)과 보낸 사람 표시 이름만 갑니다. 원문은 `data/state.db`(git 제외)에만.
- 오류 메시지에서 키 값을 지웁니다. OAuth 토큰은 `~/.reply-copilot/tokens/`.

## 구조

```
reply_copilot/
  pipeline.py      judge_first / draft_direct
  questions.py     Jev 질문 세트
  privacy.py       전처리·마스킹·비밀 가리기
  providers/       typesafe.py, anthropic.py, openai_compat.py, mock.py
  adapters/        fixtures.py, gmail.py, youtube.py, instagram.py
  store.py         SQLite
  evaluation.py    오프라인 평가
  cli.py
eval/fixtures/     가상 한국어 메시지 10개
eval/results/      평가 결과
tests/             네트워크 없이 도는 테스트
```
