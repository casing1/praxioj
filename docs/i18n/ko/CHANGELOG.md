# 변경 이력

[English](../../../CHANGELOG.md) · [문서 목차](index.md)

사용자 영향 중심의 변경을 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식으로 관리한다. 향후 실제 발행 버전은 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 따른다. 이 문서 자체로 릴리스나 태그가 생성되지 않으며 미발행 변경은 `Unreleased`에 둔다.

## [Unreleased]

### Added

- 확인 응답이 있는 Judge Lease 갱신, 제한된 합성 Dispatcher Heartbeat Loop와 엄격한 메모리 내 Runner 통신 기반을 추가한다. 공개 Endpoint나 실제 코드 실행은 활성화하지 않는다.

### Changed

- Terminal Judge 증거·이력 보존을 기본 7일/30일로 제한한다. 유지보수에서 적격 Payload·Capability 레코드를 정리하고 남은 평가에 증거 없음 상태를 표시한 뒤 Summary를 삭제한다. 기존 제출 점수는 별도로 유지한다. Payload 정리 후 용량을 회수하고 Summary 레코드에도 별도 한도를 적용한다. Migration `0009_judge_lifecycle`은 업그레이드 시 기존 레코드를 보존한다.

### Documentation

- Issue 우선 GitHub 개발 관리, 동일 Milestone·담당자·라벨 메타데이터, 구체적인 PR 증거와 기존 보호된 Squash Merge 절차를 도입한다. [Governance Issue #16](https://github.com/casing1/praxioj/issues/16).
- 문서 목차, 설계·명세·검증·보안 검토 템플릿, 영문 원본·유지되는 한국어 번역 정책, 상호 링크와 결정적인 문서 검사를 도입한다.
- [M6-A](https://github.com/casing1/praxioj/milestone/1)와 [M6-B](https://github.com/casing1/praxioj/milestone/2)를 별도 계획 객체로 구성한다. 비신뢰 코드 Runner를 활성화하거나 계획을 구현으로 취급하지 않는다.
- 실측 개발 호스트 정보, 공식 Linux Runtime 전제 조건과 미검증 M6-B 격리 수용 조건을 기록한다.

## 과거 Milestone 기록

검증 가능한 개발 이력의 요약이며 발행 버전 릴리스가 아니다. 과거의 릴리스 날짜·버전·태그를 추정하지 않는다.

- **M5:** 버전 관리 실행 프로토콜, 영속 합성 Judge Broker, 제한 Capability, 엄격한 결과·Artifact와 결정적인 Mock Judge. 실제 실행은 기본 Unavailable이다. [PR #15](https://github.com/casing1/praxioj/pull/15), [검증](../../development/validation-m5.md) (영문).
- **M4:** localhost 운영 제어, 공유 할당량, 계정 내보내기·삭제, Worker 유지보수와 격리 PostgreSQL 복구 검증. [PR #14](https://github.com/casing1/praxioj/pull/14), [검증](../../development/validation-m4.md) (영문).
- **M3:** 계정, 서버 세션, 역할·CSRF, 불변 게시, 별도 Lease AI Worker와 Trace 증거 무결성. [PR #12](https://github.com/casing1/praxioj/pull/12), [검증](../../development/validation-m3.md) (영문).
- **M1–M2:** 독립 Framework, Problem SDK, Runtime·Mock 계약, 평가, Platform과 compatible Provider Adapter·제한 논리 Tool을 갖춘 AI Workspace. [최초 공개 소스](https://github.com/casing1/praxioj/commit/bfe6e13), [M1 검증](../../development/validation.md), [M2 검증](../../development/validation-m2.md) (영문).
