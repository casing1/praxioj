# 아키텍처·설계 템플릿

[English](../../../templates/design.md) · [문서 정책](../development/documentation-policy.md)

템플릿이다. 작성 지침을 증거로 바꾸고 설계의 현재 상태를 밝힌다. 해당하지 않는 절은 삭제하거나 적용되지 않는 이유를 쓴다.

## Overview

목적, 구현 상태, 관련 Issue, Milestone, PR을 명시한다.

## Motivation

구체적인 문제와 기존 동작이 충분하지 않은 이유를 설명한다.

## Requirements

검증 가능한 기능·자원·운영·보안 요구사항을 적는다.

## Non-goals

변경 범위와 계속 지원하지 않는 기능을 명시한다.

## Current Architecture

관련된 현재 컴포넌트와 소스 계약을 설명한다.

## Proposed Design

책임, 인터페이스, 데이터 흐름, 상태, 실패 처리를 설명하고 제안과 구현을 구분한다.

## Trust Boundaries

자산, 호출자, 권한, 신뢰할 수 없는 입력과 강제 주체를 명시한다.

## Alternatives & Trade-offs

현실적인 대안, 결정의 이유, 비용과 복구 영향을 비교한다.

## Compatibility

API, 프로토콜, DB, 데이터 수명주기, 지원 환경과 롤백 제약의 영향을 설명한다.

## Acceptance Criteria

측정 가능한 완료 조건과 이를 입증하는 테스트를 정의한다.

## Open Questions

미해결 결정, 의존성과 담당자를 적는다. 없다면 적용되지 않는 근거를 쓴다.

## References

Issue, PR, 명세, 위협 모델과 검증 증거를 연결한다. 완성 문서에는 대응 번역 링크를 넣는다.
