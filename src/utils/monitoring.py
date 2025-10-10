#!/usr/bin/env python3
"""
Flutter CI/CD Server - Monitoring Tool

워크스페이스 통계 및 디스크 사용량 모니터링 도구
"""
import psutil
from pathlib import Path
from ..core.config import BUILDS_DIR, QUEUE_LOCKS_DIR, WORKSPACE_ROOT
from datetime import datetime


def format_size(size_bytes: int) -> str:
    """바이트를 읽기 쉬운 형식으로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: Path) -> int:
    """디렉토리 크기 계산"""
    try:
        return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    except Exception as e:
        print(f"⚠️ Error calculating size for {path}: {e}")
        return 0


def get_workspace_stats():
    """워크스페이스 통계 조회"""
    print("=" * 70)
    print("🔍 Flutter CI/CD Server - Workspace Statistics")
    print("=" * 70)
    print()
    
    # 워크스페이스 루트 정보
    print(f"📂 Workspace Root: {WORKSPACE_ROOT}")
    print(f"📂 Builds Directory: {BUILDS_DIR}")
    print(f"🔒 Queue Locks Directory: {QUEUE_LOCKS_DIR}")
    print()
    
    # 빌드 캐시 통계
    print("-" * 70)
    print("📊 Build Caches")
    print("-" * 70)
    
    if not BUILDS_DIR.exists():
        print("⚠️ Builds directory does not exist")
        return
    
    build_dirs = [d for d in BUILDS_DIR.iterdir() if d.is_dir()]
    
    if not build_dirs:
        print("✅ No build caches found")
    else:
        build_stats = []
        total_size = 0
        
        for build_dir in sorted(build_dirs, key=lambda d: d.stat().st_mtime, reverse=True):
            try:
                dir_size = get_dir_size(build_dir)
                dir_mtime = datetime.fromtimestamp(build_dir.stat().st_mtime)
                age = datetime.now() - dir_mtime
                
                build_stats.append({
                    'name': build_dir.name,
                    'size': dir_size,
                    'modified': dir_mtime,
                    'age_days': age.days
                })
                
                total_size += dir_size
                
            except Exception as e:
                print(f"⚠️ Error processing {build_dir.name}: {e}")
        
        # 최근 10개 빌드 표시
        print(f"\n총 {len(build_stats)}개 빌드 캐시\n")
        print(f"{'Build ID':<40} {'Size':>12} {'Age':>8} {'Modified':<20}")
        print("-" * 70)
        
        for stat in build_stats[:10]:
            print(f"{stat['name']:<40} {format_size(stat['size']):>12} {stat['age_days']:>6}d  {stat['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if len(build_stats) > 10:
            print(f"... and {len(build_stats) - 10} more")
        
        print("-" * 70)
        print(f"{'Total':>40} {format_size(total_size):>12}")
        print()
    
    # 락 파일 통계
    print("-" * 70)
    print("🔒 Queue Lock Files")
    print("-" * 70)
    
    if not QUEUE_LOCKS_DIR.exists():
        print("⚠️ Queue locks directory does not exist")
    else:
        lock_files = list(QUEUE_LOCKS_DIR.glob("*.lock"))
        
        if not lock_files:
            print("✅ No lock files found")
        else:
            print(f"\n총 {len(lock_files)}개 락 파일\n")
            print(f"{'Queue Key':<50} {'Age':>8} {'Modified':<20}")
            print("-" * 70)
            
            for lock_file in sorted(lock_files, key=lambda f: f.stat().st_mtime, reverse=True):
                try:
                    lock_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
                    age = datetime.now() - lock_mtime
                    queue_key = lock_file.stem  # 파일명에서 .lock 제거
                    
                    status = "⚠️" if age.total_seconds() > 3600 else "✅"  # 1시간 이상이면 경고
                    print(f"{status} {queue_key:<47} {age.days:>6}d  {lock_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                except Exception as e:
                    print(f"⚠️ Error processing {lock_file.name}: {e}")
    
    print()
    
    # 디스크 사용량
    print("-" * 70)
    print("💾 Disk Usage")
    print("-" * 70)
    
    try:
        disk = psutil.disk_usage(str(WORKSPACE_ROOT))
        
        print(f"\n총 용량:     {format_size(disk.total)}")
        print(f"사용 중:     {format_size(disk.used)} ({disk.percent:.1f}%)")
        print(f"여유 공간:   {format_size(disk.free)}")
        
        # 경고 표시
        if disk.percent > 90:
            print("\n⚠️ 경고: 디스크 사용률이 90%를 초과했습니다!")
            print("   빌드 캐시 정리를 권장합니다: python -c \"from cleanup_scheduler import manual_cleanup; manual_cleanup()\"")
        elif disk.percent > 80:
            print("\n⚠️ 주의: 디스크 사용률이 80%를 초과했습니다.")
        
    except Exception as e:
        print(f"⚠️ Error reading disk usage: {e}")
    
    print()
    print("=" * 70)


def get_build_details(build_id: str):
    """특정 빌드의 상세 정보 조회"""
    build_path = BUILDS_DIR / build_id
    
    if not build_path.exists():
        print(f"❌ Build '{build_id}' not found")
        return
    
    print("=" * 70)
    print(f"🔍 Build Details: {build_id}")
    print("=" * 70)
    print()
    
    try:
        # 전체 크기
        total_size = get_dir_size(build_path)
        dir_mtime = datetime.fromtimestamp(build_path.stat().st_mtime)
        age = datetime.now() - dir_mtime
        
        print(f"총 크기:     {format_size(total_size)}")
        print(f"생성 시간:   {dir_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"경과 시간:   {age.days}일 {age.seconds // 3600}시간")
        print()
        
        # 서브 디렉토리 크기
        print("서브 디렉토리:")
        print("-" * 70)
        
        subdirs = [
            ('repo', build_path / 'repo'),
            ('pub_cache', build_path / 'pub_cache'),
            ('gradle_home', build_path / 'gradle_home'),
        ]
        
        for name, subdir in subdirs:
            if subdir.exists():
                size = get_dir_size(subdir)
                percentage = (size / total_size * 100) if total_size > 0 else 0
                print(f"{name:<20} {format_size(size):>12}  ({percentage:>5.1f}%)")
            else:
                print(f"{name:<20} {'N/A':>12}")
        
    except Exception as e:
        print(f"❌ Error reading build details: {e}")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 특정 빌드 상세 정보 조회
        build_id = sys.argv[1]
        get_build_details(build_id)
    else:
        # 전체 워크스페이스 통계
        get_workspace_stats()

