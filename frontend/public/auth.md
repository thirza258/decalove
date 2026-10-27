# auth.md

## Overview
Authentication and registration guide for agents using Decalove.

## Discovery
- OAuth Protected Resource Metadata: https://decalove.nevatal.id/.well-known/oauth-protected-resource
- OAuth 2.0 Authorization Server Metadata: https://decalove.nevatal.id/.well-known/oauth-authorization-server
- OpenID Connect Discovery: https://decalove.nevatal.id/.well-known/openid-configuration
- API Catalog: https://decalove.nevatal.id/.well-known/api-catalog
- Agent Card: https://decalove.nevatal.id/.well-known/agent-card.json

## Registration
Public content can be read without credentials. Agents that need write
access register at https://decalove.nevatal.id/api/agent/register and receive bearer credentials.
