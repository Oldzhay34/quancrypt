import { vi } from 'vitest';
import { FakeBackend, activeConsent } from './fakeBackend';
import { FINDINGS, PLAN, PLAN_ITEMS, REPORT_EN, REPORT_TR, overview } from './reviewFixtures';

/** A backend with a completed QBank-like scan: findings, topology, a CBOM, a plan and its report; consent already given. */
export function reviewBackend(): FakeBackend {
    const backend = new FakeBackend();
    backend.consents = [activeConsent('MODEL_TRAINING')];
    backend.overview = overview();
    backend.findings = FINDINGS;
    backend.artifact = '{"bomFormat":"CycloneDX","specVersion":"1.6"}';
    backend.plan = { plan: PLAN, items: PLAN_ITEMS };
    backend.planReport = { tr: REPORT_TR, en: REPORT_EN };
    return backend;
}

export interface Downloads {
    names: string[];
    blobs: Blob[];
}

/** jsdom has no object URLs or downloads: record what the page hands to the browser instead. */
export function captureDownloads(): Downloads {
    const downloads: Downloads = { names: [], blobs: [] };
    URL.createObjectURL = vi.fn((blob: Blob) => {
        downloads.blobs.push(blob);
        return 'blob:test';
    });
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
        downloads.names.push(this.download);
    });
    return downloads;
}
