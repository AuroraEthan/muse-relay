# 구조

송신자 → Railway HTTPS → Muse별 영구 큐 → 연결 기기의 폴링 프로그램 → localhost 수신기

- server.py: HTTP 서버, 기존 단일 VM API와 정적 파일.
- muse_api.py: 계정·소유자·기기·Muse별 API 라우팅.
- muse_store.py: scrypt 비밀번호, 해시된 세션·연결 코드·기기키, 소유권, 사용량 제한.
- queue_store.py: SQLite 트랜잭션으로 저장·임시 점유·완료 처리.
- muse_agent.py: 일회용 코드 교환과 연결 설정, 기기 실행.
- vm_agent.py: 폴링, HTTP/TCP localhost 전달, 전달 이력.
- runtime.py: 리다이렉트 제한과 URL 검증 등 공유 도구.
- static/muse.*: 가입·등록·관리·공개 전송 화면.

## 저장소

DB_PATH가 /data/queue.db일 때 계정·세션·Muse 레지스트리와 기존 메시지는 queue.db의 별도 테이블에 저장됩니다. 신규 Muse 큐는 /data/queue-muses/m_<uuid>.db로 분리됩니다. 경로는 서버가 생성한 ID만 사용합니다. 백업할 때 레지스트리와 큐 디렉터리를 함께 포함해야 합니다.

## 전달 의미

메시지는 120초 점유됩니다. 기기가 localhost의 성공 응답을 받은 후 서버에 ack합니다. 네트워크 응답 유실 시 재전달될 수 있으므로 수신기에서도 ID로 중복을 방지해야 합니다. acked는 localhost의 응답을 확인했다는 의미이며 Muse 작업 실행 완료를 보장하지 않습니다.

## 접근 범위

공개 Muse의 /send만 무인증·외부 CORS를 허용합니다. 비공개 Muse는 같은 Origin의 소유자 세션으로 전송합니다. 내역과 설정은 소유자에게만 허용됩니다. 기기키는 해당 Muse의 claim·ack만 허용됩니다. 연결 코드는10분 안에 한 번만 교환되며 새 기기 연결은 이전 키를 대체합니다.

소유자 세션은30일 HttpOnly·SameSite=Strict이며 HTTPS에서 Secure를 적용합니다. 완료 기록은30일 후 큐 접근 시 정리하고 유휴 큐도 매시간 정리합니다. 미전달 데이터는 보관합니다. SQLite 삭제는 파일의 물리적 크기를 즉시 줄이지 않으며 페이지를 재사용합니다.

현재 서버는 단일 프로세스·단일 replica를 전제로 합니다. 다중 서버나 대규모 사용자 운영에는 저장소와 작업 처리 구조를 별도로 설계해야 합니다.
