# 채널별로 실제 연결하는 법

모든 채널은 **읽기 + 초안 보관**까지만 합니다. 메일 발송, 댓글 게시는 코드에 없습니다.
토큰은 `~/.reply-copilot/tokens/`(저장소 밖)에 저장되고, 키는 환경변수로만 읽습니다.

## 공통: 모델 키

| 역할 | 최소 설정 | 비용(2026-09 기준) |
|---|---|---|
| 판단·순위 (Jev) | `TYPESAFE_API_KEY` ([typesafe.ai](https://docs.typesafe.ai/)) | 입력 100만 토큰당 $0.042, 출력 무료. 메시지 1건당 판단+순위 약 2천 토큰 → 약 $0.0001 |
| 초안 (Claude 기본) | `ANTHROPIC_API_KEY`, `pip install anthropic` | `claude-opus-5` 입력 $5 / 출력 $25 (100만 토큰당). 초안 1건 입력 ~700·출력 ~250 토큰이면 약 $0.01 (추정). `DRAFT_MODEL=claude-sonnet-5`($2/$10)나 `claude-haiku-4-5`($1/$5)로 낮출 수 있음 |
| 초안 (대안) | `REPLY_DRAFTER=deepseek` + `DEEPSEEK_API_KEY` | 공급자 요금표 확인 후 `DRAFT_PRICE_IN`/`DRAFT_PRICE_OUT`을 넣으면 비용이 계산됨 |

OpenRouter 키 하나로 둘 다 쓰려면 `REPLY_JUDGE=openrouter REPLY_DRAFTER=openrouter OPENROUTER_API_KEY=...`.

## 1. Gmail

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성 → **Gmail API** 사용 설정.
2. **OAuth 동의 화면**: 사용자 유형 "외부", 테스트 사용자에 본인 Gmail 추가.
3. **사용자 인증 정보 → OAuth 클라이언트 ID → 데스크톱 앱** 생성, JSON 다운로드(저장소 밖에 보관).
4. 설치와 최초 로그인:
   ```
   pip install -e ".[google]"
   set GOOGLE_CLIENT_SECRET_FILE=C:\경로\client_secret.json
   set OWNER_EMAIL=본인주소@gmail.com
   python -m reply_copilot auth gmail
   ```
5. 확인: `python -m reply_copilot run --channel gmail --dry-run` (아무것도 쓰지 않음)
6. 초안 저장: `python -m reply_copilot run --channel gmail --stage` → Gmail **임시보관함**에 답장 초안 1건씩.

- **스코프**: `gmail.readonly`(읽기) + `gmail.compose`(초안 생성). Google에는 "초안만" 스코프가 없어서 `gmail.compose`는 발송 권한도 포함합니다. 코드는 발송을 호출하지 않고, `tests/test_cli_and_safety.py`가 발송 코드가 생기면 실패합니다.
- **둘 다 "제한(restricted)" 스코프**입니다. 앱을 "테스트" 상태로 두면 **refresh token이 7일마다 만료**되어 매주 `auth gmail`을 다시 해야 합니다. 본인 혼자 쓰는 앱이면 동의 화면을 "프로덕션"으로 게시하고 "확인되지 않은 앱" 경고를 감수하는 방법이 있습니다(외부 사용자에게 배포하려면 Google 보안 평가가 필요 — 이 프로젝트 범위 밖).
- 기본 검색어: `in:inbox is:unread newer_than:3d -category:promotions -category:social -category:forums`.
- 비용: Gmail API는 무료(사용자당 할당량 내).

## 2. YouTube 댓글

1. 같은 Google Cloud 프로젝트에서 **YouTube Data API v3** 사용 설정. 동의 화면 스코프에 `youtube.readonly` 추가.
2. `python -m reply_copilot auth youtube` (채널을 가진 Google 계정으로 로그인. 브랜드 계정 채널이면 로그인 시 그 채널 선택)
3. `python -m reply_copilot run --channel youtube --dry-run`, 괜찮으면 `--stage` → 로컬 승인 대기열.
4. `python -m reply_copilot review` 로 대기열 확인 → 링크를 열어 **직접** 답글 달기 → `python -m reply_copilot mark <번호> done`.

- 읽는 것: `channels.list(mine=true)`로 내 채널 ID, `commentThreads.list(allThreadsRelatedToChannelId=내 채널)`, 영상 제목용 `videos.list`. 모두 1 unit, 기본 할당량 하루 10,000 unit → 무료.
- 내가 이미 답한 스레드와 내 댓글은 건너뜁니다.
- 채널 ID를 고정하려면 `YOUTUBE_CHANNEL_ID`.
- 게시(`comments.insert`, 50 unit, `youtube.force-ssl` 필요)는 구현하지 않았습니다.
- 확인 못 한 것: "검토 대기(heldForReview)" 댓글을 읽으려면 `moderationStatus` 파라미터와 더 넓은 스코프가 필요할 수 있습니다. v1은 게시된 댓글만 읽습니다.
- Gmail과 같은 프로젝트를 "테스트" 상태로 두면 YouTube 토큰도 7일 만료 규칙을 따릅니다.

## 3. Instagram 댓글

코드는 완성돼 있지만(`adapters/instagram.py`, 가짜 HTTP로 테스트) 실제 계정으로는 확인하지 못했습니다.

**전제 조건**
- Instagram 계정이 **프로페셔널 계정(비즈니스 또는 크리에이터)** 이어야 합니다. 개인 계정은 공식 API 접근이 없습니다. 앱 설정 → 계정 유형 전환(무료).
- Facebook 페이지 연결은 **필요 없습니다**(Instagram 로그인 방식 사용).

**단계**
1. [Meta for Developers](https://developers.facebook.com/)에서 앱 생성 → 제품 **"Instagram" → "Instagram 로그인을 통한 API 설정"** 추가.
2. 권한: `instagram_business_basic`, `instagram_business_manage_comments`. 본인 계정만 쓰는 동안은 앱 심사 없이 **Standard Access**로 충분합니다(앱의 역할에 본인 Instagram 계정을 테스터로 추가).
3. 앱 대시보드의 "액세스 토큰 생성"에서 본인 계정으로 로그인 → 토큰 발급. 단기 토큰(1시간)이면 장기 토큰(60일)으로 교환:
   `GET https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=<앱 시크릿>&access_token=<단기 토큰>`
4. 장기 토큰을 환경변수로: `set IG_ACCESS_TOKEN=...` (파일로 저장하지 마세요).
5. `python -m reply_copilot run --channel instagram --dry-run`, 괜찮으면 `--stage` → 승인 대기열.
6. **60일 안에 갱신**: `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<장기 토큰>` (발급 24시간 이후부터 가능). v1에는 자동 갱신이 없습니다.

- 읽는 것: `GET /me`, `GET /me/media`(최근 게시물 5개), `GET /{media-id}/comments`. 모두 GET.
- API 버전은 `IG_API_VERSION`(기본 `v25.0`, 확인 필요).
- 비용: 무료. 호출 한도는 시간당 약 200회 수준으로 알려져 있어 게시물 5개 × 1시간 1회 폴링이면 충분합니다.
- 답글 게시(`/{comment-id}/replies`)는 구현하지 않았습니다.

## 4. 나중에 / 안 함

- **X(Twitter)**: API가 유료(읽기 포함)라 v1에서 제외. 어댑터 파일 하나로 추가 가능.
- **네이버 블로그**: 댓글 API가 없어 제외.
