FROM python:3.11-slim

# Cài đặt các gói hệ thống cần thiết cho newspaper3k
RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# Copy và cài đặt dependencies (Làm trước để tận dụng cache của Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tải dữ liệu ngôn ngữ (Phải chạy sau khi cài requirements)
RUN python -m nltk.downloader punkt

# COPY TOÀN BỘ PROJECT VÀO CONTAINER
COPY . .

# Chạy đúng đường dẫn cấu trúc thư mục
# CMD ["python", "src/crawler/crawler.py"]