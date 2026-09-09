FROM python:3.12-slim

WORKDIR /app

# 先拷依赖清单并安装（利用 Docker 层缓存，改代码不用重装依赖）
# 使用阿里云 pip 镜像，加速国内服务器构建
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 再拷贝项目代码
COPY . .

EXPOSE 8900

# 端口用环境变量 PORT，默认 8900：
# - 阿里云 docker-compose 不设 PORT，容器监听 8900
# - 万一以后 Render 改用 Docker 部署，Render 会注入 $PORT，也能正常监听
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8900}"]
