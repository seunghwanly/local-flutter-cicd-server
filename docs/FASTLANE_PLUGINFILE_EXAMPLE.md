# Fastlane Pluginfile 예시

iOS 프로젝트의 `ios/fastlane/Pluginfile`에 다음 내용을 추가하세요:

```ruby
# Datadog CI 플러그인
gem "fastlane-plugin-datadog"
```

## 설치 및 사용법

### 1. Pluginfile 생성
iOS 프로젝트의 `ios/fastlane/` 디렉토리에 `Pluginfile` 파일을 생성하고 위의 내용을 추가합니다.

### 2. 플러그인 설치
```bash
cd ios
bundle exec fastlane add_plugin datadog
```

### 3. Fastfile에 dSYM 업로드 액션 추가
`ios/fastlane/Fastfile`에 다음 액션을 추가합니다:

```ruby
desc "Upload dSYM files to Datadog"
lane :upload_dsym_to_datadog do
  # dSYM 파일 경로 찾기
  dsym_path = lane_context[SharedValues::DSYM_OUTPUT_PATH]
  
  if dsym_path.nil?
    # 기본 경로에서 찾기
    dsym_path = Dir.glob("build/*.xcarchive/dSYMs/**/*.dSYM").first
  end
  
  if dsym_path.nil?
    UI.error("dSYM 파일을 찾을 수 없습니다.")
    return
  end
  
  UI.success("dSYM 파일 발견: #{dsym_path}")
  
  # Datadog에 업로드
  datadog_ci_dsyms_upload(
    dsyms: dsym_path,
    service: "your-app-name",  # 앱 이름으로 변경
    version: get_version_number(target: "Runner")  # 버전 번호
  )
  
  UI.success("dSYM 파일이 Datadog에 성공적으로 업로드되었습니다.")
end
```

### 4. 기존 레인에 통합
기존 빌드 레인(예: `beta`, `release`)에 dSYM 업로드를 추가합니다:

```ruby
lane :beta do
  # 기존 빌드 로직...
  
  # 빌드 성공 후 dSYM 업로드
  upload_dsym_to_datadog
end
```

## 환경변수 설정

`.env` 파일에 다음 환경변수를 설정하세요:

```bash
DATADOG_API_KEY=your_datadog_api_key_here
```

## 주의사항

1. **macOS 전용**: Datadog CI dsyms upload 명령은 macOS에서만 실행됩니다.
2. **API 키 보안**: DATADOG_API_KEY는 환경변수로 설정하고 Git에 커밋하지 마세요.
3. **dSYM 경로**: 빌드 설정에 따라 dSYM 파일 경로가 다를 수 있습니다. 필요시 경로를 조정하세요.
