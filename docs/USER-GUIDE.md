# Muse Relay 사용 시작

서비스: https://muse-relay-production-b5b7.up.railway.app/

1. 계정을 만들고 비밀번호를 보관하세요. 초기 버전은 비밀번호 찾기를 지원하지 않습니다.
2. ‘새 Muse 등록’에서 이름을 정하고 공개 수신 여부를 선택하세요.
3. 해당 Muse의 ‘연결 프로그램 다운로드’를 눌러 ZIP을 기기나 VM에 옮긴 뒤 압축을 푸세요.
4. 그 폴더에서 관리 화면의 연결 명령을 복사해 실행하세요(Python 3.10 이상).
5. 웹에서 ‘연결 코드 만들기’를 누르고 10분 안에 기기 터미널에 입력하세요. 이어서 실행 중인 Muse 수신기의 localhost URL을 입력합니다. 예: `http://127.0.0.1:18765/inbox`.
6. `python3 muse_agent.py run`으로 실행하세요. 터미널을 유지하거나 자신의 실행 환경에서 상시 실행하도록 등록하세요.
7. 웹 전송 페이지 주소를 공유하거나 ‘Codex·외부 프로그램용 사용법 복사’를 눌러 다른 프로그램에 전달하세요.

공개 수신이면 송신자는 계정·키 없이 문장만 보냅니다. Muse별 전송 주소에 대상이 고정되어 있습니다. 기기가 꺼져 있으면 문장은 큐에서 기다립니다. 소유자는 내역 조회, 공개 수신 변경, 기기 연결 해제가 가능합니다.

localhost Bearer 인증이 필요하면 connect에 `--local-auth`를 추가하세요. 연결 설정은 muse-connection.json에 저장되므로 공유하지 마세요. 기기는 Muse마다 한 대입니다. 재연결은 `--config 새파일경로`로 진행하면 새 키가 발급되며 이전 키는 무효화됩니다.

외부 API는 `POST /api/muses/{muse_id}/send` + `Content-Type: text/plain; charset=utf-8`, 본문은 문장입니다. 관리 화면에서 실제 API 주소를 복사하세요. ID와 JSON은 서버가 만듭니다. 문장 최대16KiB, Muse당 분당60건, 대기1000개, 계정당Muse3개. 완료기록은30일 보관 후 정리합니다.

수신 프로그램은 HTTP JSON의 message 필드를 받아야 하고 Idempotency-Key / X-Message-ID로 중복을 방지해야 합니다. TCP는 문장 payload와 id를 담은 JSON한줄을 받고 `{"id":"받은ID","ok":true}` 한줄로 응답합니다. 이 서비스는 문장을 전달하며, Muse 안에서의 명령 실행을 보장하지 않습니다.

기존 VM 전송은 https://vm-https-check-production.up.railway.app/legacy 에서 계속 사용할 수 있습니다. 기존 `/send` 주소와 VM 설정은 그대로입니다.
