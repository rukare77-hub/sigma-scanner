# 시그마 스캐너

금, 미국 주식·ETF, 암호화폐, 부동산(리츠·주택 ETF), 채권·환율·해외 ETF 60개의 **일일 종가**를 받아 평균에서 몇 σ(시그마) 벗어났는지 보여주는 웹사이트입니다.

- **Z-score 탭**: 자산 하나의 종가가 자기 평균에서 몇 σ 떨어졌는지
- **상대가치 비율 탭**: 두 자산의 가격비(A÷B)가 자기 평균에서 몇 σ 떨어졌는지 (금÷주식, 비트코인÷금 등 15개 기본 제공, 화면에서 직접 추가 가능)
- 이탈 기준 1σ / 1.5σ / 2σ, 기준 기간 20·60·120·252일, 로그·단순 가격을 화면에서 바로 바꿉니다.
- 행을 누르면 종가·평균·±1σ·±1.5σ 밴드 차트와 Z 추이가 나옵니다.

구조: 매일 한 번 GitHub가 `scripts/fetch_data.py`를 돌려 `data/data.json`을 갱신하고, `index.html`이 그 파일을 읽어 계산·표시합니다. 서버 비용과 설치가 없습니다.

---

## 처음 한 번만 하는 설정 (약 10분)

### 1. GitHub 계정과 저장소 만들기
1. https://github.com 에서 가입합니다.
2. 오른쪽 위 **+ → New repository**. 이름은 `sigma-scanner`, 공개 범위는 **Public**(무료 Pages는 Public 저장소에서 쓸 수 있습니다), **Create repository**.

### 2. 파일 올리기
1. 받은 zip을 PC에서 풉니다.
2. 만든 저장소 화면에서 **uploading an existing file** 링크(또는 **Add file → Upload files**)를 누릅니다.
3. 풀어낸 폴더 안의 **모든 파일과 폴더**(`index.html`, `config.json`, `data`, `scripts`, `.github`, `README.md`)를 끌어다 놓습니다.
   - `.github` 폴더가 안 보이면 윈도우는 탐색기 **보기 → 표시 → 숨긴 항목**, 맥은 Finder에서 `Cmd + Shift + .` 을 누르세요.
   - 그래도 안 올라가면 **Add file → Create new file**에서 파일 이름 칸에 `.github/workflows/update-data.yml` 이라고 입력하고, zip 안의 같은 이름 파일 내용을 붙여넣으면 됩니다.
4. 맨 아래 **Commit changes**.

### 3. 웹사이트 공개 켜기
**Settings → Pages → Build and deployment**에서 Source를 **Deploy from a branch**, Branch를 **main / (root)** 로 두고 **Save**. 1~2분 뒤 같은 화면 위쪽에 주소(`https://내아이디.github.io/sigma-scanner/`)가 나옵니다.

### 4. 시세 수집을 처음 한 번 실행하기
**Actions** 탭 → 왼쪽 **데이터 업데이트** → **Run workflow** → 초록 버튼. 1~3분 뒤 초록 체크가 뜨면 `data/data.json`이 생기고, 사이트의 노란 "가상 데모 데이터" 띠가 사라지며 실제 종가가 보입니다.

이후에는 **매일 한국시간 오전 9시 30분경** 자동으로 갱신됩니다(미국 정규장 마감과 암호화폐 UTC 일봉 마감 이후).

> 주소를 폴더에서 `index.html`을 더블클릭해 열면 브라우저 보안 때문에 시세 파일을 못 읽습니다. 반드시 위 GitHub Pages 주소로 여세요.

---

## 자산·비율 바꾸기

`config.json`을 GitHub 화면에서 연필 아이콘으로 수정합니다.

- 자산 추가: `assets` 안의 한 줄을 복사해 `symbol`(Yahoo Finance 티커), `name`, `category`를 바꿉니다. 예: `{"symbol": "005930.KS", "name": "삼성전자", "category": "한국 개별주"}`
- 비율 추가: `pairs`에 `{"id": "원하는이름", "a": "분자 티커", "b": "분모 티커", "name": "표시 이름"}`을 넣습니다. `a`, `b`는 `assets`에 있는 티커여야 합니다.
- 쉼표와 따옴표를 빠뜨리지 않게 주의하세요. 저장 후 Actions에서 **Run workflow**를 한 번 실행하면 반영됩니다.

화면에서 만든 "직접 비율"은 그 브라우저에만 저장됩니다.

## 데이터 출처와 한계

| 출처 | 비용 | 용도 |
|---|---|---|
| Yahoo Finance 차트 주소 | 무료, 키 없음 | 기본 출처. 주식·ETF·금·환율·암호화폐 모두 |
| Binance 공개 시세 | 무료, 키 없음 | 암호화폐 보조(야후 실패 시) |
| Twelve Data | 키 필요(무료 요금제 있음, 유료로 확장) | 보조. 키가 있을 때만 사용 |

- Yahoo 주소는 공식 계약이 있는 API가 아니라서 예고 없이 바뀌거나 막힐 수 있습니다. 그럴 때를 대비해 Twelve Data를 연결해 둘 수 있습니다: Twelve Data에서 키를 받고, 저장소 **Settings → Secrets and variables → Actions → New repository secret**에 이름 `TWELVEDATA_API_KEY`, 값에 키를 넣습니다. 무료 요금제는 호출 제한이 작아 보조용으로 적합합니다.
- 수집에 실패한 자산은 직전 값을 유지하고, 사이트 맨 아래에 실패 목록이 표시됩니다. 전부 실패하면 기존 파일을 건드리지 않고 Actions가 빨간 표시로 알려줍니다.
- **부동산**: 아파트·주택 가격지수는 월간·분기 통계라 일일 종가가 없습니다. 이 사이트는 일일 종가가 있는 상장 리츠, 주택건설 ETF를 부동산 대용치로 씁니다.
- 종가는 분할만 보정하고 배당은 반영하지 않습니다. 확정되지 않은 당일 봉은 버립니다.
- σ 이탈은 "평균에서 얼마나 멀리 있나"를 재는 값입니다. 되돌림을 보장하지 않으며, 추세가 강하면 이탈이 몇 주씩 이어집니다. 투자 판단의 근거 하나로만 쓰세요.

## 파일 구성

```
index.html                         화면과 계산 (브라우저에서 실행)
config.json                        자산·비율 목록 (직접 수정)
scripts/fetch_data.py              종가 수집 스크립트
.github/workflows/update-data.yml  매일 자동 실행 설정
data/data.json                     수집 결과 (자동 생성)
data/demo.json                     실제 데이터가 생기기 전까지 보여주는 가상 데이터
```
