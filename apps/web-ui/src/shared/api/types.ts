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

export const CONSENT_TYPES: readonly ConsentType[] = ['WAREHOUSE_ANALYTICS', 'MODEL_TRAINING'];
