from fastapi import FastAPI, Request, Header, HTTPException
from datetime import datetime
import threading
import hmac
import hashlib
import subprocess
import os
import re
from typing import Dict, Optional
from enum import Enum

app = FastAPI()

# Build status tracking
class BuildStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# In-memory build tracking (use Redis/DB in production)
build_jobs: Dict[str, Dict] = {}

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


@app.get("/build/{build_id}")
async def get_build_status(build_id: str):
    """Get the current status and logs of a build"""
    if build_id not in build_jobs:
        raise HTTPException(status_code=404, detail="Build not found")
    
    job = build_jobs[build_id]
    
    # Check if processes are still running
    setup_running = job.get('setup_process') and job['setup_process'].poll() is None
    android_running = job.get('android_process') and job['android_process'].poll() is None
    ios_running = job.get('ios_process') and job['ios_process'].poll() is None
    
    # Update status based on process states
    if setup_running or android_running or ios_running:
        job['status'] = BuildStatus.RUNNING.value
    elif job['status'] == BuildStatus.RUNNING.value:
        # All processes finished, check return codes
        setup_code = job.get('setup_process', {}).returncode if job.get('setup_process') else 0
        android_code = job.get('android_process', {}).returncode if job.get('android_process') else 0
        ios_code = job.get('ios_process', {}).returncode if job.get('ios_process') else 0
        
        if any(code != 0 for code in [setup_code, android_code, ios_code] if code is not None):
            job['status'] = BuildStatus.FAILED.value
        else:
            job['status'] = BuildStatus.COMPLETED.value
    
    return {
        "build_id": build_id,
        "status": job['status'],
        "started_at": job['started_at'],
        "flavor": job['flavor'],
        "platform": job['platform'],
        "processes": {
            "setup": {
                "running": setup_running,
                "return_code": job.get('setup_process', {}).returncode if job.get('setup_process') else None
            },
            "android": {
                "running": android_running,
                "return_code": job.get('android_process', {}).returncode if job.get('android_process') else None
            } if job['platform'] in ['all', 'android'] else None,
            "ios": {
                "running": ios_running,
                "return_code": job.get('ios_process', {}).returncode if job.get('ios_process') else None
            } if job['platform'] in ['all', 'ios'] else None
        },
        "progress": job.get('progress', {}),
        "logs": job.get('logs', [])
    }


@app.get("/builds")
async def list_builds():
    """List all builds with their current status"""
    builds = []
    for build_id, job in build_jobs.items():
        # Quick status check
        setup_running = job.get('setup_process') and job['setup_process'].poll() is None
        android_running = job.get('android_process') and job['android_process'].poll() is None
        ios_running = job.get('ios_process') and job['ios_process'].poll() is None
        
        status = BuildStatus.RUNNING.value if (setup_running or android_running or ios_running) else job['status']
        
        builds.append({
            "build_id": build_id,
            "status": status,
            "started_at": job['started_at'],
            "flavor": job['flavor'],
            "platform": job['platform']
        })
    
    return {"builds": builds}


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
            build_id = start_build_pipeline("dev", "all")
            return {"status": "ok", "build_id": build_id}

    elif (
        x_github_event == "create" and
        payload.get("ref_type") == "tag"
    ):
        tag_name = payload.get("ref", "")
        print(f"✅ Tag created: {tag_name}")

        if re.match(r"\d+\.\d+\.\d+", tag_name):
            print(f"✅ Valid tag format: {tag_name}")
            build_id = start_build_pipeline("prod", "all")
            return {"status": "ok", "build_id": build_id}

    return {"status": "ok"}


@app.post("/build")
async def manual_build(request: Request):
    body = await request.json()
    flavor = body.get("flavor", "dev")
    platform = body.get("platform", "all")
    build_name = body.get("build_name", None)
    build_number = body.get("build_number", None)
    
    build_id = start_build_pipeline(flavor, platform, build_name, build_number)
    return {"status": "manual trigger ok", "build_id": build_id}


def start_build_pipeline(
    flavor: str,
    platform: str,
    build_name: str = None,
    build_number: str = None,
) -> str:
    """Start a build pipeline and return build ID for tracking"""
    now = datetime.now()
    build_id = f"{flavor}-{platform}-{now.strftime('%Y%m%d-%H%M%S')}"
    
    # Initialize build job tracking
    build_jobs[build_id] = {
        "build_id": build_id,
        "status": BuildStatus.PENDING.value,
        "started_at": now.isoformat(),
        "flavor": flavor,
        "platform": platform,
        "build_name": build_name,
        "build_number": build_number,
        "logs": []
    }
    
    # Start build in background thread
    threading.Thread(
        target=build_pipeline_with_monitoring, 
        args=(build_id, flavor, platform, build_name, build_number)
    ).start()
    
    return build_id


