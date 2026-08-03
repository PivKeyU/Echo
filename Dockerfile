FROM python:3.10-slim

ENV TZ=Asia/Shanghai \
    DOCKER_MODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    WORKDIR=/app

WORKDIR ${WORKDIR}

# 安装构建依赖和运行时依赖，确保镜像在 amd64 / arm64 上都能正常构建。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        docker-compose \
        docker.io \
        git \
        libffi-dev \
        libjpeg-dev \
        libpq-dev \
        postgresql-client \
        libssl-dev \
        pkg-config \
        tzdata \
        zlib1g-dev \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo Asia/Shanghai > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY . ./

# 清理调试产物和本地配置，避免把不该进入镜像的文件一起打包。
RUN python3 scripts/install_runtime_plugin_dependencies.py \
    && rm -rf ./image __pycache__ \
    && rm -f ./config.json ./data/config.json \
    && mkdir -p ./data \
    && find . -type d -name "__pycache__" -prune -exec rm -rf {} +

ENTRYPOINT ["python3"]
CMD ["main.py"]
