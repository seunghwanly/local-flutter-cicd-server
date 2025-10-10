"""
Flutter CI/CD Server - Build Service

빌드 파이프라인 관리 서비스
"""
import os
import subprocess
import threading
import logging
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

from ..core.config import get_build_workspace, get_isolated_env
from ..core.queue_manager import queue_manager

logger = logging.getLogger(__name__)

# 상수 정의
MAX_LOG_LINES = 500
KEEP_LOG_LINES = 400
QUEUE_LOCK_TIMEOUT = 3600  # 1시간 (초)


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
            except (IOError, OSError) as e:
                logger.error(f"Failed to write to log file {self.log_file_path}: {e}")
                print(f"Error writing to log file {self.log_file_path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error writing to log file {self.log_file_path}: {e}")
                print(f"Unexpected error writing to log file {self.log_file_path}: {e}")
    
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
    
    def _load_fvm_flavor_mapping(self, build_id: str, fvm_flavor: str) -> Dict[str, str]:
        """FVM flavor 매핑을 로드합니다."""
        versions = {
            'flutter_version': None,
            'cocoapods_version': None,
            'fastlane_version': None,
            'gradle_version': None
        }
        
        if not fvm_flavor:
            return versions
            
        try:
            import json
            mapping_path = os.path.join(os.getcwd(), 'fvm_flavors.json')
            with open(mapping_path, 'r') as f:
                flavor_map = json.load(f)
                
            if fvm_flavor in flavor_map:
                versions['flutter_version'] = flavor_map[fvm_flavor].get('flutter_version')
                versions['cocoapods_version'] = flavor_map[fvm_flavor].get('cocoapods_version')
                versions['fastlane_version'] = flavor_map[fvm_flavor].get('fastlane_version')
                versions['gradle_version'] = flavor_map[fvm_flavor].get('gradle_version')
                
                self._log_to_build_file(build_id, f"[{build_id}] 🔧 FVM flavor '{fvm_flavor}' loaded:")
                for key, value in versions.items():
                    if value:
                        self._log_to_build_file(build_id, f"[{build_id}]    - {key.replace('_', ' ').title()}: {value}")
            else:
                self._log_to_build_file(build_id, f"[{build_id}] ⚠️ fvm_flavor '{fvm_flavor}' not found. Using defaults.")
                
        except Exception as e:
            self._log_to_build_file(build_id, f"[{build_id}] ⚠️ Failed to load fvm_flavors.json: {str(e)}")
            
        return versions

    def _setup_build_environment(self, build_id: str, flavor: str, branch_name: str, fvm_flavor: str, versions: Dict[str, str]) -> Dict:
        """빌드 환경을 설정합니다."""
        # 격리된 환경 생성
        isolated = get_isolated_env(
            build_id, 
            flutter_version=versions['flutter_version'],
            gradle_version=versions['gradle_version'],
            cocoapods_version=versions['cocoapods_version']
        )
        env = isolated["env"]
        
        # 환경 정보 로깅
        self._log_to_build_file(build_id, f"[{build_id}] 📂 Workspace: {get_build_workspace(build_id)}")
        self._log_to_build_file(build_id, f"[{build_id}] 🔒 PUB_CACHE: {isolated['pub_cache_dir']}")
        self._log_to_build_file(build_id, f"[{build_id}] 🔧 GRADLE_HOME: {isolated['gradle_home_dir']}")
        self._log_to_build_file(build_id, f"[{build_id}] 💎 GEM_HOME: {isolated['gem_home_dir']}")
        self._log_to_build_file(build_id, f"[{build_id}] 🍫 CP_HOME_DIR: {isolated['cocoapods_cache_dir']}")
        
        # 버전 정보 환경변수 설정
        for key, value in versions.items():
            if value:
                env[key.upper()] = value
        
        # 기본 환경변수 설정
        env.update({
            "REPO_URL": os.environ.get("REPO_URL", ""),
            "LOCAL_DIR": isolated["repo_dir"],
            "BRANCH_NAME": branch_name,
            "FLAVOR": flavor,
            "FASTLANE_LANE": os.environ.get(f"{flavor.upper()}_FASTLANE_LANE", "beta")
        })
        
        if fvm_flavor:
            env['FVM_FLAVOR'] = fvm_flavor
        
        # Fastlane Match 비밀번호 설정
        match_password = os.environ.get("MATCH_PASSWORD")
        if match_password:
            env["MATCH_PASSWORD"] = match_password
            self._log_to_build_file(build_id, f"[{build_id}] 🔑 MATCH_PASSWORD configured")
        else:
            self._log_to_build_file(build_id, f"[{build_id}] ⚠️ MATCH_PASSWORD not set in environment")
            available_vars = [k for k in os.environ.keys() if 'MATCH' in k or 'FASTLANE' in k]
            if available_vars:
                self._log_to_build_file(build_id, f"[{build_id}] 🔍 Available env vars: {', '.join(available_vars)}")
        
        return isolated

    def _run_setup_script(self, build_id: str, env: Dict) -> bool:
        """Setup 스크립트를 실행합니다."""
        print(f"📦 [{build_id}] Running setup in isolated environment...")
        self._log_to_build_file(build_id, f"[{build_id}] 📦 Running setup...")
        
        setup_script = "action/0_setup.sh"
        job = self.build_jobs[build_id]
        
        try:
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
            
            # 실시간 출력 캡처
            for line in setup_process.stdout:
                line = line.strip()
                if line:
                    self._log_to_build_file(build_id, f"[{build_id}][SETUP] {line}")
                    print(f"[{build_id}][SETUP] {line}")
            
            setup_process.wait()
            if setup_process.returncode != 0:
                job['status'] = BuildStatus.FAILED.value
                self._log_to_build_file(build_id, f"[{build_id}] ❌ Setup failed with code {setup_process.returncode}")
                return False
                
            return True
            
        except Exception as e:
            job['status'] = BuildStatus.FAILED.value
            self._log_to_build_file(build_id, f"[{build_id}] ❌ Setup script execution failed: {str(e)}")
            logger.error(f"Setup script execution failed for {build_id}: {e}")
            return False

    def _run_build_scripts(self, build_id: str, platform: str, build_name: str, build_number: str, env: Dict) -> bool:
        """빌드 스크립트들을 실행합니다."""
        job = self.build_jobs[build_id]
        processes = []
        
        # 빌드 스크립트 인자 준비
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

        # Android 빌드 시작
        if platform in ["all", "android"]:
            print(f"🤖 [{build_id}] Starting Android build...")
            self._log_to_build_file(build_id, f"[{build_id}] 🤖 Starting Android build...")
            
            try:
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
            except Exception as e:
                self._log_to_build_file(build_id, f"[{build_id}] ❌ Failed to start Android build: {str(e)}")
                logger.error(f"Failed to start Android build for {build_id}: {e}")

        # iOS 빌드 시작
        if platform in ["all", "ios"]:
            print(f"🍎 [{build_id}] Starting iOS build...")
            self._log_to_build_file(build_id, f"[{build_id}] 🍎 Starting iOS build...")
            
            try:
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
            except Exception as e:
                self._log_to_build_file(build_id, f"[{build_id}] ❌ Failed to start iOS build: {str(e)}")
                logger.error(f"Failed to start iOS build for {build_id}: {e}")

        if not processes:
            self._log_to_build_file(build_id, f"[{build_id}] ❌ No build processes started")
            return False

        # 프로세스 모니터링 시작
        for platform_name, process in processes:
            threading.Thread(
                target=self._monitor_process_output,
                args=(build_id, platform_name, process)
            ).start()

        # 모든 프로세스 완료 대기
        success = True
        for platform_name, process in processes:
            process.wait()
            if process.returncode != 0:
                self._log_to_build_file(build_id, f"[{build_id}] ❌ {platform_name.title()} build failed with code {process.returncode}")
                success = False
            else:
                self._log_to_build_file(build_id, f"[{build_id}] ✅ {platform_name.title()} build completed successfully")

        return success

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
            
            # FVM flavor 매핑 로드
            versions = self._load_fvm_flavor_mapping(build_id, fvm_flavor)
            
            # 빌드 환경 설정
            isolated = self._setup_build_environment(build_id, flavor, branch_name, fvm_flavor, versions)
            env = isolated["env"]
            
            self._log_to_build_file(build_id, f"[{build_id}] 🌿 Branch: {branch_name}")
            print(f"[{build_id}] 🌿 Branch: {branch_name}, Queue: {job.get('queue_key')}")

            # Setup 스크립트 실행
            if not self._run_setup_script(build_id, env):
                return

            # 빌드 스크립트 실행
            if not self._run_build_scripts(build_id, platform, build_name, build_number, env):
                job['status'] = BuildStatus.FAILED.value
                return

            print(f"🎉 [{build_id}] Build pipeline completed")
            self._log_to_build_file(build_id, f"[{build_id}] 🎉 Build pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            job['status'] = BuildStatus.FAILED.value
            self._log_to_build_file(build_id, f"[{build_id}] 💥 Build pipeline failed: {str(e)}")
            print(f"💥 [{build_id}] Build pipeline failed: {str(e)}")
            logger.error(f"Build pipeline failed for {build_id}: {e}")
    
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
    
    def _initialize_progress_tracking(self, build_id: str, platform_name: str):
        """Initialize progress tracking for a platform"""
        job = self.build_jobs[build_id]
        if 'progress' not in job:
            job['progress'] = {}
        job['progress'][platform_name] = {
            'current_step': 'starting',
            'percentage': 0,
            'steps_completed': [],
            'current_message': 'Starting build...'
        }

    def _parse_progress_line(self, line: str, build_id: str, platform_name: str) -> str:
        """Parse structured progress lines and update job progress"""
        job = self.build_jobs[build_id]
        
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
                    return f"[{build_id}][{platform_name.upper()}] 📊 {message} ({percentage}%)"
                except ValueError:
                    return f"[{build_id}][{platform_name.upper()}] {line}"
            else:
                return f"[{build_id}][{platform_name.upper()}] {line}"
                
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
                return f"[{build_id}][{platform_name.upper()}] {status_emoji} {message}"
            else:
                return f"[{build_id}][{platform_name.upper()}] {line}"
        else:
            # Regular log line
            return f"[{build_id}][{platform_name.upper()}] {line}"

    def _monitor_process_output(self, build_id: str, platform_name: str, process: subprocess.Popen):
        """Monitor a subprocess output in real-time with structured progress parsing"""
        self._initialize_progress_tracking(build_id, platform_name)
        
        try:
            for line in process.stdout:
                line = line.strip()
                if line:
                    log_entry = self._parse_progress_line(line, build_id, platform_name)
                    self._log_to_build_file(build_id, log_entry)
                    print(f"{log_entry}")
                    
                    # Keep log size manageable
                    job = self.build_jobs[build_id]
                    if len(job['logs']) > MAX_LOG_LINES:
                        job['logs'] = job['logs'][-KEEP_LOG_LINES:]
                        
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