def build_pipeline_with_monitoring(
    build_id: str,
    flavor: str,
    platform: str,
    build_name: str,
    build_number: str,
):
    """Enhanced build pipeline with progress monitoring"""
    job = build_jobs[build_id]
    job['status'] = BuildStatus.RUNNING.value
    
    try:
        print(f"🛠️ [{flavor}] Build {build_id} started")
        job['logs'].append(f"🛠️ [{flavor}] Build started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Step 1: Setup
        print(f"📦 [{build_id}] Running setup...")
        job['logs'].append("📦 Running setup...")
        
        setup_process = subprocess.Popen(
            ["bash", f"action/{flavor}/0_setup.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        job['setup_process'] = setup_process
        
        # Capture setup output in real-time
        for line in setup_process.stdout:
            line = line.strip()
            if line:
                job['logs'].append(f"[SETUP] {line}")
                print(f"[{build_id}][SETUP] {line}")
        
        setup_process.wait()
        if setup_process.returncode != 0:
            job['status'] = BuildStatus.FAILED.value
            job['logs'].append(f"❌ Setup failed with code {setup_process.returncode}")
            return

        # Step 2: Build based on platform
        android_build_args = ["bash", f"action/{flavor}/1_android.sh"]
        ios_build_args = ["bash", f"action/{flavor}/1_ios.sh"]

        if build_name:
            android_build_args.append(f"-n {build_name}")
            ios_build_args.append(f"-n {build_name}")

        if build_number:
            android_build_args.append(f"-b {build_number}")
            ios_build_args.append(f"-b {build_number}")

        processes = []

        if platform in ["all", "android"]:
            print(f"🤖 [{build_id}] Starting Android build...")
            job['logs'].append("🤖 Starting Android build...")
            
            android_process = subprocess.Popen(
                android_build_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            job['android_process'] = android_process
            processes.append(('android', android_process))

        if platform in ["all", "ios"]:
            print(f"🍎 [{build_id}] Starting iOS build...")
            job['logs'].append("🍎 Starting iOS build...")
            
            ios_process = subprocess.Popen(
                ios_build_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            job['ios_process'] = ios_process
            processes.append(('ios', ios_process))

        # Monitor all build processes
        for platform_name, process in processes:
            threading.Thread(
                target=monitor_process_output,
                args=(build_id, platform_name, process)
            ).start()

        # Wait for all processes to complete
        for platform_name, process in processes:
            process.wait()
            if process.returncode != 0:
                job['logs'].append(f"❌ {platform_name.title()} build failed with code {process.returncode}")
            else:
                job['logs'].append(f"✅ {platform_name.title()} build completed successfully")

        # Final status update will be handled by get_build_status endpoint
        print(f"🎉 [{build_id}] Build pipeline completed")
        job['logs'].append(f"🎉 Build pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        job['status'] = BuildStatus.FAILED.value
        job['logs'].append(f"💥 Build pipeline failed: {str(e)}")
        print(f"💥 [{build_id}] Build pipeline failed: {str(e)}")


def monitor_process_output(build_id: str, platform_name: str, process: subprocess.Popen):
    """Monitor a subprocess output in real-time with structured progress parsing"""
    job = build_jobs[build_id]
    
    # Initialize progress tracking for this platform
    if 'progress' not in job:
        job['progress'] = {}
    job['progress'][platform_name] = {
        'current_step': 'starting',
        'percentage': 0,
        'steps_completed': [],
        'current_message': 'Starting build...'
    }
    
    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                # Parse structured progress lines
                if line.startswith("PROGRESS:"):
                    # Format: PROGRESS:step:message:percentage%
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        step = parts[1]
                        message = parts[2]
                        percent_str = parts[3].replace('%', '')
                        try:
                            percentage = int(percent_str)
                            job['progress'][platform_name].update({
                                'current_step': step,
                                'percentage': percentage,
                                'current_message': message
                            })
                            log_entry = f"[{platform_name.upper()}] 📊 {message} ({percentage}%)"
                        except ValueError:
                            log_entry = f"[{platform_name.upper()}] {line}"
                    else:
                        log_entry = f"[{platform_name.upper()}] {line}"
                        
                elif line.startswith("STEP:"):
                    # Format: STEP:step:status:message
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        step = parts[1]
                        status = parts[2]
                        message = parts[3]
                        
                        step_info = {
                            'step': step,
                            'status': status,
                            'message': message,
                            'timestamp': datetime.now().isoformat()
                        }
                        job['progress'][platform_name]['steps_completed'].append(step_info)
                        
                        status_emoji = "✅" if status == "SUCCESS" else "❌"
                        log_entry = f"[{platform_name.upper()}] {status_emoji} {message}"
                    else:
                        log_entry = f"[{platform_name.upper()}] {line}"
                else:
                    # Regular log line
                    log_entry = f"[{platform_name.upper()}] {line}"
                
                job['logs'].append(log_entry)
                print(f"[{build_id}]{log_entry}")
                
                # Keep log size manageable (last 500 lines)
                if len(job['logs']) > 500:
                    job['logs'] = job['logs'][-400:]  # Keep last 400 lines
                    
    except Exception as e:
        job['logs'].append(f"[{platform_name.upper()}] Error monitoring output: {str(e)}")
