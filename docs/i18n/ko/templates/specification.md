# 기술 명세 템플릿

[English](../../../templates/specification.md) · [문서 정책](../development/documentation-policy.md)

템플릿이다. 실제 계약과 구현 상태를 정의한다. 작성 지침만 남은 문서는 명세가 아니다.

## Overview

목적, 현재 구현 상태, Issue, Milestone과 관련 설계를 명시한다.

## Scope

포함하는 동작과 명시적 비목표를 정의한다.

## Terminology

코드 식별자를 바꾸지 않고 용어, 주체와 권한을 정의한다.

## Data Model

필드, 형식, 필수 값, 크기 제한, 식별자와 영속성 소유권을 명시한다.

## Interface / Protocol

동작, 요청·결과 형식과 관련 예시를 설명한다.

## Preconditions

인증·인가, 소스·버전, 자원과 Runtime 요구사항을 명시한다.

## State Transitions

허용 전이, 종료 상태, 동시성과 멱등성 동작을 정의한다.

## Validation Rules

파서, Digest, 자원, 경로와 관련 자원 간 결합 검사를 필요한 범위에서 명시한다.

## Security Invariants

신뢰 경계, 제한 권한, 폐기와 비밀정보 배제를 식별한다.

## Error Handling

통제된 오류, Timeout, 취소, 복구와 관찰 가능한 결과를 정의한다.

## Versioning

프로토콜·스키마 버전과 알 수 없는 버전의 처리 방식을 명시한다.

## Compatibility

기존 호출자, 마이그레이션, 롤백과 폐기 예정 동작의 영향을 설명한다.

## Test Requirements

정상·거부·경계·회귀·동시성 테스트, 실제 증거, 관련 PR과 완성 문서의 번역을 연결한다.
