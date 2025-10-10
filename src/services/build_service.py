"""
Flutter CI/CD Server - Build Service

빌드 파이프라인 관리 서비스
"""
import os
import re
import subprocess
import threading
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

from ..core.config import get_build_workspace, get_isolated_env
from ..core.queue_manager import queue_manager


class BuildStatus(Enum):
    """빌드 상태 열거형"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BuildLogger:
    """Thread-safe build log file writer"""
    
    def __init__(self, build_id: str):
        self.build_id = build_id
        self.log_file_path = get_build_workspace(build_id) / "build.log"
        self._lock = threading.Lock()
        
        # Ensure directory exists
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize log file with build start info
        with self._lock:
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                f.write(f"=== Build Log for {build_id} ===\n")
                f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
    
    def log(self, message: str):
        """Thread-safe log message write"""
        with self._lock:
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    f.write(f"{message}\n")
                    f.flush()  # Ensure immediate write
            except Exception as e:
                print(f"Error writing to log file {self.log_file_path}: {e}")
    
    def get_log_path(self) -> str:
        """Get the log file path"""
        return str(self.log_file_path)


class BuildService:
    """빌드 서비스 클래스"""
    
    def __init__(self):
        self.build_jobs: Dict[str, Dict] = {}
        self.build_loggers: Dict[str, BuildLogger] = {}
    
    def start_build_pipeline(
        self,
        flavor: str,
        platform: str,
        build_name: str = None,
        build_number: str = None,
        branch_name: str = None,
        fvm_flavor: str = None,
    ) -> str:
        """Start a build pipeline and return build ID for tracking"""
        now = datetime.now()
        build_id = f"{flavor}-{platform}-{now.strftime('%Y%m%d-%H%M%S')}"
        
        # 브랜치명 결정 (환경변수 폴백)
        if not branch_name:
            env_key = f"{flavor.upper()}_BRANCH_NAME"
            branch_name = os.environ.get(env_key, "develop")
        
        # 큐 키 생성
        queue_key = queue_manager.get_queue_key(branch_name, fvm_flavor, flavor)
        
        # Initialize build job tracking
        self.build_jobs[build_id] = {
            "build_id": build_id,
            "status": BuildStatus.PENDING.value,
            "started_at": now.isoformat(),
            "flavor": flavor,
            "platform": platform,
            "build_name": build_name,
            "build_number": build_number,
            "branch_name": branch_name,
            "fvm_flavor": fvm_flavor,
            "queue_key": queue_key,
            "logs": []
        }
        
        # Initialize build logger
        self.build_loggers[build_id] = BuildLogger(build_id)
        
        # Start build in background thread with queue management
        threading.Thread(
            target=lambda: queue_manager.execute_with_queue(
                queue_key,
                build_id,
                self._build_pipeline_with_monitoring,
                build_id, flavor, platform, build_name, build_number, branch_name, fvm_flavor
            )
        ).start()
        
        return build_id
    
    def _build_pipeline_with_monitoring(
        self,
        build_id: str,
        flavor: str,
        platform: str,
        build_name: str,
        build_number: str,
        branch_name: str,
        fvm_flavor: str,
    ):
        """Enhanced build pipeline with complete environment isolation"""
        job = self.build_jobs[build_id]
        job['status'] = BuildStatus.RUNNING.value
        
        try:
            print(f"[{build_id}] 🛠️ [{flavor}] Build started in isolated environment")
            self._log_to_build_file(build_id, f"[{build_id}] 🛠️ [{flavor}] Build started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # FVM flavor 매핑 로드 (캐시 전략에 필요)
            flutter_version = None
            cocoapods_version = None
            fastlane_version = None
            gradle_version = None
            
            if fvm_flavor:
                try:
                    import json
                    mapping_path = os.path.join(os.getcwd(), 'fvm_flavors.json')
                    with open(mapping_path, 'r') as f:
                        flavor_map = json.load(f)
                    if fvm_flavor in flavor_map:
                        flutter_version = flavor_map[fvm_flavor].get('flutter_version')
                        cocoapods_version = flavor_map[fvm_flavor].get('cocoapods_version')
                        fastlane_version = flavor_map[fvm_flavor].get('fastlane_version')
                        gradle_version = flavor_map[fvm_flavor].get('gradle_version')  # 선택적
                        self._log_to_build_file(build_id, f"[{build_id}] 🔧 FVM flavor '{fvm_flavor}' loaded:")
                        if flutter_version:
                            self._log_to_build_file(build_id, f"[{build_id}]    - Flutter: {flutter_version}")
                        if cocoapods_version:
                            self._log_to_build_file(build_id, f"[{build_id}]    - CocoaPods: {cocoapods_version}")
                        if fastlane_version:
                            self._log_to_build_file(build_id, f"[{build_id}]    - Fastlane: {fastlane_version}")
                        if gradle_version:
                            self._log_to_build_file(build_id, f"[{build_id}]    - Gradle: {gradle_version}")
                    else:
                        self._log_to_build_file(build_id, f"[{build_id}] ⚠️ fvm_flavor '{fvm_flavor}' not found. Using defaults.")
                except Exception as e:
                    self._log_to_build_file(build_id, f"[{build_id}] ⚠️ Failed to load fvm_flavors.json: {str(e)}")
            
            # ✅ 완전히 격리된 환경 생성 (버전별 공유 캐시 사용)
            isolated = get_isolated_env(
                build_id, 
                flutter_version=flutter_version,
                gradle_version=gradle_version,
                cocoapods_version=cocoapods_version
            )
            env = isolated["env"]
            repo_dir = isolated["repo_dir"]
            
            self._log_to_build_file(build_id, f"[{build_id}] 📂 Workspace: {get_build_workspace(build_id)}")
            self._log_to_build_file(build_id, f"[{build_id}] 🔒 PUB_CACHE: {isolated['pub_cache_dir']}")
            self._log_to_build_file(build_id, f"[{build_id}] 🔧 GRADLE_HOME: {isolated['gradle_home_dir']}")
            self._log_to_build_file(build_id, f"[{build_id}] 💎 GEM_HOME: {isolated['gem_home_dir']}")
            self._log_to_build_file(build_id, f"[{build_id}] 🍫 CP_HOME_DIR: {isolated['cocoapods_cache_dir']}")
            
            # 환경변수에 버전 정보 추가
            if flutter_version:
                env['FLUTTER_VERSION'] = flutter_version
            if cocoapods_version:
                env['COCOAPODS_VERSION'] = cocoapods_version
            if fastlane_version:
                env['FASTLANE_VERSION'] = fastlane_version
            if gradle_version:
                env['GRADLE_VERSION'] = gradle_version
            
            # 환경변수 설정 (격리된 스크립트용)
            env["REPO_URL"] = os.environ.get("REPO_URL", "")
            env["LOCAL_DIR"] = repo_dir
            env["BRANCH_NAME"] = branch_name
            env["FLAVOR"] = flavor
            
            if fvm_flavor:
                env['FVM_FLAVOR'] = fvm_flavor
            
            # Fastlane 레인 설정 (필요시)
            env["FASTLANE_LANE"] = os.environ.get(f"{flavor.upper()}_FASTLANE_LANE", "beta")
            
            # Fastlane Match 비밀번호 전달
            match_password = os.environ.get("MATCH_PASSWORD")
            if match_password:
                env["MATCH_PASSWORD"] = match_password
                self._log_to_build_file(build_id, f"[{build_id}] 🔑 MATCH_PASSWORD configured {env['MATCH_PASSWORD']}")
            else:
                self._log_to_build_file(build_id, f"[{build_id}] ⚠️ MATCH_PASSWORD not set in environment")
                self._log_to_build_file(build_id, f"[{build_id}] 🔍 Available env vars: {', '.join([k for k in os.environ.keys() if 'MATCH' in k or 'FASTLANE' in k])}")
            
            self._log_to_build_file(build_id, f"[{build_id}] 🌿 Branch: {branch_name}")
            print(f"[{build_id}] 🌿 Branch: {branch_name}, Queue: {job.get('queue_key')}")

            # Step 1: Setup (격리된 스크립트 사용)
            print(f"📦 [{build_id}] Running setup in isolated environment...")
            self._log_to_build_file(build_id, f"[{build_id}] 📦 Running setup...")
            
            setup_script = "action/0_setup.sh"
            
            setup_process = subprocess.Popen(
                ["bash", setup_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                cwd=os.getcwd()
            )
            job['setup_process'] = setup_process
            
            # Capture setup output in real-time
            for line in setup_process.stdout:
                line = line.strip()
                if line:
                    self._log_to_build_file(build_id, f"[{build_id}][SETUP] {line}")
                    print(f"[{build_id}][SETUP] {line}")
            
            setup_process.wait()
            if setup_process.returncode != 0:
                job['status'] = BuildStatus.FAILED.value
                self._log_to_build_file(build_id, f"[{build_id}] ❌ Setup failed with code {setup_process.returncode}")
                return

            # Step 2: Build based on platform
            android_script = "action/1_android.sh"
            ios_script = "action/1_ios.sh"
            
            android_build_args = ["bash", android_script]
            ios_build_args = ["bash", ios_script]

            if build_name:
                android_build_args.extend(["-n", build_name])
                ios_build_args.extend(["-n", build_name])

            if build_number:
                android_build_args.extend(["-b", build_number])
                ios_build_args.extend(["-b", build_number])

            processes = []

            if platform in ["all", "android"]:
                print(f"🤖 [{build_id}] Starting Android build...")
                self._log_to_build_file(build_id, f"[{build_id}] 🤖 Starting Android build...")
                
                android_process = subprocess.Popen(
                    android_build_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=os.getcwd()
                )
                job['android_process'] = android_process
                processes.append(('android', android_process))

            if platform in ["all", "ios"]:
                print(f"🍎 [{build_id}] Starting iOS build...")
                self._log_to_build_file(build_id, f"[{build_id}] 🍎 Starting iOS build...")
                
                ios_process = subprocess.Popen(
                    ios_build_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=os.getcwd()
                )
                job['ios_process'] = ios_process
                processes.append(('ios', ios_process))

            # Monitor all build processes
            for platform_name, process in processes:
                threading.Thread(
                    target=self._monitor_process_output,
                    args=(build_id, platform_name, process)
                ).start()

            # Wait for all processes to complete
            for platform_name, process in processes:
                process.wait()
                if process.returncode != 0:
                    self._log_to_build_file(build_id, f"[{build_id}] ❌ {platform_name.title()} build failed with code {process.returncode}")
                else:
                    self._log_to_build_file(build_id, f"[{build_id}] ✅ {platform_name.title()} build completed successfully")

            print(f"🎉 [{build_id}] Build pipeline completed")
            self._log_to_build_file(build_id, f"[{build_id}] 🎉 Build pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            job['status'] = BuildStatus.FAILED.value
            self._log_to_build_file(build_id, f"[{build_id}] 💥 Build pipeline failed: {str(e)}")
            print(f"💥 [{build_id}] Build pipeline failed: {str(e)}")
    
    def _log_to_build_file(self, build_id: str, message: str):
        """Log message to both memory and file"""
        # Add to memory logs
        if build_id in self.build_jobs:
            self.build_jobs[build_id]['logs'].append(message)
        
        # Add to file logs
        if build_id in self.build_loggers:
            self.build_loggers[build_id].log(message)
        else:
            # Create logger if it doesn't exist
            self.build_loggers[build_id] = BuildLogger(build_id)
            self.build_loggers[build_id].log(message)
    
    def _monitor_process_output(self, build_id: str, platform_name: str, process: subprocess.Popen):
        """Monitor a subprocess output in real-time with structured progress parsing"""
        job = self.build_jobs[build_id]
        
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
                                log_entry = f"[{build_id}][{platform_name.upper()}] 📊 {message} ({percentage}%)"
                            except ValueError:
                                log_entry = f"[{build_id}][{platform_name.upper()}] {line}"
                        else:
                            log_entry = f"[{build_id}][{platform_name.upper()}] {line}"
                            
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
                            log_entry = f"[{build_id}][{platform_name.upper()}] {status_emoji} {message}"
                        else:
                            log_entry = f"[{build_id}][{platform_name.upper()}] {line}"
                    else:
                        # Regular log line
                        log_entry = f"[{build_id}][{platform_name.upper()}] {line}"
                    
                    self._log_to_build_file(build_id, log_entry)
                    print(f"{log_entry}")
                    
                    # Keep log size manageable (last 500 lines)
                    if len(job['logs']) > 500:
                        job['logs'] = job['logs'][-400:]  # Keep last 400 lines
                        
        except Exception as e:
            self._log_to_build_file(build_id, f"[{platform_name.upper()}] Error monitoring output: {str(e)}")
    
    def get_build_status(self, build_id: str) -> Optional[Dict]:
        """Get build status by build_id"""
        if build_id not in self.build_jobs:
            return None
        
        job = self.build_jobs[build_id]
        
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
        
        # Get log file path if logger exists
        log_file_path = None
        if build_id in self.build_loggers:
            log_file_path = self.build_loggers[build_id].get_log_path()
        
        return {
            "build_id": build_id,
            "status": job['status'],
            "started_at": job['started_at'],
            "flavor": job['flavor'],
            "platform": job['platform'],
            "fvm_flavor": job.get('fvm_flavor'),
            "branch_name": job.get('branch_name'),
            "build_name": job.get('build_name'),
            "build_number": job.get('build_number'),
            "queue_key": job.get('queue_key'),
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
            "logs": job.get('logs', []),
            "log_file_path": log_file_path
        }
    
    def list_builds(self) -> [Dict]:
        """List all builds"""
        builds = []
        for build_id, job in self.build_jobs.items():
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
                "platform": job['platform'],
                "fvm_flavor": job.get('fvm_flavor'),
                "branch_name": job.get('branch_name'),
                "build_name": job.get('build_name'),
                "build_number": job.get('build_number'),
                "queue_key": job.get('queue_key')
            })
        
        return builds


# 전역 인스턴스
build_service = BuildService()
