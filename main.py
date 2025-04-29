from fastapi import FastAPI, Request, Header, HTTPException
from datetime import datetime
import threading
import hmac
import hashlib
import subprocess
import os
import re

app = FastAPI()

# GitHub Webhook Secret은 환경변수에서 반드시 직접 지정해야 함
GITHUB_SECRET_ENV = os.environ.get("GITHUB_WEBHOOK_SECRET")
if not GITHUB_SECRET_ENV:
    raise RuntimeError("환경변수 GITHUB_WEBHOOK_SECRET이 설정되지 않았습니다.")
GITHUB_SECRET = GITHUB_SECRET_ENV.encode()


def verify_signature(payload: bytes, signature: str) -> bool:
    sha_name, signature = signature.split('=')
    if sha_name != 'sha256':
        return False
    mac = hmac.new(GITHUB_SECRET, msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)


@app.get("/")
async def root():
    return {"message": "👋 Flutter CI/CD Container is running!"}


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None)
):
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()

    if (
        x_github_event == "pull_request" and
        payload.get("action") == "closed" and
        payload.get("pull_request", {}).get("merged")
    ):
        if (payload.get("pull_request", {}).get("base", {}).get("ref") == "develop" and
                payload.get("pull_request", {}).get("head", {}).get("ref").startswith("release-dev-v")):
            print("✅ PR merged to develop! Running CI/CD...")
            threading.Thread(target=build_pipeline, args=("dev",)).start()

    elif (
        x_github_event == "create" and
        payload.get("ref_type") == "tag"
    ):
        tag_name = payload.get("ref", "")
        print(f"✅ Tag created: {tag_name}")

        if re.match(r"\d+\.\d+\.\d+", tag_name):
            print(f"✅ Valid tag format: {tag_name}")
            threading.Thread(target=build_pipeline, args=("prod",)).start()

    return {"status": "ok"}


@app.post("/build")
async def manual_build(request: Request):
    body = await request.json()
    flavor = body.get("flavor", "dev")
    threading.Thread(target=build_pipeline, args=(flavor,)).start()
    return {"status": "manual trigger ok"}


def build_pipeline(flavor: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🛠️ [{flavor}] Build started at {now}")

    subprocess.run(["bash", f"action/{flavor}/0_setup.sh"], check=True)
    subprocess.Popen(["bash", f"action/{flavor}/1_android.sh"])
    subprocess.Popen(["bash", f"action/{flavor}/1_ios.sh"])
