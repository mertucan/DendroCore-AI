"""
DendroVox - Doğanın Sesi

Geliştirme sunucusunu başlatır:  python app.py
Uygulama kodu dendrovox/ paketindedir.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from dendrovox import create_app  # noqa: E402  (ortam değişkenleri önce yüklenmeli)

app = create_app()

if __name__ == '__main__':
    # Debug modu yalnızca .env içinde FLASK_DEBUG=1 ise açılır; ağdan erişim için HOST=0.0.0.0 verilebilir.
    app.run(debug=app.config['DEBUG'], host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', 5000)))
