# Forex Data API

FastAPI service untuk mengambil data forex multi-timeframe menggunakan ForexConnect. API ini dapat digunakan untuk mengambil data historis dari berbagai instrumen forex dengan parameter yang dapat disesuaikan.

## 🚀 Features

- ✅ Multi-timeframe data (Daily, H1, M15)
- ✅ Dynamic parameters (username, password, instrument, dll)
- ✅ RESTful API dengan FastAPI
- ✅ Docker support
- ✅ Health check endpoint
- ✅ Error handling yang proper
- ✅ Compatible dengan n8n automation

## 📋 Requirements

- Python 3.7
- Docker (untuk deployment)
- Akun ForexConnect yang valid

## 🛠️ Installation

### Local Development

1. Clone repository:
```bash
git clone <your-repo-url>
cd forex-api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run aplikasi:
```bash
python main.py
```

API akan berjalan di `http://localhost:9898`

### Docker Deployment

1. Build image:
```bash
docker build -t forex-api .
```

2. Run container:
```bash
docker run -p 9898:9898 forex-api
```

### EasyPanel Deployment

1. Upload code ke GitHub/GitLab
2. Login ke EasyPanel dashboard
3. Create new service → From Source Code
4. Connect repository
5. Set port ke `9898`
6. Deploy

## 📖 API Documentation

### Base URL
```
https://your-service-url:9898
```

### Endpoints

#### 1. Get Forex Data
**POST** `/get-forex-data`

Mengambil data forex multi-timeframe dengan parameter yang dapat disesuaikan.

**Request Body:**
```json
{
  "username": "your_username",
  "password": "your_password",
  "url": "http://www.fxcorporate.com/Hosts.jsp",
  "connection": "Real",
  "instrument": "GBP/USD",
  "candles_d1": 60,
  "candles_h1": 1200,
  "candles_m15": 300
}
```

**Parameters:**
- `username` (string, required): Username ForexConnect
- `password` (string, required): Password ForexConnect
- `url` (string, optional): Server URL (default: fxcorporate.com)
- `connection` (string, optional): "Real" atau "Demo" (default: "Real")
- `instrument` (string, optional): Pair forex (default: "GBP/USD")
- `candles_d1` (int, optional): Jumlah candle daily (default: 60)
- `candles_h1` (int, optional): Jumlah candle hourly (default: 1200)
- `candles_m15` (int, optional): Jumlah candle 15-menit (default: 300)

**Response Success:**
```json
{
  "status": "success",
  "data": {
    "instrument": "GBP/USD",
    "timestamp": "2025-08-04T10:30:00",
    "daily": [
      {
        "time": "2025-08-04 00:00:00",
        "open": 1.27234,
        "high": 1.27456,
        "low": 1.27123,
        "close": 1.27345
      }
    ],
    "H1": [...],
    "M15": [...]
  }
}
```

**Response Error:**
```json
{
  "detail": "Failed to fetch forex data: connection error"
}
```

#### 2. Health Check
**GET** `/health`

Endpoint untuk monitoring status aplikasi.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-08-04T10:30:00"
}
```

#### 3. Root Endpoint
**GET** `/`

Informasi dasar tentang API.

**Response:**
```json
{
  "message": "Forex Data API is running",
  "endpoints": ["/get-forex-data"]
}
```

## 🔧 Usage Examples

### cURL
```bash
curl -X POST "https://your-service-url:9898/get-forex-data" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password",
    "instrument": "EUR/USD",
    "candles_d1": 30
  }'
```

### Python Requests
```python
import requests

url = "https://your-service-url:9898/get-forex-data"
data = {
    "username": "your_username",
    "password": "your_password",
    "instrument": "GBP/USD",
    "candles_d1": 60
}

response = requests.post(url, json=data)
result = response.json()
print(result)
```

### n8n Integration

1. **Add HTTP Request Node** di n8n workflow
2. **Configuration:**
   - Method: `POST`
   - URL: `https://your-service-url:9898/get-forex-data`
   - Headers: `Content-Type: application/json`
   - Body: JSON dengan parameter yang diperlukan

3. **Example n8n Body:**
```json
{
  "username": "{{ $json.username }}",
  "password": "{{ $json.password }}",
  "instrument": "{{ $json.instrument || 'GBP/USD' }}",
  "candles_d1": "{{ $json.candles_d1 || 60 }}"
}
```

## 🎯 Supported Instruments

API ini mendukung semua instrumen yang tersedia di ForexConnect, contoh:
- `EUR/USD`
- `GBP/USD`
- `USD/JPY`
- `AUD/USD`
- `USD/CHF`
- `NZD/USD`
- `USD/CAD`
- Dan lainnya sesuai broker

## 🎯 Supported Timeframes

- `D1` - Daily
- `H1` - 1 Hour
- `m15` - 15 Minutes

## ⚠️ Important Notes

1. **Security:** Jangan hardcode credentials di code. Gunakan environment variables atau secure storage.
2. **Rate Limiting:** ForexConnect mungkin memiliki rate limits, gunakan dengan bijak.
3. **Connection:** Pastikan koneksi internet stabil untuk akses ke server ForexConnect.
4. **Error Handling:** API akan return HTTP 500 jika terjadi error pada ForexConnect.

## 🐛 Troubleshooting

### Common Issues

1. **Login Failed**
   - Periksa username/password
   - Pastikan akun aktif
   - Cek koneksi internet

2. **Connection Error**
   - Periksa URL server
   - Pastikan firewall tidak memblokir

3. **Instrument Not Found**
   - Pastikan spelling instrument benar
   - Cek apakah instrument tersedia di broker

### Logs
Check container logs untuk debugging:
```bash
docker logs <container-name>
```

## 📝 Development

### Project Structure
```
forex-api/
├── main.py          # FastAPI application
├── Dockerfile       # Docker configuration
├── requirements.txt # Python dependencies
└── README.md        # Documentation
```

### Adding New Features

1. Fork repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

## 📄 License

MIT License - feel free to use and modify as needed.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For issues and questions:
1. Check troubleshooting section
2. Review logs
3. Create issue in repository