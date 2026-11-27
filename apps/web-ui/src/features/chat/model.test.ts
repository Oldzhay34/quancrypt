import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { LOCAL_CHAT_MODEL } from './model';

describe('the model label', () => {
    it("names agent-service's configured chat model", () => {
        // vitest runs in apps/web-ui
        const path = resolve('../../services/agent-service/config/model_config.yaml');
        const configured = /^\s*chat_model:\s*(\S+)/m.exec(readFileSync(path, 'utf-8'))?.[1];
        expect(LOCAL_CHAT_MODEL).toBe(configured);
    });
});
