FROM debian:bullseye-slim

# 1. 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip git bash wget ca-certificates \
    ruby ruby-dev build-essential liblzma-dev libsqlite3-dev \
    libreadline-dev zlib1g-dev openssh-client gnupg2 \
    pkg-config openssl python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 2. Flutter SDK 설치
ENV FLUTTER_VERSION=${FLUTTER_VERSION}
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="${FLUTTER_HOME}/bin:${PATH}"

RUN git clone https://github.com/flutter/flutter.git ${FLUTTER_HOME} \
    && cd ${FLUTTER_HOME} \
    && git checkout "refs/tags/${FLUTTER_VERSION}" \
    && flutter doctor

# 3. Fastlane 설치
RUN gem install fastlane -NV

# 4. 작업 디렉토리 설정
WORKDIR /workspace

# 4-1. 필수 디렉토리 생성
RUN mkdir -p /workspace/action /workspace/src /workspace/log

# 5. Python 패키지 설치
COPY requirements.txt ./
RUN pip3 install --upgrade pip && pip3 install -r requirements.txt

# 6. 필요한 파일 복사
COPY main.py .
COPY action/ ./action/
COPY src/ ./src/
COPY entrypoint.sh .

# 7. entrypoint 실행
ENTRYPOINT ["bash", "./entrypoint.sh"]
