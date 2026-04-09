# Claude Usage Monitor

> **Windows 전용** (Windows 10 / 11)

Claude.ai 구독 사용량을 화면에 항상 표시하는 플로팅 오버레이 앱.

## 표시 정보

| 항목 | 설명 |
|---|---|
| **5h 세션** | 현재 세션 사용률 (%) + 리셋까지 남은 시간 |
| **7일** | 주간 사용률 (%) |
| **Sonnet** | 7일 Sonnet 모델 사용률 (%) |
| **Extra** | 추가 크레딧 사용량 |

사용률에 따라 색상 변경: 초록(~60%) → 노랑(~85%) → 빨강(85%+)

## 요구 사항

- Windows 10 / 11
- Python 3.8 이상

## 설치

```bash
pip install requests
```

> `tkinter`는 Python for Windows 기본 포함.

## 설정

`claude_monitor.py` 상단의 두 값을 채운다.

```python
SESSION_KEY = "sk-ant-sid01-XXXXXXXX..."   # 브라우저 쿠키
ORG_ID      = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # 아래 참고
```

### SESSION_KEY 찾는 법

1. 브라우저에서 `claude.ai` 접속
2. **F12** → **Application** 탭
3. 좌측 **Cookies** → `https://claude.ai`
4. `sessionKey` 항목의 Value 복사

> 세션 만료 또는 로그아웃 시 재추출 필요.

### ORG_ID 찾는 법

1. `claude.ai` 접속 후 **F12** → **Network** 탭
2. **Fetch/XHR** 필터 → **F5** 새로고침
3. 요청 URL 중 `/api/organizations/xxxxxxxx-.../` 형태에서 UUID 복사

## 실행

```bash
python claude_monitor.py
```

화면 우측 하단에 플로팅 창이 표시된다.

## 조작

| 동작 | 기능 |
|---|---|
| 드래그 | 창 위치 이동 |
| 우클릭 | 새로고침 / 종료 메뉴 |

자동 갱신: API 60초, 카운트다운 1분마다 업데이트.

## 시작 프로그램 등록 (선택)

Windows 시작 시 자동 실행하려면:

1. `start_claude_monitor.bat` 파일 생성:
    ```bat
    @echo off
    pythonw "C:\경로\claude_monitor.py"
    ```
2. `Win + R` → `shell:startup` 입력
3. 위 `.bat` 파일을 해당 폴더에 복사
