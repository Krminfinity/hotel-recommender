# Hotel Recommender API

ユーザーが駅名・上限価格・日付を入力すると、楽天トラベルから最適なホテルを2〜3件推薦するMVPアプリケーションです。

## セットアップ

### 1. 仮想環境の作成と有効化

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. 依存関係のインストール

```powershell
pip install -U pip
pip install -e ".[dev]"
```

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、必要なAPIキーを設定してください：

**Windows:**
```powershell
copy .env.example .env
```

**Linux/Mac:**
```bash
cp .env.example .env
```

**必要なAPIキー:**

1. **Google Places API キー**
   - [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成
   - Places API を有効化
   - 認証情報でAPIキーを作成
   - `.env` の `GOOGLE_PLACES_API_KEY` に設定

2. **楽天トラベルAPI キー**
   - [楽天デベロッパー](https://webservice.rakuten.co.jp/) でアカウント作成
   - アプリケーションIDを取得
   - アフィリエイトIDを取得（収益化用）
   - `.env` の `RAKUTEN_APPLICATION_ID` と `RAKUTEN_AFFILIATE_ID` に設定

### 4. サーバーの起動

```powershell
uvicorn api.main:app --reload
```

```

## フロントエンド利用方法

### Webインターフェース

1. **サーバー起動**
```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

2. **ブラウザアクセス**
   - http://127.0.0.1:8000 にアクセス

3. **使用方法**
   - 駅名を入力（例：新宿駅、渋谷駅）
   - 予算上限を設定（円）
   - 日付または曜日を選択（オプション）
   - 「ホテルを検索」ボタンをクリック

### フロントエンドテスト

```powershell
# 基本テスト実行
python -m pytest tests/test_frontend.py -v

# フロントエンドテストランナー
python test_frontend.py
```

## API利用方法

### エンドポイント

- `GET /` - フロントエンドWebページ
- `GET /health` - ヘルスチェック
- `POST /api/suggest` - ホテル推薦API

### API使用例

### Health Check

```bash
GET http://localhost:8000/health
```

### Hotel Recommendation

```bash
POST http://localhost:8000/api/suggest
Content-Type: application/json

{
  "stations": ["新宿", "品川"],
  "price_max": 12000,
  "date": "2025-10-03"
}
```

## 開発ツール

### Lint & Format

```powershell
# Lint
ruff check .

# Format
black .

# Fix auto-fixable issues
ruff check --fix .
```

### テスト実行

```powershell
pytest
```

## プロジェクト構成

```
hotel-recommender/
├─ api/
│   ├─ main.py              # FastAPI アプリケーション
│   ├─ schemas.py           # Pydantic モデル
│   ├─ cache.py            # キャッシュ機能
│   ├─ services/
│   │   ├─ resolver.py      # 曜日→日付変換、データ整形
│   │   ├─ ranking.py       # ホテルランキングロジック
│   │   └─ distance.py      # 距離計算（Haversine）
│   └─ providers/
│       ├─ station_base.py  # 駅情報取得の基底クラス
│       ├─ station_google.py # Google Places API
│       ├─ hotel_base.py    # ホテル情報取得の基底クラス
│       └─ hotel_rakuten.py # 楽天トラベル API
├─ static/
│   ├─ index.html          # フロントエンドメインページ
│   ├─ css/
│   │   └─ style.css       # スタイルシート
│   └─ js/
│       └─ app.js          # フロントエンドロジック
├─ tests/                  # テストケース
├─ test_frontend.py       # フロントエンドテストランナー
├─ .env.example           # 環境変数テンプレート
└─ README.md              # このファイル
```

## 技術仕様

- **Backend**: Python 3.11+, FastAPI
- **External APIs**: Google Places API, 楽天トラベル WebService
- **Cache**: メモリベースTTLキャッシュ（駅=24h、ホテル=15m）
- **Development**: ruff, black, pytest

## ライセンス

MIT License