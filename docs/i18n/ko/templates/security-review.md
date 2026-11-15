# 보안 검토 템플릿

[English](../../../templates/security-review.md) · [문서 정책](../development/documentation-policy.md)

템플릿이다. 완성된 검토에는 증거와 정의된 리비전이 필요하다. 체크리스트만으로 보안 인증이 되지는 않는다.

## Scope

리비전, 변경 경로, 관련 Issue·PR, 검토 범위와 제외 사항을 식별한다.

## Threat Model

적용할 모델을 연결하고 공격자, 목표와 강제 경계의 변경을 설명한다.

## Assets & Trust Boundaries

보호 데이터, 신원, Capability, 시스템과 권한 전이를 명시한다.

## Assumptions

검증한 사전 조건, 신뢰하는 운영자 가정과 접근할 수 없는 환경을 구분한다.

## Attack Surfaces

접근 가능한 입력, 신원·인가 경로, 파서, 상태 경쟁, 자원과 복구 경로를 식별한다.

## Security Controls

실제 강제 주체와 안전한 거부 동작을 설명하고 계획된 제어와 구현된 제어를 구분한다.

## Tests & Evidence

실행한 테스트, 실제 명령·결과, 수동 검사와 독립 검토 결과물을 기록한다.

## Findings

검증한 발견 사항과 개선을 설명하거나 검토 범위에서 발견 사항이 없었음을 명시한다. 모든 범위가 안전하다고 추론하지 않는다.

## Residual Risks

남은 한계, 운영 의존성과 수용한 절충을 설명한다.

## Unverified Claims

추가 호스트, 자격증명, 배포 또는 OS 격리 시험이 필요한 주장을 명시한다.

## Next Actions

구체적인 후속 Issue, 담당자와 수용 기준을 연결한다. 완성된 검토에는 대응 번역 링크를 넣는다.
