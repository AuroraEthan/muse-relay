# Railway 배포

현재 운영 서비스는 기존 Railway에 배포되어 있습니다. 이 GitHub 저장소를 만드는 작업은 운영 데이터나 기존 VM 연결을 변경하지 않습니다.

## 필수 설정

- Dockerfile 빌드를 사용합니다(railway.toml 포함).
- 영구 볼륨을 /data에 연결합니다.
- replica는1개로 유지합니다.
- 아래 환경변수를 설정합니다. 실제 키는 저장소에 커밋하지 않습니다.

| 변수 | 값 |
| --- | --- |
| PRODUCER_TOKEN | 기존 API 관리용으로 생성한 긴 무작위 키 |
| CONSUMER_TOKEN | 위와 서로 다른 긴 무작위 키 |
| DB_PATH | /data/queue.db |
| PUBLIC_ORIGIN | 실제 HTTPS 서비스 origin, 끝에 슬래시 없음 |
| PUBLIC_SEND | 기존 /send를 공개하려면 true, 인증하려면 false |
| PORT | Railway가 제공하는 포트 |

새 Muse의 공개 수신은 PUBLIC_SEND와 별개로 각 Muse에서 정합니다. 계정·기기 연결키는 서비스가 자동으로 처리합니다. 사용자 가입·로그인·소유자 변경은 PUBLIC_ORIGIN과 일치하는 Origin을 요구하므로 도메인이 바뀌면 함께 변경하세요. 기본 기기 CLI는 운영 주소를 사용하므로 다른 인스턴스는 connect의 --server에 자신의 HTTPS origin을 지정하세요.

## 소스 배포

원하는 기존 Railway 서비스에 이 저장소의 main 브랜치를 소스로 연결하거나, 저장소 루트에서 Railway CLI로 명시적인 프로젝트·서비스·환경을 지정해 배포합니다.

```sh
railway up --project YOUR_PROJECT_ID --service YOUR_SERVICE_ID --environment YOUR_ENVIRONMENT_ID
```

GitHub Actions는 검증 전용이며 Railway 토큰을 저장하지 않습니다. GitHub 소스 연결과 자동 배포 여부는 Railway 서비스 설정에서 확인하세요.

## 배포 확인과 데이터

GET /health가200인지, /openapi.json이2.0 API인지, /downloads/muse-agent.zip을 받을 수 있는지 확인합니다. 새 테스트 Muse로 연결·전송·localhost 수신·ack까지 확인하세요. 기존 VM에 임의 테스트 메시지를 보내지 마세요.

백업에는 /data/queue.db와 /data/queue-muses 전체를 같은 시점의 일관된 스냅샷으로 보관합니다. WAL 사용 중인 DB 파일을 단독 복사하면 최신 내용이 누락될 수 있으므로 SQLite 백업 또는 서비스 중지 상태의 볼륨 스냅샷을 사용하세요. 최초 다중 Muse 배포는 기존 테이블을 삭제하지 않고 레지스트리 테이블을 추가합니다.
