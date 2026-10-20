# Muse Relay

웹·Codex·API에서 받은 문장을 Muse의 클라우드 VM 내부 localhost 수신기로 전달하는 서비스입니다. 여기서 Muse는 Meta AI를 뜻합니다. 연결 프로그램은 Muse의 클라우드 VM 안에서 실행합니다. VM 내부 수신기와 Meta AI가 수신함을 읽고 처리하는 절차는 별도로 구성합니다. 사용자마다 Muse를 등록하고 Muse별 송신 API 키를 발급합니다. 공통 API가 키로 대상 Muse를 찾아 자연어를 전달합니다. 공개 수신은 지원하지 않습니다.

[운영 서비스](https://muse-relay-production-b5b7.up.railway.app/) · [API 문서](https://muse-relay-production-b5b7.up.railway.app/api-docs) · [사용 안내](docs/USER-GUIDE.md)

## 사용하기

1. 서비스에서 계정을 만들고 Muse를 등록합니다.
2. **‘연결 프롬프트 만들고 복사’**를 누릅니다. 선택한 Muse의 서버 주소·프로그램 주소·10분 일회용 코드와 수행할 작업이 자동으로 담깁니다.
3. **Muse 대화에 그대로 붙여넣습니다.** Muse가 자신의 클라우드 환경을 확인하고 다운로드·수신함 준비·연결·실행·결과 보고를 진행하도록 요청합니다. 사용자가 VM 터미널 명령이나 JSON을 작성할 필요는 없습니다.
4. Muse가 준비됐다고 알려주면 웹의 ‘테스트 문장 보내기’를 누르고 해당 메시지의 수신기 ACK를 확인합니다.
5. ‘송신 API 키 발급’을 누르고 ‘Codex·외부 프로그램용 사용법 복사 (키 포함)’를 사용합니다.

프롬프트의 일회용 코드는 연결할 Muse에게만 전달하세요. 장기 기기키·비밀번호는 포함하지 않습니다. 유효한 프롬프트는 다시 복사할 수 있고, 만료·사용 후에는 새로 만듭니다. 다른 Muse를 선택한 동안 끝난 요청은 자동 복사하지 않습니다. 자동 복사가 차단되면 ‘프롬프트 내용 보기 · 직접 복사’를 사용하세요.

Muse가 터미널/Python/네트워크/백그라운드 실행을 사용할 수 있는지 실제로 확인하도록 안내합니다. 도구 사용이나 지속 실행을 지원하지 않는 환경은 Muse가 제약을 보고해야 합니다. 수신기 ACK와 Muse의 실제 읽기·작업 결과는 별도입니다. 직접 설치할 사용자는 관리 화면의 ‘직접 설정하기 · 고급 안내’를 참고하세요.

## 외부 API

관리 화면에서 송신 API 키를 발급하고 공통 API 주소와 사용법을 복사하세요. 키 원문은 발급 직후에만 표시하며 서버는 해시만 저장합니다. 새로고침·Muse 선택 변경 후에는 원문을 다시 조회할 수 없습니다.

```http
POST /api/send
Authorization: Bearer 발급받은송신키
Content-Type: text/plain; charset=utf-8

작업 결과를 정리해서 알려줘.
```

송신 키는 한 Muse의 전송만 허용합니다. JSON·Muse ID·직접 정하는 메시지 ID는 필요 없습니다. 키 누락·오류·교체·폐기는 401입니다. 키는 신뢰하는 실행 환경의 비밀 설정에 보관하고 URL·공개 코드·로그에는 넣지 마세요. 소유자는 키를 교체·폐기할 수 있으며 기기 연결과 큐에는 영향이 없습니다. 서버가 ID를 만들고 `{"message":"문장"}`으로 감쌉니다. HTTP 201은 서버 접수 확인입니다. 서버 접수, localhost 수신기 ACK, Meta AI의 읽기·실행을 각각 구분해야 합니다. 외부 웹사이트도 호출할 수 있습니다.

같은 요청을 재시도할 때는 선택적인 `Idempotency-Key`를 생성해 재사용하세요. 새 요청에 같은 문장을 보내면 별도 메시지로 저장됩니다. 완료 기록과 재시도키는 30일 후 정리됩니다.

## 로컬 서버 실행

Python 3.10 이상과 표준 라이브러리만 사용합니다. 추가 Python 패키지가 필요 없습니다.

```sh
export PRODUCER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export CONSUMER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PORT=8080
export DB_PATH=./data/queue.db
export PUBLIC_ORIGIN=http://127.0.0.1:8080
export PUBLIC_SEND=false
python3 server.py
```

브라우저에서 `http://127.0.0.1:8080`을 엽니다. 로컬 인스턴스에 기기를 연결할 때는 `python3 muse_agent.py connect --server http://127.0.0.1:8080`을 사용하세요. 웹의 연결 명령과 다운로드 안내는 접속한 서버 주소를 포함합니다.

`PUBLIC_SEND`는 더 이상 익명 전송을 활성화하지 않습니다. 기존 공개 플래그는 비활성화되며 Muse별 send는 같은 Origin의 소유자 웹 세션만 허용합니다. 서버 토큰 두 개는 기존 API용이며, 새 사용자나 송신자에게 공유하지 않습니다.

## 테스트와 배포

```sh
python3 -m unittest discover -s tests -v
node --check static/muse-test.js
node --test tests/test_onboarding.cjs
node --check static/muse.js
node --check static/app.js
```

GitHub Actions가 Python 3.10·3.13 테스트, JavaScript 구문 검사와 Docker 이미지 기동을 확인합니다. CI는 임시 데이터와 테스트용 키만 사용합니다.

- [Railway 배포 안내](docs/DEPLOYMENT.md)
- [구조와 데이터 보관](docs/ARCHITECTURE.md)
- [테스트 범위](TESTING.md)
- [변경 기록](CHANGELOG.md)

## 현재 범위

계정당 Muse 3개, Muse당 기기 1대, 문장 16KiB, 분당 60건, 미전달 1,000개입니다. 소유자만 내역을 조회하고 송신 키·기기 연결을 관리할 수 있습니다. 외부 수신 포트를 열 필요가 없으며 기기가 HTTPS로 폴링합니다.

초기 베타에는 비밀번호 복구, 이메일 인증, 결제, 팀 권한이 없습니다. 수신기는 메시지 ID로 중복 처리를 방지해야 합니다.

기존 VM의 `/send`, `/messages`, `/claim` API는 유지됩니다. 기존 전송 화면은 [/legacy](https://vm-https-check-production.up.railway.app/legacy)입니다.

## VM 재시작 후 자동 복구와 알림

연결 프롬프트는 파일이 유지되는 VM에서 Muse가 다음을 직접 구성하고 검증하도록 요청합니다.

- 영구 저장 경로에 프로그램·비밀 설정·수신함·메시지 ID별 처리 기록과 재개 지침 보관
- 환경이 지원하는 부팅 시 자동 시작과 프로세스 감독으로 수신기·중계기·Muse의 수신함 확인 및 처리 재개, 중복 실행 방지
- 유효한 기기키 재사용, 일시 오류 재시도, 서버에 대기 중인 문장과 수신함의 미완료 작업 재개
- 완료된 작업 중복 처리 방지, 중단된 외부 작업의 성공 여부 확인 후 재개
- 정상 재시작·재연결·복구는 로그에만 기록. 최초 설정·테스트와 요청한 작업 결과는 보고하고, 복구 알림은 사용자 조치가 필요한 지속 장애·인증 실패·처리 정체만 중복 없이 보고

이는 Muse에게 전달하는 설정 요청입니다. 실제 자동 시작과 AI 처리 재개는 Muse 환경에서 검증해야 하며 웹의 수신기 ACK만으로 확인할 수 없습니다. 사용자 요청 없이 VM을 재부팅하지 않고, 실제 재부팅으로 검증하지 못한 부분은 구분하도록 요청합니다. 기기키가 폐기된 경우에는 새 연결이 필요합니다. 송신 API 키 교체는 기기 재연결을 요구하지 않습니다.
