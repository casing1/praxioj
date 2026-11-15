# 검증 보고서 템플릿

[English](../../../templates/validation.md) · [문서 정책](../development/documentation-policy.md)

템플릿이다. 실제 결과로 작성 지침을 바꾼다. 계획하거나 Skip한 검사를 통과로 기록하지 않는다.

## Target Milestone

목표, 수용 기준, 범위, 비목표와 연결된 Milestone·Issue를 명시한다.

## Commit / Environment

테스트한 리비전, 기준선 리비전, 플랫폼, Runtime 버전, Fixture와 관련 설정을 비밀정보 없이 식별한다.

## Baseline

변경 전에 실행한 명령과 결과, 유효한 비교 범위를 기록한다.

## Implementation

실제 제공한 동작·계약, 소스 경로와 아키텍처 결정을 설명한다.

## Security Tests

신뢰 경계·불변식을 실제 정상·거부·경쟁 테스트와 검토 결과에 대응시킨다.

## Unit / Integration / E2E Tests

명령, 환경, 정확한 수, 의미 있는 관찰과 증거 위치를 기록한다.

## Results & Skips

통과·실패·Skip·차단·미검증을 구분하고 중요한 한계를 설명한다.

## Optimization Measurements

별도 검토, 부하, 비교 가능한 Before/After, 단위, 반복 수, 절충과 회귀 결과를 기록한다. 정당한 변경이 없으면 "reviewed; no justified optimization"과 이유를 적는다.

## Regression Validation

유지된 동작과 관련 마이그레이션·데이터 수명주기 호환성 검사를 기록한다.

## Known Limitations

남은 위험, 지원하지 않는 환경, 외부 연동과 미검증 보장을 명시한다.

## GitHub PR / CI Results

실제 Issue, Milestone, PR, Head·병합 리비전과 CI/CodeQL을 연결한다. 조회한 메타데이터로 담당자, 라벨, Milestone과 리뷰 결과를 확인하고 로컬 검사와 원격 CI를 구분한다.

## Final Status

각 종료 조건을 증거와 비교하고 미완료 작업과 후속 Issue를 명시한다. 필수 작업을 해결·검증한 뒤에만 Milestone을 닫는다. 대응 번역을 연결한다.
