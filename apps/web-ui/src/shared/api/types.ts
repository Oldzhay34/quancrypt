import type { components as CoreComponents } from './generated/core';
import type { components as AgentComponents } from './generated/agent';

export type Project = CoreComponents['schemas']['Project'];
export type ProjectPage = CoreComponents['schemas']['ProjectPage'];
export type PrivacyNotice = CoreComponents['schemas']['PrivacyNotice'];
export type Consent = CoreComponents['schemas']['Consent'];
export type ConsentList = CoreComponents['schemas']['ConsentList'];
export type ConsentGrant = CoreComponents['schemas']['ConsentGrant'];
export type ConsentType = ConsentGrant['consentType'];
export type AgentSchemas = AgentComponents['schemas'];

// agent-service (chat, P5.3)
export type Session = AgentSchemas['Session'];
export type ChatMessage = AgentSchemas['Message'];
export type MessagePage = AgentSchemas['MessagePage'];
export type Evidence = AgentSchemas['Evidence'];
export type ClarificationQuestion = AgentSchemas['ClarificationQuestion'];
export type ClarificationAnswer = AgentSchemas['ClarificationAnswer'];
export type ClarificationList = AgentSchemas['ClarificationList'];
export type AnswerKind = ClarificationQuestion['answer_kind'];

// core-service (scan summary, P5.3)
export type Scan = CoreComponents['schemas']['Scan'];
export type ScanPage = CoreComponents['schemas']['ScanPage'];
export type ScanSummary = CoreComponents['schemas']['ScanSummary'];
export type Topology = CoreComponents['schemas']['Topology'];

export const CONSENT_TYPES: readonly ConsentType[] = ['WAREHOUSE_ANALYTICS', 'MODEL_TRAINING'];
