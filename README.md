# Muse Relay

내 컴퓨터·VM에서 실행되는 Muse로 문장을 전달하는 서비스입니다. 사용자마다 전용 웹 전송 페이지와 API 주소를 만들고, 공개 수신을 켜면 송신자는 키 없이 자연어만 보낼 수 있습니다.

[운영 서비스](https://vm-https-check-production.up.railway.app/) · [API 문서](https://vm-https-check-production.up.railway.app/api-docs) · [사용 안내](docs/USER-GUIDE.md)

## 사용하기

1. 서비스에서 계정을 만들고 Muse를 등록합니다.
2. 관리 화면의 연결 프로그램을 내려받고, Muse가 실행되는 기기에서 관리 화면에 표시된 `python3 muse_agent.py connect --server 서버주소` 명령을 실행합니다.
3. 웹에서 생성한 10분 일회용 코드와 실행 중인 localhost 수신기의 URL을 입력합니다.
4. `python3 muse_agent.py run`으로 폴링을 시작합니다.
5. Muse 전용 페이지를 공유하거나 ‘Codex·외부 프로그램용 사용법 복사’를 사용합니다.

수신 프로그램이 별도로 실행돼 있어야 합니다. HTTP 수신 URL 예: `http://127.0.0.1:18765/inbox`. localhost 인증이 필요하면 connect에 `--local-auth`를 추가합니다. 기기 연결키는 자동 발급되어 로컬 설정 파일에 저장됩니다.

## 외부 API

관리 화면에서 자신의 실제 API 주소를 복사하세요.

```http
POST /api/muses/{muse_id}/send
Content-Type: text/plain; charset=utf-8

작업 결과를 정리해서 알려줘.
```

공개 수신이면 인증키·로그인·JSON·직접 정하는 ID가 필요 없습니다. 서버가 ID를 만들고 `{"message":"문장"}`으로 감쌉니다. HTTP 201은 서버 접수 확인이며, 기기 수신이나 작업 실행 완료를 뜻하지 않습니다. 외부 웹사이트도 호출할 수 있습니다.

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

`PUBLIC_SEND`는 기존 단일 VM의 `/send` 공개 여부입니다. 새 Muse의 공개 여부는 Muse별 설정으로 관리합니다. 서버 토큰 두 개는 기존 API용이며, 새 사용자나 송신자에게 공유하지 않습니다.

## 테스트와 배포

```sh
python3 -m unittest discover -s tests -v
node --check static/muse.js
node --check static/app.js
```

GitHub Actions가 Python 3.10·3.13 테스트, JavaScript 구문 검사와 Docker 이미지 기동을 확인합니다. CI는 임시 데이터와 테스트용 키만 사용합니다.

- [Railway 배포 안내](docs/DEPLOYMENT.md)
- [구조와 데이터 보관](docs/ARCHITECTURE.md)
- [테스트 범위](TESTING.md)
- [변경 기록](CHANGELOG.md)

## 현재 범위

계정당 Muse 3개, Muse당 기기 1대, 문장 16KiB, 분당 60건, 미전달 1,000개입니다. 소유자만 내역을 조회하고 공개 수신·기기 연결을 관리할 수 있습니다. 외부 수신 포트를 열 필요가 없으며 기기가 HTTPS로 폴링합니다.

초기 베타에는 비밀번호 복구, 이메일 인증, 결제, 팀 권한이 없습니다. 수신기는 메시지 ID로 중복 처리를 방지해야 합니다.

기존 VM의 `/send`, `/messages`, `/claim` API는 유지됩니다. 기존 전송 화면은 [/legacy](https://vm-https-check-production.up.railway.app/legacy)입니다.
