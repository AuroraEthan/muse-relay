# 검증

Python3.10 이상, 추가 패키지 없이 unittest를 실행합니다.

```sh
python3 -m unittest discover -s tests -v
node --check static/muse.js
node --check static/app.js
```

51개 테스트가 실제 임시 SQLite와 로컬 HTTP/TCP 서버로 기존 VM 전달·재시도·점유·재시작, 공개 텍스트 송신, 계정·세션·Origin 검증, 소유자·기기 격리, 코드 만료·경합, 기기 교체·폐기, 보관 기간, 잘못된 Unicode, 연결 프로그램의 localhost 전달을 검증합니다. 테스트는 운영 서비스에 메시지를 보내지 않습니다.

GitHub Actions는 Linux에서 Python3.10·3.13을 검증합니다. Docker 빌드 후 실제 컨테이너를 기동해 홈페이지·health·Muse 다운로드·관리 인증과 비밀 파일 비공개를 확인합니다. macOS에서는 로컬 테스트와 브라우저 가입→등록→기기연결→송신→전달완료 흐름을 확인했습니다. Windows는 CI 검증 범위에 포함하지 않습니다.
