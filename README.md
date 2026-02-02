# scrap_os_browser_info

운영체제와 브라우저의 최신 버전(정식/베타) 정보를 수집하는 간단한 수집기입니다. Wikipedia 및 공식 업데이트 API를 조합해 최신 버전/버전 코드/출시일을 JSON으로 출력합니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용법

```bash
python collect_info.py -o data.json
```

출력은 다음과 같은 구조입니다.

```json
{
  "generated_at": "2025-01-01T00:00:00Z",
  "operating_systems": {
    "windows": {
      "stable": {
        "version": "23H2",
        "version_code": "23H2",
        "release_date": "2023-10-31",
        "source": "https://en.wikipedia.org/wiki/Windows_11"
      },
      "beta": {
        "version": "24H2",
        "version_code": "24H2",
        "release_date": "2024-09-24",
        "source": "https://en.wikipedia.org/wiki/Windows_11"
      }
    }
  },
  "browsers": {
    "chrome": {
      "stable": {
        "version": "123.0.6312.58",
        "version_code": "123",
        "release_date": "2024-03-19",
        "source": "https://chromiumdash.appspot.com/fetch_milestones"
      }
    }
  }
}
```

## 데이터 소스 참고

* Chrome: Chromium Dash milestone API
* Firefox: Mozilla product-details API
* Edge: Microsoft Edge Update API
* Opera: Opera FTP 디렉터리 목록
* Safari/Whale 및 주요 운영체제: Wikipedia infobox

Wikipedia infobox 키가 바뀌면 `collect_info.py`의 매핑을 업데이트해야 합니다.
